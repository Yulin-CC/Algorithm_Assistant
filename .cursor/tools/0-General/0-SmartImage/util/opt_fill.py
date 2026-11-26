"""
# @Author: Yullin
# @Date: 2026-11-11
# @Description: 读漏检裁图。先由调用方确认落掩膜还是落框。掩膜用 Triton SAM 多边形。框默认定位后再取掩膜的水平最小外接矩形。不改原标注。
# @Command: python util/opt_fill.py --dataset /path --shape mask --locate gpi --refine sam
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np

_PKG_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
_REPO = os.path.normpath(os.path.join(_PKG_ROOT, "..", "..", ".."))
_MODEL_UTIL = os.path.join(_REPO, "server", "util")
_GPI_UTIL = os.path.join(_REPO, "tools", "1-DataEngine", "2-Image-DetSeg", "groundingpi", "util")
_SAM3_UTIL = os.path.join(_REPO, "tools", "1-DataEngine", "2-Image-DetSeg", "sam3", "util")
if _MODEL_UTIL not in sys.path:
    sys.path.insert(0, _MODEL_UTIL)

from common import ensure_dir, load_json, task_draft, write_json
from overlay import cd_layout, qa_jsons_dir, resolve_jsons_dir, shape_xyxy

FILL_SLUG = "fill"
MISS_SLUG = "miss"
LOCATE_CHOICES = ("gpi", "sam3", "off")
REFINE_CHOICES = ("sam", "off")
SHAPE_CHOICES = ("mask", "box")
SAM3_CONF = 0.45


def default_sam3_weights() -> str:
    return os.path.join(_REPO, "tools", "1-DataEngine", "_weights", "sam3.pt")


def box_iou(a, b) -> float:
    ax0, ay0, ax1, ay1 = [float(v) for v in a]
    bx0, by0, bx1, by1 = [float(v) for v in b]
    ix0, iy0 = max(ax0, bx0), max(ay0, by0)
    ix1, iy1 = min(ax1, bx1), min(ay1, by1)
    inter = max(0.0, ix1 - ix0) * max(0.0, iy1 - iy0)
    if inter <= 0:
        return 0.0
    area_a = max(0.0, ax1 - ax0) * max(0.0, ay1 - ay0)
    area_b = max(0.0, bx1 - bx0) * max(0.0, by1 - by0)
    union = area_a + area_b - inter
    return inter / union if union else 0.0


def overlaps_existing(xyxy, shapes, thr=0.5) -> bool:
    ax0, ay0, ax1, ay1 = [float(v) for v in xyxy]
    area = max(0.0, ax1 - ax0) * max(0.0, ay1 - ay0)
    if area <= 0:
        return True
    for shape in shapes or []:
        other = shape_xyxy(shape)
        if not other:
            continue
        ix0, iy0 = max(ax0, other[0]), max(ay0, other[1])
        ix1, iy1 = min(ax1, other[2]), min(ay1, other[3])
        inter = max(0.0, ix1 - ix0) * max(0.0, iy1 - iy0)
        if inter / area >= thr or box_iou(xyxy, other) >= thr:
            return True
    return False


def shift_xyxy(xyxy, origin) -> list:
    ox, oy = float(origin[0]), float(origin[1])
    return [
        float(xyxy[0]) + ox, float(xyxy[1]) + oy,
        float(xyxy[2]) + ox, float(xyxy[3]) + oy,
    ]


def shift_pts(pts, origin) -> list:
    ox, oy = float(origin[0]), float(origin[1])
    return [[float(x) + ox, float(y) + oy] for x, y in pts]


def norm_xyxy(box) -> list:
    x0, y0, x1, y1 = [float(v) for v in box[:4]]
    return [min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)]


def xyxy_of(pts) -> list:
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return [min(xs), min(ys), max(xs), max(ys)]


def load_shapes(json_path: str):
    data = load_json(json_path, default={}) or {}
    shapes = data.get("shapes") if isinstance(data.get("shapes"), list) else []
    return shapes


def crop_problem(item) -> str:
    if item.get("crop_error"):
        return str(item["crop_error"])
    path = str(item.get("crop") or "")
    window = item.get("window") or []
    if not path or not os.path.isfile(path):
        return "裁图不存在，先重跑 label_miss.py"
    if len(window) < 4:
        return "裁图窗口缺失，先重跑 label_miss.py"
    return ""


def make_gpi(base_url, model, timeout):
    if _GPI_UTIL not in sys.path:
        sys.path.insert(0, _GPI_UTIL)
    from detect_segment import _make_gpi

    client, name = _make_gpi(base_url, model, timeout, False)
    return client, name


def locate_gpi(client, crop_path: str, label: str) -> list:
    if _GPI_UTIL not in sys.path:
        sys.path.insert(0, _GPI_UTIL)
    from detect_segment import gpi_boxes

    boxes = []
    for row in gpi_boxes(client, crop_path, [label]):
        box = row.get("box") or []
        if len(box) < 4:
            continue
        boxes.append({
            "label": str(row.get("label") or label),
            "xyxy": norm_xyxy(box),
        })
    return boxes


def load_sam3(weights: str, device: str):
    path = weights or default_sam3_weights()
    if not os.path.isfile(path):
        raise SystemExit(f"找不到 SAM3 权重: {path}")
    if _SAM3_UTIL not in sys.path:
        sys.path.insert(0, _SAM3_UTIL)
    from batch_prelabel_json import load_predictor

    args = SimpleNamespace(
        weights=path, device=str(device), half=True, conf=SAM3_CONF, iou=0.45,
    )
    return load_predictor(args), path


def locate_sam3(predictor, crop_path: str, label: str) -> list:
    if _SAM3_UTIL not in sys.path:
        sys.path.insert(0, _SAM3_UTIL)
    from batch_prelabel_json import predict_one, result_to_shapes

    boxes = []
    for res in predict_one(predictor, Path(crop_path), [label]):
        for shape in result_to_shapes(res, "detect", SAM3_CONF, [label]):
            pts = shape.get("points") or []
            if len(pts) < 2:
                continue
            x0, y0 = pts[0][:2]
            x1, y1 = pts[1][:2]
            boxes.append({
                "label": str(shape.get("label") or label),
                "xyxy": norm_xyxy([x0, y0, x1, y1]),
            })
    return boxes


def mask_shape(mask, label: str, origin) -> dict:
    from sam_client import mask_to_polygon

    pts = mask_to_polygon(mask)
    if not pts:
        return {}
    full = shift_pts(pts, origin)
    return {
        "label": label,
        "shape_type": "polygon",
        "points": full,
        "xyxy": xyxy_of(full),
    }


def emit_shape(mask, label: str, origin, shape_mode: str) -> dict:
    """掩膜留下多边形。框取这块掩膜的水平最小外接矩形。"""
    poly = mask_shape(mask, label, origin)
    if not poly or shape_mode != "box":
        return poly
    return rectangle_shape(poly["xyxy"], label, (0.0, 0.0))


def rectangle_shape(xyxy, label: str, origin) -> dict:
    full = shift_xyxy(xyxy, origin)
    return {
        "label": label,
        "shape_type": "rectangle",
        "points": [[full[0], full[1]], [full[2], full[3]]],
        "xyxy": full,
    }


def keep_shapes(candidates, existing) -> tuple:
    """已有目标和本批已经留下的新框都参与去重。挨在一起、不是同一辆的车不会被去掉。"""
    kept, dropped = [], 0
    seen = list(existing or [])
    for shape in candidates:
        if overlaps_existing(shape["xyxy"], seen):
            dropped += 1
            continue
        kept.append(shape)
        seen.append(shape)
    return kept, dropped


def finish_row(base, shapes, dropped, errors) -> dict:
    row = dict(base)
    row["shapes"] = shapes
    row["n_dropped"] = dropped
    if shapes:
        row["status"] = "filled"
    elif dropped:
        row["status"] = "dropped"
    elif errors:
        row["status"] = "failed"
        row["error"] = errors[0]
    else:
        row["status"] = "empty"
    return row


def fill_one(item, existing, locate, refine, shape_mode, gpi, predictor, sam) -> dict:
    label = str(item.get("label") or "")
    base = {
        "label": label,
        "cx": item.get("cx"),
        "cy": item.get("cy"),
        "reason": item.get("reason") or "",
        "window": item.get("window") or [],
        "point": item.get("point") or [],
        "crop": item.get("crop") or "",
        "shapes": [],
    }
    problem = crop_problem(item)
    if problem:
        base["status"] = "failed"
        base["error"] = problem
        return base
    window = item["window"]
    origin = window[:2]
    crop_path = str(item["crop"])
    try:
        if locate == "gpi":
            boxes = locate_gpi(gpi, crop_path, label)
        elif locate == "sam3":
            boxes = locate_sam3(predictor, crop_path, label)
        else:
            boxes = []
    except Exception as e:
        base["status"] = "failed"
        base["error"] = str(e)
        return base
    if locate != "off" and not boxes:
        base["status"] = "empty"
        return base
    if refine != "sam":
        shapes = [rectangle_shape(box["xyxy"], box["label"], origin) for box in boxes]
        kept, dropped = keep_shapes(shapes, existing)
        return finish_row(base, kept, dropped, [])
    try:
        encoded = sam.encode_file(crop_path)
    except Exception as e:
        base["status"] = "failed"
        base["error"] = str(e)
        return base
    shapes, errors = [], []
    if locate == "off":
        point = item.get("point") or []
        if len(point) < 2:
            base["status"] = "failed"
            base["error"] = "缺少报点，先重跑 label_miss.py"
            return base
        local = [float(point[0]) - float(origin[0]), float(point[1]) - float(origin[1])]
        try:
            mask = sam.decode_point(encoded, local)
        except Exception as e:
            base["status"] = "failed"
            base["error"] = str(e)
            return base
        shape = emit_shape(mask, label, origin, shape_mode)
        if not shape:
            errors.append("sam 没有掩膜")
        else:
            shapes.append(shape)
    else:
        for box in boxes:
            try:
                mask = sam.decode_box(encoded, box["xyxy"])
            except Exception as e:
                errors.append(str(e))
                continue
            shape = emit_shape(mask, box["label"], origin, shape_mode)
            if not shape:
                errors.append("sam 没有掩膜")
                continue
            shapes.append(shape)
    kept, dropped = keep_shapes(shapes, existing)
    return finish_row(base, kept, dropped, errors)


def overlap_ratio(shape, mask) -> float:
    """新掩膜落在已有变化图上的面积比例。"""
    pts = shape.get("points") or []
    if mask is None or len(pts) < 3:
        return 0.0
    h, w = mask.shape[:2]
    canvas = np.zeros((h, w), np.uint8)
    poly = np.array([[int(round(p[0])), int(round(p[1]))] for p in pts], np.int32)
    cv2.fillPoly(canvas, [poly], 1)
    area = int(canvas.sum())
    if area <= 0:
        return 1.0
    inter = int(np.logical_and(canvas > 0, mask > 0).sum())
    return inter / float(area)


def drop_covered(shapes, mask, thr=0.5) -> tuple:
    kept, dropped = [], 0
    for shape in shapes or []:
        if overlap_ratio(shape, mask) >= thr:
            dropped += 1
            continue
        kept.append(shape)
    return kept, dropped


def write_mask_png(path: str, hw, shapes) -> str:
    canvas = np.zeros(hw, np.uint8)
    for shape in shapes or []:
        pts = shape.get("points") or []
        if len(pts) < 3:
            continue
        poly = np.array([[int(round(p[0])), int(round(p[1]))] for p in pts], np.int32)
        cv2.fillPoly(canvas, [poly], 255)
    ensure_dir(os.path.dirname(path) or ".")
    ok, buf = cv2.imencode(".png", canvas)
    if not ok:
        raise RuntimeError(f"无法写掩膜: {path}")
    buf.tofile(path)
    return path


def count_status(rows) -> dict:
    stats = {"filled": 0, "dropped": 0, "empty": 0, "failed": 0}
    for row in rows:
        key = row.get("status")
        if key in stats:
            stats[key] += 1
        else:
            stats["failed"] += 1
    return stats


def run_fill(dataset_root, shape, locate="gpi", refine="sam", weights="", base_url="",
             model="", timeout=600, device="0", limit=None, masks=""):
    """定位用数据引擎单图函数。修边用 Triton SAM。不改原标注，不再问 Qwen。"""
    shape = str(shape or "").strip().lower()
    locate = str(locate or "gpi").strip().lower()
    refine = str(refine or "sam").strip().lower()
    if shape not in SHAPE_CHOICES:
        raise SystemExit(f"先确认落盘形状：--shape {'/'.join(SHAPE_CHOICES)}")
    if locate not in LOCATE_CHOICES or refine not in REFINE_CHOICES:
        raise SystemExit(f"locate 为 {'/'.join(LOCATE_CHOICES)}，refine 为 {'/'.join(REFINE_CHOICES)}")
    if locate == "off" and refine == "off":
        raise SystemExit("locate 和 refine 不能同时关掉")
    if shape == "mask" and refine != "sam":
        raise SystemExit("掩膜要 Triton SAM 出结果。直出框时用 --shape box --refine off")
    layout = cd_layout(resolve_jsons_dir(dataset_root, masks), dataset_root) if masks else None
    folder = os.path.join(layout["miss"], "jsons") if layout else qa_jsons_dir(dataset_root, MISS_SLUG)
    if not os.path.isdir(folder):
        raise SystemExit(f"先跑 label_miss.py，找不到 {folder}")
    files = sorted(Path(folder).glob("*.json"))
    if limit:
        files = files[: int(limit)]
    records = []
    has_crop = False
    for path in files:
        rec = load_json(str(path))
        if not isinstance(rec, dict):
            continue
        records.append((path, rec))
        for item in rec.get("miss") or []:
            if not crop_problem(item):
                has_crop = True
                break
    paired = any(rec.get("pair") for _, rec in records)
    if paired and (locate != "off" or refine != "sam" or shape != "mask"):
        raise SystemExit(
            "变化检测补标只走 Qwen 报点加 Triton SAM："
            "--shape mask --locate off --refine sam。不走 GroundingPI。"
        )
    gpi, gpi_name, predictor, sam = None, "", None, None
    if has_crop and locate == "gpi":
        gpi, gpi_name = make_gpi(base_url, model, timeout)
    if has_crop and locate == "sam3":
        predictor, _weights = load_sam3(weights, device)
    if has_crop and refine == "sam":
        from sam_client import TritonSAM
        sam = TritonSAM()
    if paired:
        if not layout:
            first_mask = str((records[0][1] or {}).get("mask") or "")
            layout = cd_layout(first_mask, dataset_root)
        out_dir = os.path.join(layout["fill"], "jsons")
        mask_dir = os.path.join(layout["fill"], "masks")
    else:
        out_dir = qa_jsons_dir(dataset_root, FILL_SLUG)
        mask_dir = os.path.join(task_draft(dataset_root, FILL_SLUG), "masks")
    ensure_dir(out_dir)
    totals = {"filled": 0, "dropped": 0, "empty": 0, "failed": 0}
    for path, rec in records:
        existing = [] if rec.get("pair") else load_shapes(str(rec.get("json") or ""))
        src_mask = None
        if rec.get("pair"):
            mask_path = str(rec.get("mask") or "")
            if mask_path and os.path.isfile(mask_path):
                from cd_pair import read_mask
                src_mask = read_mask(mask_path)
        items = []
        kept_shapes = []
        for item in rec.get("miss") or []:
            row = fill_one(item, existing, locate, refine, shape, gpi, predictor, sam)
            if item.get("phase"):
                row["phase"] = item.get("phase")
            if rec.get("pair") and row.get("shapes"):
                kept, n_drop = drop_covered(row.get("shapes") or [], src_mask)
                row["n_dropped"] = int(row.get("n_dropped") or 0) + n_drop
                row["shapes"] = kept
                if not kept and row.get("status") == "filled":
                    row["status"] = "dropped"
            items.append(row)
            existing.extend(row.get("shapes") or [])
            kept_shapes.extend(row.get("shapes") or [])
        stats = count_status(items)
        for key in totals:
            totals[key] += stats[key]
        mask_out = ""
        if rec.get("pair") and kept_shapes:
            hw = src_mask.shape[:2] if src_mask is not None else None
            if hw is None:
                from cd_pair import read_bgr
                image = str(rec.get("image") or "")
                bgr = read_bgr(image) if image else None
                hw = bgr.shape[:2] if bgr is not None else None
            if hw is not None:
                mask_out = write_mask_png(
                    os.path.join(mask_dir, f"{path.stem}.png"), hw, kept_shapes,
                )
        payload = {
            "stem": rec.get("stem") or path.stem,
            "image": rec.get("image") or "",
            "json": rec.get("json") or "",
            "shape": shape,
            "locate": locate,
            "refine": refine,
            "model": gpi_name,
            "n": len(items),
            "items": items,
        }
        if rec.get("pair"):
            payload["pair"] = True
            payload["before"] = rec.get("before") or ""
            payload["mask"] = rec.get("mask") or ""
            payload["prompt"] = rec.get("prompt") or ""
            payload["mask_out"] = mask_out
        write_json(os.path.join(out_dir, path.name), payload)
    print(
        f"opt-fill shape={shape} locate={locate} refine={refine} filled={totals['filled']} "
        f"dropped={totals['dropped']} empty={totals['empty']} failed={totals['failed']} → {out_dir}"
    )
    return totals


def parse_args():
    p = argparse.ArgumentParser(description="漏检裁图上定位。先选定掩膜或框。不改原标注")
    p.add_argument("--dataset", required=True)
    p.add_argument("--shape", choices=SHAPE_CHOICES, required=True, help="mask 落 SAM 多边形；box 落掩膜的水平最小外接矩形")
    p.add_argument("--locate", choices=LOCATE_CHOICES, default="gpi")
    p.add_argument("--refine", choices=REFINE_CHOICES, default="sam")
    p.add_argument("--weights", default="", help="SAM3 权重。空则用 tools/1-DataEngine/_weights/sam3.pt")
    p.add_argument("--device", default="0")
    p.add_argument("--base_url", default="", help="GroundingPI 地址。空则读 vllm_server.json")
    p.add_argument("--model", default="")
    p.add_argument("--timeout", type=int, default=600)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--masks", default="", help="变化检测：漏检 json 在该版本 miss/jsons，补标写 fill/")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run_fill(
        args.dataset,
        shape=args.shape,
        locate=args.locate,
        refine=args.refine,
        weights=args.weights,
        base_url=args.base_url,
        model=args.model,
        timeout=args.timeout,
        device=args.device,
        limit=args.limit,
        masks=args.masks,
    )
