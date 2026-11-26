"""
# @Author: Yullin
# @Date: 2026-11-11
# @Description: 把定档 adjust 的框当成报点，裁图后走补标链重出形状。变化检测 --masks 改为 Qwen 报点再交 Triton SAM。不改原标注。
# @Command: python util/opt_adjust.py --dataset /path --shape mask
# @Command: python util/opt_adjust.py --dataset /path --masks label --prompt "新建或拆除的建筑"
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import cv2
import numpy as np

_PKG_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
_REPO = os.path.normpath(os.path.join(_PKG_ROOT, "..", "..", ".."))
_MODEL_UTIL = os.path.join(_REPO, "server", "util")
if _MODEL_UTIL not in sys.path:
    sys.path.insert(0, _MODEL_UTIL)

from common import ensure_dir, load_json, task_draft, write_json
from label_grade import item_grade
from label_miss import COVER_GRAY, COVER_PAD, CROP_SIDE, ask_cd, gray_shapes, pack_crops, read_bgr
from opt_fill import (
    LOCATE_CHOICES,
    REFINE_CHOICES,
    SHAPE_CHOICES,
    count_status,
    fill_one,
    load_sam3,
    load_shapes,
    make_gpi,
    write_mask_png,
)
from overlay import (
    cd_layout,
    cover_gray,
    model_dir,
    model_name_for,
    qa_jsons_dir,
    resolve_jsons_dir,
    save_jpg,
    shape_xyxy,
    vis_dir,
)

ADJUST_SLUG = "adjust"
OVERLAY_SLUG = "overlay"


def adjust_crop_dir(dataset_root: str) -> str:
    return os.path.join(task_draft(dataset_root, ADJUST_SLUG), "crop")


def shape_center(shape) -> tuple:
    box = shape.get("xyxy") or shape_xyxy(shape)
    if not box:
        return None
    return (float(box[0]) + float(box[2])) / 2.0, (float(box[1]) + float(box[3])) / 2.0


def holds_point(shape, px, py) -> bool:
    """新形状要罩住原来的中心，才算这一个 adjust 的替换。"""
    box = shape.get("xyxy") or shape_xyxy(shape)
    if not box:
        return False
    if not (box[0] <= px <= box[2] and box[1] <= py <= box[3]):
        return False
    pts = shape.get("points") or []
    if str(shape.get("shape_type") or "") == "polygon" and len(pts) >= 3:
        arr = np.asarray(pts, dtype=np.float32)
        return cv2.pointPolygonTest(arr, (float(px), float(py)), False) >= 0
    return True


def take_for_points(shapes, anchors) -> dict:
    taken = {a["index"]: [] for a in anchors}
    for shape in shapes or []:
        center = shape_center(shape)
        hits = [a for a in anchors if holds_point(shape, a["px"], a["py"])]
        if not hits or center is None:
            continue
        best = min(hits, key=lambda a: (a["px"] - center[0]) ** 2 + (a["py"] - center[1]) ** 2)
        taken[best["index"]].append(shape)
    return taken


def point_of(shape, width, height):
    box = shape_xyxy(shape)
    if not box or width <= 0 or height <= 0:
        return None
    cx = ((float(box[0]) + float(box[2])) / 2.0) / float(width)
    cy = ((float(box[1]) + float(box[3])) / 2.0) / float(height)
    return cx, cy, box


def anchors_of(crop, width, height) -> list:
    anchors = []
    for point in crop.get("points") or []:
        if point.get("index") is None:
            continue
        anchors.append({
            "index": int(point["index"]),
            "label": point.get("label") or "",
            "issue": point.get("issue") or "",
            "reason": point.get("reason") or "",
            "cx": point.get("cx"),
            "cy": point.get("cy"),
            "px": float(point.get("cx") or 0) * width,
            "py": float(point.get("cy") or 0) * height,
        })
    return anchors


def prepare_image(dataset_root, rec) -> tuple:
    """不改要调整的目标。其余目标涂灰，再按中心裁图。"""
    json_path = str(rec.get("json") or "")
    image_path = str(rec.get("image") or "")
    shapes = load_shapes(json_path)
    picked = []
    for item in rec.get("items") or []:
        if item.get("source") == "failed" or item.get("view_skip"):
            continue
        if item_grade(item) != "adjust":
            continue
        index = item.get("index")
        label = str(item.get("label") or "")
        if not isinstance(index, int) or index < 0 or index >= len(shapes):
            picked.append({"error": "定档下标对不上当前标注", "index": index, "label": label})
            continue
        shape = shapes[index]
        if str(shape.get("label") or "") != label:
            picked.append({"error": "定档下标上的类别已经变了", "index": index, "label": label})
            continue
            picked.append({
                "index": index,
                "label": label,
                "issue": item.get("issue") or "",
                "reason": item.get("reason") or "",
                "shape": shape,
            })
    if not picked:
        return shapes, [], [], ""
    bgr = read_bgr(image_path) if image_path else None
    if bgr is None:
        return shapes, picked, [], "读图失败"
    height, width = bgr.shape[:2]
    ready, bad = [], []
    for row in picked:
        if row.get("error"):
            bad.append(row)
            continue
        located = point_of(row["shape"], width, height)
        if not located:
            bad.append({**row, "error": "框没有点"})
            continue
        cx, cy, box = located
        ready.append({**row, "cx": cx, "cy": cy, "xyxy": box})
    if not ready:
        return shapes, bad, [], ""
    keep = {row["index"] for row in ready}
    others = [shape for i, shape in enumerate(shapes) if i not in keep]
    drawn = cover_gray(bgr, gray_shapes(image_path, others), COVER_GRAY, COVER_PAD)
    vis = os.path.join(vis_dir(dataset_root, ADJUST_SLUG), f"{rec.get('stem')}.jpg")
    ensure_dir(os.path.dirname(vis))
    save_jpg(vis, drawn)
    crops = pack_crops(
        dataset_root,
        rec.get("stem") or Path(json_path).stem,
        drawn,
        ready,
        CROP_SIDE,
        adjust_crop_dir(dataset_root),
    )
    return shapes, ready + bad, crops, ""


def rows_for_crop(crop, anchors, located, refine_row) -> list:
    by_index = {row["index"]: row for row in located if "xyxy" in row}
    if crop.get("crop_error") or refine_row.get("status") == "failed":
        error = crop.get("crop_error") or refine_row.get("error") or "裁图失败"
        return [_closed(by_index[a["index"]], crop, "failed", [], error) for a in anchors if a["index"] in by_index]
    taken = take_for_points(refine_row.get("shapes") or [], anchors)
    rows = []
    for anchor in anchors:
        src = by_index.get(anchor["index"])
        if not src:
            continue
        shapes = taken.get(anchor["index"]) or []
        if shapes:
            rows.append(_closed(src, crop, "filled", shapes, ""))
        elif refine_row.get("status") == "dropped":
            rows.append(_closed(src, crop, "dropped", [], ""))
        else:
            rows.append(_closed(src, crop, "empty", [], ""))
    return rows


def _closed(src, crop, status, shapes, error) -> dict:
    row = {
        "index": src["index"],
        "label": src.get("label") or "",
        "issue": src.get("issue") or "",
        "reason": src.get("reason") or "",
        "xyxy": src.get("xyxy") or [],
        "cx": src.get("cx"),
        "cy": src.get("cy"),
        "window": crop.get("window") or [],
        "crop": crop.get("crop") or "",
        "status": status,
        "shapes": shapes,
    }
    if error:
        row["error"] = error
    return row


def run_adjust(dataset_root, shape, locate="gpi", refine="sam", weights="", base_url="",
               model="", timeout=600, device="0", limit=None):
    """adjust 的框中心就是报点。其余流程与补标相同。不改原标注。"""
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
    folder = qa_jsons_dir(dataset_root, OVERLAY_SLUG)
    if not os.path.isdir(folder):
        raise SystemExit(f"先跑 label_grade.py，找不到 {folder}")
    files = sorted(Path(folder).glob("*.json"))
    if limit:
        files = files[: int(limit)]
    records = []
    for path in files:
        rec = load_json(str(path))
        if isinstance(rec, dict):
            records.append(rec)
    needs_model = False
    prepared = []
    for rec in records:
        shapes, located, crops, error = prepare_image(dataset_root, rec)
        prepared.append((rec, shapes, located, crops, error))
        if any(not crop.get("crop_error") for crop in crops):
            needs_model = True
    gpi, gpi_name, predictor, sam = None, "", None, None
    if needs_model and locate == "gpi":
        gpi, gpi_name = make_gpi(base_url, model, timeout)
    if needs_model and locate == "sam3":
        predictor, _weights = load_sam3(weights, device)
    if needs_model and refine == "sam":
        from sam_client import TritonSAM
        sam = TritonSAM()
    out_dir = qa_jsons_dir(dataset_root, ADJUST_SLUG)
    ensure_dir(out_dir)
    totals = {"filled": 0, "dropped": 0, "empty": 0, "failed": 0}
    for rec, shapes, located, crops, error in prepared:
        stem = rec.get("stem") or ""
        items = []
        if error:
            for row in located:
                items.append(_closed(row, {}, "failed", [], error))
        else:
            adjust_at = {row["index"] for row in located if "xyxy" in row}
            existing = [s for i, s in enumerate(shapes) if i not in adjust_at]
            height = width = 0
            image = str(rec.get("image") or "")
            bgr = read_bgr(image) if image else None
            if bgr is not None:
                height, width = bgr.shape[:2]
            used = set()
            for crop in crops:
                anchors = anchors_of(crop, width, height)
                used.update(a["index"] for a in anchors)
                if crop.get("crop_error"):
                    items.extend(rows_for_crop(crop, anchors, located, {"status": "failed"}))
                    continue
                others = [s for s in existing]
                row = fill_one(crop, others, locate, refine, shape, gpi, predictor, sam)
                got = rows_for_crop(crop, anchors, located, row)
                items.extend(got)
                for one in got:
                    existing.extend(one.get("shapes") or [])
            for row in located:
                if row.get("error"):
                    items.append(_closed(row, {}, "failed", [], row["error"]))
                elif row["index"] not in used:
                    items.append(_closed(row, {}, "failed", [], "没有裁图"))
        stats = count_status(items)
        for key in totals:
            totals[key] += stats[key]
        write_json(os.path.join(out_dir, f"{stem}.json"), {
            "stem": stem,
            "image": rec.get("image") or "",
            "json": rec.get("json") or "",
            "shape": shape,
            "locate": locate,
            "refine": refine,
            "model": gpi_name,
            "n": len(items),
            "items": items,
        })
    print(
        f"opt-adjust shape={shape} locate={locate} refine={refine} filled={totals['filled']} "
        f"dropped={totals['dropped']} empty={totals['empty']} failed={totals['failed']} → {out_dir}"
    )
    return totals


def _shape_holds(shape, px, py) -> bool:
    pts = shape.get("points") or []
    if len(pts) < 3:
        return False
    poly = np.array(pts, np.float32)
    return cv2.pointPolygonTest(poly, (float(px), float(py)), False) >= 0


def _adjust_view(before, after, mask, comp):
    from cd_pair import crop_window, paint_mask, stitch

    others = (mask > 0) & ~np.asarray(comp["mask"]).astype(bool)
    gray_left = before.copy()
    gray_right = after.copy()
    gray_left[others] = COVER_GRAY
    gray_right[others] = COVER_GRAY
    nx0, ny0, nx1, ny1 = crop_window(before.shape, comp["xyxy"])
    left = gray_left[ny0:ny1, nx0:nx1]
    right = gray_right[ny0:ny1, nx0:nx1]
    sl = comp["mask"][ny0:ny1, nx0:nx1]
    view = stitch(
        paint_mask(left, sl, (0, 220, 255)),
        paint_mask(right, sl, (0, 220, 255)),
    )
    return view, left, right, (nx0, ny0)


def _keep_point_shapes(row, px, py) -> dict:
    kept = [shape for shape in row.get("shapes") or [] if _shape_holds(shape, px, py)]
    if row.get("shapes") and not kept:
        row = dict(row)
        row["shapes"] = []
        row["status"] = "dropped"
        row["error"] = "新掩膜没有罩住报点"
        return row
    if kept and len(kept) != len(row.get("shapes") or []):
        row = dict(row)
        row["shapes"] = kept
    return row


def run_adjust_change(dataset_root, prompt="", prompt_file="", limit=None,
                      timeout=600, base_url="", model="", masks=""):
    """变化检测 adjust：Qwen 重新报点，Triton SAM 出掩膜。不走 GroundingPI。"""
    from cd_pair import cd_locate_prompt, mask_components, read_bgr as read_pair, read_mask, require_task
    from describe import _make_client
    from label_miss import place_cd_points

    task = require_task(prompt, prompt_file)
    locate_prompt = cd_locate_prompt(task, "adjust")
    mask_dir = resolve_jsons_dir(dataset_root, masks) if masks else ""
    layout = cd_layout(mask_dir, dataset_root) if mask_dir else None
    folder = layout["jsons"] if layout else qa_jsons_dir(dataset_root, OVERLAY_SLUG)
    if not os.path.isdir(folder):
        raise SystemExit(f"先跑 label_grade.py --masks，找不到 {folder}")
    files = sorted(Path(folder).glob("*.json"))
    if limit:
        files = files[: int(limit)]
    records = []
    for path in files:
        rec = load_json(str(path))
        if isinstance(rec, dict) and rec.get("pair"):
            records.append(rec)
    if not records:
        raise SystemExit(f"变化检测调整需要 {folder} 里 pair=true 的定档结果")
    client, model_name = _make_client(base_url, model, timeout)
    jobs = []
    for rec in records:
        stem = str(rec.get("stem") or "")
        try:
            before = read_pair(str(rec.get("before") or ""))
            after = read_pair(str(rec.get("image") or ""))
            mask = read_mask(str(rec.get("mask") or ""))
            if before.shape[:2] != after.shape[:2] or before.shape[:2] != mask.shape[:2]:
                raise ValueError("A/B/掩膜尺寸不一致")
            comps = mask_components(mask)
        except Exception as e:
            jobs.append({"rec": rec, "stem": stem, "error": str(e), "crops": []})
            continue
        crops = []
        for item in rec.get("items") or []:
            if item.get("source") == "failed" or item.get("view_skip"):
                continue
            if item_grade(item) != "adjust":
                continue
            index = item.get("index")
            if not isinstance(index, int) or index < 0 or index >= len(comps):
                crops.append({
                    "index": index, "status": "failed", "error": "定档下标对不上连通域",
                    "shapes": [], "label": "change", "issue": item.get("issue") or "",
                })
                continue
            comp = comps[index]
            view, gray_left, gray_right, origin = _adjust_view(before, after, mask, comp)
            adj_crop = os.path.join(layout["adjust"], "crop") if layout else adjust_crop_dir(dataset_root)
            m_path = os.path.join(adj_crop, f"{stem}__{index:03d}.jpg")
            v_path = m_path
            ensure_dir(os.path.dirname(v_path))
            save_jpg(v_path, view)
            verdict = ask_cd(client, view, locate_prompt, m_path)
            placed = []
            if verdict.get("source") == "vllm":
                placed = place_cd_points(
                    verdict.get("miss") or [],
                    gray_left.shape[1], gray_right.shape[1], gray_left.shape[0],
                    gray_left, gray_right,
                )[:1]
            if not placed:
                crops.append({
                    "index": index, "status": "empty" if verdict.get("source") == "vllm" else "failed",
                    "error": verdict.get("error"), "shapes": [], "label": "change",
                    "issue": item.get("issue") or "", "reason": item.get("reason") or "",
                    "model": m_path, "vis": v_path,
                })
                continue
            hit = placed[0]
            phase = hit["phase"]
            image = before if phase == "t1" else after
            full_h, full_w = image.shape[:2]
            local_w = gray_left.shape[1] if phase == "t1" else gray_right.shape[1]
            local_h = gray_left.shape[0]
            full_px = float(hit["cx"]) * local_w + origin[0]
            full_py = float(hit["cy"]) * local_h + origin[1]
            packed = pack_crops(
                dataset_root, f"{stem}__{index:03d}", image,
                [{
                    "label": "change",
                    "cx": full_px / float(full_w),
                    "cy": full_py / float(full_h),
                    "reason": hit.get("reason") or item.get("reason") or "",
                    "index": index,
                    "issue": item.get("issue") or "",
                }],
                CROP_SIDE,
                adj_crop,
            )
            crop = packed[0] if packed else {"crop_error": "没有裁图"}
            crop["index"] = index
            crop["phase"] = phase
            crop["issue"] = item.get("issue") or ""
            crop["anchor"] = [full_px, full_py]
            crop["model"] = m_path
            crop["vis"] = v_path
            crops.append(crop)
        jobs.append({"rec": rec, "stem": stem, "error": "", "crops": crops, "mask": mask})
    needs_sam = any(
        crop.get("crop") and not crop.get("crop_error") and crop.get("status") != "failed"
        for job in jobs for crop in job["crops"]
    )
    sam = None
    if needs_sam:
        from sam_client import TritonSAM
        sam = TritonSAM()
    if layout:
        out_dir = os.path.join(layout["adjust"], "jsons")
        mask_png_dir = os.path.join(layout["adjust"], "masks")
    else:
        out_dir = qa_jsons_dir(dataset_root, ADJUST_SLUG)
        mask_png_dir = os.path.join(task_draft(dataset_root, ADJUST_SLUG), "masks")
    ensure_dir(out_dir)
    totals = {"filled": 0, "dropped": 0, "empty": 0, "failed": 0}
    for job in jobs:
        rec, stem = job["rec"], job["stem"]
        items = []
        kept_shapes = []
        if job.get("error"):
            items.append({
                "status": "failed", "error": job["error"], "shapes": [], "label": "change",
            })
        else:
            for crop in job["crops"]:
                if crop.get("status") in {"failed", "empty"} and not crop.get("crop"):
                    items.append(crop)
                    continue
                if crop.get("crop_error") or not crop.get("crop"):
                    items.append({
                        "index": crop.get("index"), "label": "change", "phase": crop.get("phase") or "",
                        "issue": crop.get("issue") or "", "status": "failed",
                        "error": crop.get("crop_error") or "没有裁图", "shapes": [],
                    })
                    continue
                row = fill_one(crop, [], "off", "sam", "mask", None, None, sam)
                anchor = crop.get("anchor") or crop.get("point") or []
                if len(anchor) >= 2:
                    row = _keep_point_shapes(row, anchor[0], anchor[1])
                row["index"] = crop.get("index")
                row["phase"] = crop.get("phase") or ""
                row["issue"] = crop.get("issue") or ""
                row["model"] = crop.get("model") or ""
                row["vis"] = crop.get("vis") or ""
                items.append(row)
                kept_shapes.extend(row.get("shapes") or [])
        stats = count_status(items)
        for key in totals:
            totals[key] += stats[key]
        mask_out = ""
        mask = job.get("mask")
        if kept_shapes is not None and kept_shapes and mask is not None:
            mask_out = write_mask_png(
                os.path.join(mask_png_dir, f"{stem}.png"), mask.shape[:2], kept_shapes,
            )
        write_json(os.path.join(out_dir, f"{stem}.json"), {
            "stem": stem,
            "pair": True,
            "before": rec.get("before") or "",
            "image": rec.get("image") or "",
            "mask": rec.get("mask") or "",
            "prompt": task,
            "shape": "mask",
            "locate": "off",
            "refine": "sam",
            "model": model_name,
            "mask_out": mask_out,
            "n": len(items),
            "items": items,
        })
    print(
        f"opt-adjust change locate=off refine=sam filled={totals['filled']} "
        f"dropped={totals['dropped']} empty={totals['empty']} failed={totals['failed']} → {out_dir}"
    )
    return totals


def parse_args():
    p = argparse.ArgumentParser(description="用定档 adjust 的框中心当报点，再走补标。--masks 走变化检测，不改原标注")
    p.add_argument("--dataset", required=True)
    p.add_argument("--shape", default="", help="mask 落 SAM 多边形；box 落掩膜的水平最小外接矩形。变化检测不用")
    p.add_argument("--masks", default="", help="非空则走变化检测：Qwen 报点加 Triton SAM，不走 GroundingPI")
    p.add_argument("--prompt", default="", help="用户确认过的定位句子。变化检测必填")
    p.add_argument("--prompt-file", default="", help="提示词文件。与 --prompt 二选一")
    p.add_argument("--locate", choices=LOCATE_CHOICES, default="gpi")
    p.add_argument("--refine", choices=REFINE_CHOICES, default="sam")
    p.add_argument("--weights", default="", help="SAM3 权重。空则用 tools/1-DataEngine/_weights/sam3.pt")
    p.add_argument("--device", default="0")
    p.add_argument("--base_url", default="", help="GroundingPI 地址。空则读 vllm_server.json")
    p.add_argument("--model", default="")
    p.add_argument("--timeout", type=int, default=600)
    p.add_argument("--limit", type=int, default=None)
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    if args.masks:
        run_adjust_change(
            args.dataset,
            prompt=args.prompt,
            prompt_file=args.prompt_file,
            limit=args.limit,
            timeout=args.timeout,
            base_url=args.base_url,
            model=args.model,
            masks=args.masks,
        )
    else:
        if args.shape not in SHAPE_CHOICES:
            raise SystemExit(f"先确认落盘形状：--shape {'/'.join(SHAPE_CHOICES)}")
        run_adjust(
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
        )
