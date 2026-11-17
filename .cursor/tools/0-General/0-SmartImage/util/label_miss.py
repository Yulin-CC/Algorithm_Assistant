"""
# @Author: Yullin
# @Date: 2026-11-11
# @Description: 整图把已有目标盖成灰色掩膜，再报漏检中心并裁 640。不调用定位模型。矩形默认用 Triton SAM 收成掩膜，--sam off 时直接涂整框。变化检测 --masks 按确认过的提示词在两期图上报点。
# @Command: python util/label_miss.py --dataset /path --jsons json
# @Command: python util/label_miss.py --dataset /path --jsons json --sam off
# @Command: python util/label_miss.py --dataset /path --masks label --prompt "新建或拆除的建筑"
"""

from __future__ import annotations

import argparse
import math
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

_PKG_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
_REPO = os.path.normpath(os.path.join(_PKG_ROOT, "..", "..", ".."))
_MODEL_UTIL = os.path.join(_REPO, "model", "util")
if _MODEL_UTIL not in sys.path:
    sys.path.insert(0, _MODEL_UTIL)

from tqdm import tqdm

tqdm.monitor_interval = 0

import cv2
import numpy as np

from common import ensure_dir, load_json, resolve_images_dir, task_draft, write_json
from describe import _make_client
from overlay import (
    cover_gray,
    model_dir,
    shape_kind,
    shape_xyxy,
    model_name_for,
    qa_jsons_dir,
    resolve_image,
    resolve_jsons_dir,
    save_jpg,
    vis_dir,
    write_qwen_view,
)
from vllm_client import extract_json_object

MISS_SLUG = "miss"
CROP_SIDE = 640
COVER_GRAY = (144, 144, 144)
COVER_PAD = 4
POINT_PAD = 160
MAX_CROP_SIDE = 1280
SYSTEM_MISS = "只输出一个 JSON 对象，不要 markdown。"
_SAM_LOCK = threading.Lock()


def crop_dir(dataset_root: str) -> str:
    return os.path.join(task_draft(dataset_root, MISS_SLUG), "crop")


def crop_window(bgr, cx, cy, side=CROP_SIDE):
    """以漏检中心裁正方形。cx、cy 为 0 到 1 时按整图比例。贴边时窗口内移，点仍留在裁图里。"""
    h, w = bgr.shape[:2]
    px = float(cx) * w if float(cx) <= 1.0 else float(cx)
    py = float(cy) * h if float(cy) <= 1.0 else float(cy)
    side = max(1, int(side))
    x0 = int(round(px - side / 2.0))
    y0 = int(round(py - side / 2.0))
    x0 = max(0, min(x0, max(0, w - side)))
    y0 = max(0, min(y0, max(0, h - side)))
    x1 = min(w, x0 + side)
    y1 = min(h, y0 + side)
    return bgr[y0:y1, x0:x1].copy(), [x0, y0, x1, y1], [px, py]


def rect_polygon(shape) -> dict:
    """矩形的两个角点展开成四边形，供 cover_gray 涂整框。"""
    xyxy = shape_xyxy(shape)
    if not xyxy:
        return {}
    x0, y0, x1, y1 = xyxy
    return {
        "label": shape.get("label") or "",
        "points": [[x0, y0], [x1, y0], [x1, y1], [x0, y1]],
        "shape_type": "polygon",
        "group_id": shape.get("group_id"),
        "flags": shape.get("flags") or {},
    }


def gray_shapes(image_path, shapes, use_sam=True) -> list:
    """多边形直接当掩膜。矩形默认用 Triton SAM 收成掩膜，不把整框涂灰。use_sam 关闭时涂整框。"""
    polys, boxes = [], []
    for shape in shapes or []:
        if shape_kind(shape) == "polygon":
            polys.append(shape)
        else:
            boxes.append(shape)
    if not boxes:
        return polys
    if not use_sam:
        for shape in boxes:
            poly = rect_polygon(shape)
            if poly:
                polys.append(poly)
        return polys
    from sam_client import TritonSAM, mask_to_polygon

    with _SAM_LOCK:
        sam = TritonSAM()
        encoded = sam.encode_file(image_path)
        missed = 0
        for shape in boxes:
            xyxy = shape_xyxy(shape)
            poly = None
            if xyxy:
                poly = mask_to_polygon(sam.decode_box(encoded, xyxy))
            if not poly:
                missed += 1
                continue
            polys.append({
                "label": shape.get("label") or "",
                "points": poly,
                "shape_type": "polygon",
                "group_id": shape.get("group_id"),
                "flags": shape.get("flags") or {},
            })
    if missed:
        print(f"sam 未出掩膜 {missed}，这些框没有涂灰")
    return polys


def on_gray(drawn, cx, cy) -> bool:
    h, w = drawn.shape[:2]
    px = int(round(float(cx) * w))
    py = int(round(float(cy) * h))
    px = min(max(px, 0), w - 1)
    py = min(max(py, 0), h - 1)
    pix = drawn[py, px]
    return bool(np.all(pix == np.array(COVER_GRAY, dtype=pix.dtype)))


def keep_open_points(drawn, miss) -> list:
    """灰色掩膜上的点丢掉，避免落在已经标过的目标里。"""
    return [item for item in miss or [] if not on_gray(drawn, item.get("cx"), item.get("cy"))]


def _find(parent, i):
    while parent[i] != i:
        parent[i] = parent[parent[i]]
        i = parent[i]
    return i


def cluster_indexes(pts, link) -> list:
    """窗口会叠在一起的点并成一簇。link 是像素距离。"""
    n = len(pts)
    parent = list(range(n))
    limit = float(link) * float(link)
    for i in range(n):
        for j in range(i + 1, n):
            dx = pts[i][0] - pts[j][0]
            dy = pts[i][1] - pts[j][1]
            if dx * dx + dy * dy > limit:
                continue
            pi, pj = _find(parent, i), _find(parent, j)
            if pi != pj:
                parent[pj] = pi
    groups = {}
    for i in range(n):
        groups.setdefault(_find(parent, i), []).append(i)
    return list(groups.values())


def _shift_inside(x0, y0, x1, y1, width, height):
    bw, bh = x1 - x0, y1 - y0
    if bw >= width:
        x0, x1 = 0.0, float(width)
    else:
        if x0 < 0:
            x1 -= x0
            x0 = 0.0
        if x1 > width:
            x0 -= x1 - width
            x1 = float(width)
    if bh >= height:
        y0, y1 = 0.0, float(height)
    else:
        if y0 < 0:
            y1 -= y0
            y0 = 0.0
        if y1 > height:
            y0 -= y1 - height
            y1 = float(height)
    return x0, y0, x1, y1


def _margin_ok(window, pts, pad, width, height) -> bool:
    """点到裁图边要留出车身。贴着图像边缘时留不出，允许。"""
    x0, y0, x1, y1 = window
    for px, py in pts:
        if not (x0 <= px <= x1 and y0 <= py <= y1):
            return False
        slack = 1
        if px - x0 < pad - slack and x0 > 0:
            return False
        if x1 - px < pad - slack and x1 < width:
            return False
        if py - y0 < pad - slack and y0 > 0:
            return False
        if y1 - py < pad - slack and y1 < height:
            return False
    return True


def _square(pts, width, height, side) -> list:
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    cx = (min(xs) + max(xs)) / 2.0
    cy = (min(ys) + max(ys)) / 2.0
    half = float(side) / 2.0
    x0, y0, x1, y1 = _shift_inside(cx - half, cy - half, cx + half, cy + half, width, height)
    return [int(round(x0)), int(round(y0)), int(round(x1)), int(round(y1))]


def windows_for_points(pts, width, height, side, pad=POINT_PAD, max_side=MAX_CROP_SIDE) -> list:
    """一簇点在不切到车身时合成一张，不够就放大。放大超过上限，或贴边仍会切到，就拆开。"""
    if not pts:
        return []
    side = max(1, int(side))
    pad = max(0, int(pad))
    max_side = max(side, int(max_side))
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    need = max(max(xs) - min(xs), max(ys) - min(ys)) + pad * 2
    crop_side = max(side, int(math.ceil(need)))
    if len(pts) == 1 or crop_side <= max_side:
        window = _square(pts, width, height, min(crop_side, max_side) if len(pts) > 1 else side)
        if len(pts) == 1 or _margin_ok(window, pts, pad, width, height):
            return [window]
    ordered = sorted(pts, key=lambda p: p[0] if max(xs) - min(xs) >= max(ys) - min(ys) else p[1])
    mid = max(1, len(ordered) // 2)
    return (
        windows_for_points(ordered[:mid], width, height, side, pad, max_side)
        + windows_for_points(ordered[mid:], width, height, side, pad, max_side)
    )


def clear_stem_crops(folder, stem) -> None:
    for path in Path(folder).glob(f"{stem}__*.jpg"):
        path.unlink()


def pack_crops(dataset_root: str, stem: str, bgr, miss, side=CROP_SIDE, folder=None) -> list:
    """邻近点并成一张裁图。旧的同名裁图先清掉。"""
    folder = folder or crop_dir(dataset_root)
    ensure_dir(folder)
    clear_stem_crops(folder, stem)
    h, w = bgr.shape[:2]
    located = []
    for item in miss or []:
        located.append((float(item["cx"]) * w, float(item["cy"]) * h, item))
    rows = []
    groups = cluster_indexes([(px, py) for px, py, _item in located], side)
    tiles = []
    for idxs in groups:
        members = [located[i] for i in idxs]
        for window in windows_for_points([(m[0], m[1]) for m in members], w, h, side):
            x0, y0, x1, y1 = window
            inside = [m for m in members if x0 <= m[0] <= x1 and y0 <= m[1] <= y1]
            if inside:
                tiles.append((window, inside))
    for i, (window, inside) in enumerate(tiles):
        x0, y0, x1, y1 = window
        path = os.path.join(folder, f"{stem}__{i:03d}.jpg")
        try:
            save_jpg(path, bgr[y0:y1, x0:x1].copy())
        except Exception as e:
            rows.append({
                "label": inside[0][2].get("label") or "",
                "window": [],
                "point": [],
                "crop": "",
                "crop_error": str(e),
                "n_points": len(inside),
            })
            continue
        labels, reasons, points = [], [], []
        for px, py, item in inside:
            label = str(item.get("label") or "")
            if label and label not in labels:
                labels.append(label)
            reason = str(item.get("reason") or "")
            if reason and reason not in reasons:
                reasons.append(reason)
            points.append({
                "label": label,
                "cx": item.get("cx"),
                "cy": item.get("cy"),
                "reason": reason,
                "index": item.get("index"),
                "issue": item.get("issue") or "",
            })
        px = sum(p[0] for p in inside) / len(inside)
        py = sum(p[1] for p in inside) / len(inside)
        rows.append({
            "label": labels[0] if len(labels) == 1 else ",".join(labels),
            "cx": px / w,
            "cy": py / h,
            "reason": "；".join(reasons),
            "n_points": len(inside),
            "points": points,
            "window": [x0, y0, x1, y1],
            "point": [px, py],
            "crop": path,
        })
    return rows


def miss_prompt(labels) -> str:
    names = "、".join(labels)
    return (
        f"图上灰色区域是已经标过的掩膜，属于这些类别：{names}。"
        "灰色不是目标的颜色。不要把灰色区域当成框。"
        "不要在灰色区域里落点。"
        "只找这些类别里、完全没有被灰色罩住的目标。"
        "已经罩住一部分的不要报。"
        "没有漏检就返回 {\"miss\":[]}。"
        "有漏检时，每个目标只给一个大致中心。cx、cy 是相对整张图宽和高的 0 到 1，不要给最终的框。"
        "reason 只写这张图里看到的事实。"
        "只返回一个 JSON："
        '{"miss":[{"label":"类别","cx":0.5,"cy":0.4,"reason":"..."}]}。'
    )


def class_names(shapes, extra="") -> list:
    names = []
    for shape in shapes or []:
        label = str(shape.get("label") or "").strip()
        if label and label not in names:
            names.append(label)
    for label in str(extra or "").replace("，", ",").split(","):
        label = label.strip()
        if label and label not in names:
            names.append(label)
    return names


def parse_miss(raw) -> dict:
    try:
        data = extract_json_object(raw)
    except Exception as e:
        return {"source": "failed", "error": f"parse_fail:{e}", "miss": []}
    rows = data.get("miss") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return {"source": "failed", "error": "parse_fail:miss", "miss": []}
    miss = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            cx = float(row.get("cx"))
            cy = float(row.get("cy"))
        except (TypeError, ValueError):
            continue
        if not (0.0 <= cx <= 1.0 and 0.0 <= cy <= 1.0):
            continue
        label = str(row.get("label") or "").strip()
        if not label:
            continue
        miss.append({
            "label": label,
            "cx": cx,
            "cy": cy,
            "reason": str(row.get("reason") or ""),
        })
    return {"source": "vllm", "error": None, "miss": miss}


def ask_miss(client, drawn, labels, model_path: str) -> dict:
    write_qwen_view(drawn, path=model_path)
    try:
        raw = client.describe_image(
            model_path, miss_prompt(labels), system=SYSTEM_MISS, max_tokens=512, temperature=0,
        )
    except Exception as e:
        return {"source": "failed", "error": str(e), "miss": []}
    return parse_miss(raw)


def collect_jobs(dataset_root, jsons_dir, images_dir, limit, force, labels):
    files = sorted(Path(jsons_dir).glob("*.json"))
    if limit:
        files = files[: int(limit)]
    jobs = []
    skipped = 0
    out_dir = qa_jsons_dir(dataset_root, MISS_SLUG)
    for jp in files:
        out_p = os.path.join(out_dir, f"{jp.stem}.json")
        existing = load_json(out_p) if os.path.isfile(out_p) else None
        if not force and existing and existing.get("source") not in {"failed", "placeholder"}:
            skipped += 1
            continue
        data = load_json(str(jp), default={}) or {}
        shapes = data.get("shapes") if isinstance(data.get("shapes"), list) else []
        try:
            image_abs = resolve_image(dataset_root, str(jp), data, images_dir)
            error = None
        except FileNotFoundError as e:
            image_abs = ""
            error = str(e)
        jobs.append({
            "stem": jp.stem,
            "json_path": str(jp),
            "out_p": out_p,
            "shapes": shapes,
            "labels": class_names(shapes, labels),
            "image_abs": image_abs,
            "error": error,
        })
    return jobs, skipped


def run_job(client, dataset_root, job, side=CROP_SIDE, use_sam=True) -> dict:
    stem = job["stem"]
    if job.get("error"):
        rec = {
            "stem": stem, "source": "failed", "error": job["error"],
            "n": 0, "miss": [], "json": job["json_path"],
        }
        write_json(job["out_p"], rec)
        return rec
    if not job["labels"]:
        rec = {
            "stem": stem, "image": job["image_abs"], "json": job["json_path"],
            "source": "empty", "error": None, "n": 0, "miss": [],
        }
        write_json(job["out_p"], rec)
        return rec
    bgr = read_bgr(job["image_abs"])
    if bgr is None:
        rec = {
            "stem": stem, "source": "failed", "error": "读图失败",
            "n": 0, "miss": [], "json": job["json_path"], "image": job["image_abs"],
        }
        write_json(job["out_p"], rec)
        return rec
    drawn = cover_gray(
        bgr, gray_shapes(job["image_abs"], job["shapes"], use_sam=use_sam), COVER_GRAY, COVER_PAD,
    )
    m_path = os.path.join(model_dir(dataset_root, MISS_SLUG), model_name_for(stem, None))
    v_path = os.path.join(vis_dir(dataset_root, MISS_SLUG), f"{stem}.jpg")
    save_jpg(v_path, drawn)
    verdict = ask_miss(client, drawn, job["labels"], m_path)
    raw = verdict.get("miss") or []
    if verdict.get("source") == "vllm" and raw:
        raw = keep_open_points(drawn, raw)
    miss = pack_crops(dataset_root, stem, drawn, raw, side) if raw else []
    rec = {
        "stem": stem,
        "image": job["image_abs"],
        "json": job["json_path"],
        "labels": job["labels"],
        "model": m_path,
        "vis": v_path,
        "n": len(miss),
        "n_points": len(raw),
        "source": verdict.get("source"),
        "error": verdict.get("error"),
        "miss": miss,
    }
    write_json(job["out_p"], rec)
    return rec


def read_bgr(path: str):
    data = np.fromfile(path, dtype=np.uint8)
    if data.size == 0:
        return None
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


def run_miss(dataset_root, jsons="json", limit=None, force=False, workers=2,
             timeout=600, base_url="", model="", labels="", side=CROP_SIDE, use_sam=True):
    """每张图问一次。有漏检就裁正方形，默认边长 640。"""
    jsons_dir = resolve_jsons_dir(dataset_root, jsons)
    if not os.path.isdir(jsons_dir):
        raise SystemExit(f"找不到标注目录: {jsons_dir}")
    images_dir = resolve_images_dir(dataset_root)
    jobs, skipped = collect_jobs(dataset_root, jsons_dir, images_dir, limit, force, labels)
    ensure_dir(qa_jsons_dir(dataset_root, MISS_SLUG))
    ensure_dir(model_dir(dataset_root, MISS_SLUG))
    ensure_dir(vis_dir(dataset_root, MISS_SLUG))
    ensure_dir(crop_dir(dataset_root))
    if not jobs:
        print(f"label-miss 无需定位 skip={skipped}")
        return {"skip": skipped, "n": 0, "images": 0, "fail": 0}
    client, model_name = _make_client(base_url, model, timeout)
    sam_name = "on" if use_sam else "off"
    print(f"label-miss jobs={len(jobs)} skip={skipped} model={model_name} sam={sam_name}")
    stats = {"n": 0, "points": 0, "images": 0, "fail": 0, "empty": 0}
    with ThreadPoolExecutor(max_workers=max(1, int(workers))) as pool:
        futs = [pool.submit(run_job, client, dataset_root, job, side, use_sam) for job in jobs]
        for fut in tqdm(as_completed(futs), total=len(futs), desc="label-miss"):
            rec = fut.result()
            stats["images"] += 1
            stats["n"] += int(rec.get("n") or 0)
            stats["points"] += int(rec.get("n_points") or 0)
            if rec.get("source") == "failed":
                stats["fail"] += 1
            if rec.get("source") == "empty":
                stats["empty"] += 1
    print(
        f"label-miss 完成 images={stats['images']} crops={stats['n']} points={stats['points']} "
        f"fail={stats['fail']} empty={stats['empty']} skip={skipped}"
    )
    return {**stats, "skip": skipped, "model": model_name}


def parse_cd_points(raw) -> dict:
    try:
        data = extract_json_object(raw)
    except Exception as e:
        return {"source": "failed", "error": f"parse_fail:{e}", "miss": []}
    rows = data.get("miss") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return {"source": "failed", "error": "parse_fail:miss", "miss": []}
    miss = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            cx = float(row.get("cx"))
            cy = float(row.get("cy"))
        except (TypeError, ValueError):
            continue
        if not (0.0 <= cx <= 1.0 and 0.0 <= cy <= 1.0):
            continue
        label = str(row.get("label") or "change").strip() or "change"
        miss.append({
            "label": label,
            "cx": cx,
            "cy": cy,
            "reason": str(row.get("reason") or ""),
        })
    return {"source": "vllm", "error": None, "miss": miss}


def ask_cd(client, bgr, prompt: str, model_path: str) -> dict:
    write_qwen_view(bgr, path=model_path)
    try:
        raw = client.describe_image(
            model_path, prompt, system=SYSTEM_MISS, max_tokens=512, temperature=0,
        )
    except Exception as e:
        return {"source": "failed", "error": str(e), "miss": []}
    return parse_cd_points(raw)


def place_cd_points(points, left_w, right_w, height, gray_left, gray_right) -> list:
    from cd_pair import map_stitch_point, point_is_gray

    placed = []
    for item in points or []:
        mapped = map_stitch_point(item.get("cx"), item.get("cy"), left_w, right_w, height)
        if not mapped:
            continue
        phase, px, py = mapped
        gray = gray_left if phase == "t1" else gray_right
        if point_is_gray(gray, px, py):
            continue
        h, w = gray.shape[:2]
        if w <= 0 or h <= 0 or px < 0 or py < 0 or px >= w or py >= h:
            continue
        placed.append({
            "label": item.get("label") or "change",
            "reason": item.get("reason") or "",
            "phase": phase,
            "cx": float(px) / float(w),
            "cy": float(py) / float(h),
        })
    return placed


def _pack_phases(dataset_root, stem, before, after, placed, side) -> list:
    rows = []
    for phase, image in (("t1", before), ("t2", after)):
        group = [item for item in placed if item.get("phase") == phase]
        if not group:
            continue
        packed = pack_crops(dataset_root, f"{stem}__{phase}", image, group, side)
        for row in packed:
            row["phase"] = phase
        rows.extend(packed)
    return rows


def run_cd_job(client, dataset_root, job, prompt, side) -> dict:
    from cd_pair import paint_gray, read_bgr, read_mask, stitch

    stem = job["stem"]
    base = {
        "stem": stem, "pair": True, "before": job["before"], "image": job["after"],
        "mask": job["mask"], "prompt": prompt, "n": 0, "miss": [],
    }
    if job.get("error"):
        base.update({"source": "failed", "error": job["error"]})
        write_json(job["out_p"], base)
        return base
    try:
        before = read_bgr(job["before"])
        after = read_bgr(job["after"])
        mask = read_mask(job["mask"])
        if before.shape[:2] != after.shape[:2] or before.shape[:2] != mask.shape[:2]:
            raise ValueError("A/B/掩膜尺寸不一致")
    except Exception as e:
        base.update({"source": "failed", "error": str(e)})
        write_json(job["out_p"], base)
        return base
    gray_left = paint_gray(before, mask)
    gray_right = paint_gray(after, mask)
    view = stitch(gray_left, gray_right)
    m_path = os.path.join(model_dir(dataset_root, MISS_SLUG), model_name_for(stem, None))
    v_path = os.path.join(vis_dir(dataset_root, MISS_SLUG), f"{stem}.jpg")
    save_jpg(v_path, view)
    verdict = ask_cd(client, view, prompt, m_path)
    placed = []
    if verdict.get("source") == "vllm":
        placed = place_cd_points(
            verdict.get("miss") or [],
            gray_left.shape[1], gray_right.shape[1], gray_left.shape[0],
            gray_left, gray_right,
        )
    miss = _pack_phases(dataset_root, stem, before, after, placed, side) if placed else []
    base.update({
        "model": m_path,
        "vis": v_path,
        "n": len(miss),
        "n_points": len(placed),
        "source": verdict.get("source"),
        "error": verdict.get("error"),
        "miss": miss,
    })
    write_json(job["out_p"], base)
    return base


def run_miss_change(dataset_root, masks="label", prompt="", prompt_file="", limit=None,
                    force=False, workers=2, timeout=600, base_url="", model="", side=CROP_SIDE):
    """两期图上按用户确认的句子报漏检点，并裁选中时相的原图。不走 GroundingPI。"""
    from cd_pair import cd_locate_prompt, list_pairs, pair_roots, require_task

    task = require_task(prompt, prompt_file)
    locate_prompt = cd_locate_prompt(task, "miss")
    before_dir, after_dir = pair_roots(dataset_root)
    if not before_dir:
        raise SystemExit(f"变化检测需要对齐的 A/ 与 B/: {dataset_root}")
    mask_dir = resolve_jsons_dir(dataset_root, masks)
    if not os.path.isdir(mask_dir):
        raise SystemExit(f"找不到掩膜目录: {mask_dir}")
    pairs = {stem: (before, after) for stem, before, after in list_pairs(before_dir, after_dir)}
    files = sorted(
        p for p in Path(mask_dir).iterdir()
        if p.is_file() and p.suffix.lower() in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}
    )
    if limit:
        files = files[: int(limit)]
    out_dir = qa_jsons_dir(dataset_root, MISS_SLUG)
    ensure_dir(out_dir)
    ensure_dir(model_dir(dataset_root, MISS_SLUG))
    ensure_dir(vis_dir(dataset_root, MISS_SLUG))
    ensure_dir(crop_dir(dataset_root))
    jobs, skipped = [], 0
    for path in files:
        out_p = os.path.join(out_dir, f"{path.stem}.json")
        existing = load_json(out_p) if os.path.isfile(out_p) else None
        if not force and existing and existing.get("source") not in {"failed", "placeholder"}:
            skipped += 1
            continue
        pair = pairs.get(path.stem)
        jobs.append({
            "stem": path.stem,
            "before": pair[0] if pair else "",
            "after": pair[1] if pair else "",
            "mask": str(path),
            "out_p": out_p,
            "error": "" if pair else "A/B 没有同名图",
        })
    if not jobs:
        print(f"label-miss 变化检测无需定位 skip={skipped}")
        return {"skip": skipped, "n": 0, "images": 0, "fail": 0}
    client, model_name = _make_client(base_url, model, timeout)
    print(f"label-miss change jobs={len(jobs)} skip={skipped} model={model_name}")
    stats = {"n": 0, "points": 0, "images": 0, "fail": 0, "empty": 0}
    with ThreadPoolExecutor(max_workers=max(1, int(workers))) as pool:
        futs = [
            pool.submit(run_cd_job, client, dataset_root, job, locate_prompt, side)
            for job in jobs
        ]
        for fut in tqdm(as_completed(futs), total=len(futs), desc="label-miss-cd"):
            rec = fut.result()
            stats["images"] += 1
            stats["n"] += int(rec.get("n") or 0)
            stats["points"] += int(rec.get("n_points") or 0)
            if rec.get("source") == "failed":
                stats["fail"] += 1
            if rec.get("source") == "empty":
                stats["empty"] += 1
    print(
        f"label-miss change 完成 images={stats['images']} crops={stats['n']} "
        f"points={stats['points']} fail={stats['fail']} empty={stats['empty']} skip={skipped}"
    )
    return {**stats, "skip": skipped, "model": model_name}


def parse_args():
    p = argparse.ArgumentParser(description="逐图定位漏检中心并裁图，不调用定位模型")
    p.add_argument("--dataset", required=True)
    p.add_argument("--jsons", default="json")
    p.add_argument("--masks", default="", help="变化掩膜目录（png，与 A/B 同名）。给出后走两期漏检")
    p.add_argument("--prompt", default="", help="用户确认过的定位句子。变化检测必填")
    p.add_argument("--prompt-file", default="", help="提示词文件。与 --prompt 二选一")
    p.add_argument("--labels", default="", help="额外类别，逗号分隔。图上没有框时用它")
    p.add_argument("--side", type=int, default=CROP_SIDE)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--force", action="store_true")
    p.add_argument("--workers", type=int, default=2)
    p.add_argument("--timeout", type=int, default=600)
    p.add_argument("--base_url", default="")
    p.add_argument("--model", default="")
    p.add_argument("--sam", choices=("on", "off"), default="on",
                   help="矩形涂灰前是否用 Triton SAM 收成掩膜。off 时直接涂整框")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    if args.masks:
        run_miss_change(
            args.dataset,
            masks=args.masks,
            prompt=args.prompt,
            prompt_file=args.prompt_file,
            limit=args.limit,
            force=args.force,
            workers=args.workers,
            timeout=args.timeout,
            base_url=args.base_url,
            model=args.model,
            side=args.side,
        )
    else:
        run_miss(
            args.dataset,
            jsons=args.jsons,
            limit=args.limit,
            force=args.force,
            workers=args.workers,
            timeout=args.timeout,
            base_url=args.base_url,
            model=args.model,
            labels=args.labels,
            side=args.side,
            use_sam=args.sam != "off",
        )
