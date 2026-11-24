"""
# @Author: Yullin
# @Date: 2026-11-11
# @Description: 把已有框或掩膜叠到原图上，写出裁图和整图。不调用模型。
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

_PKG_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
_REPO = os.path.normpath(os.path.join(_PKG_ROOT, "..", "..", ".."))
_MODEL_UTIL = os.path.join(_REPO, "server", "util")
if _MODEL_UTIL not in sys.path:
    sys.path.insert(0, _MODEL_UTIL)

import cv2
import numpy as np

from common import ensure_dir, task_model, task_result, task_vis

TASK_SLUG = "overlay"
QWEN_MAX_SIDE = 1280
CROP_SCALE = 2.5
MIN_CROP_SIDE = 512
HINT_THICKNESS = 1
BOX_ALPHA = 0.18
MASK_ALPHA = 0.15
MASK_THICKNESS = 2
PALETTE = [
    (40, 180, 40), (40, 40, 220), (20, 180, 220),
    (180, 80, 220), (220, 140, 20), (80, 200, 200),
]
_COLOR_EN = {
    "black", "white", "red", "blue", "green", "yellow", "orange", "purple",
    "pink", "gray", "grey", "brown", "silver", "gold",
}
_COLOR_ZH = ("黑", "白", "红", "蓝", "绿", "黄", "橙", "紫", "粉", "灰", "棕", "银", "金")


def needs_true_color(label) -> bool:
    """类别名带颜色时，框内和掩膜内不能再铺色，否则会染掉目标本身的颜色。"""
    text = str(label or "").strip().lower()
    if not text:
        return False
    parts = []
    token = []
    for ch in text:
        if "a" <= ch <= "z" or "0" <= ch <= "9":
            token.append(ch)
        elif token:
            parts.append("".join(token))
            token = []
    if token:
        parts.append("".join(token))
    if any(part in _COLOR_EN for part in parts):
        return True
    return any(word in text for word in _COLOR_ZH)


def use_slug(slug=None) -> str:
    text = str(slug or "").strip()
    return text or TASK_SLUG


def _with_part(path: str, part=None) -> str:
    name = str(part or "").strip()
    return os.path.join(path, name) if name else path


def pkg_result(dataset_root: str, slug=None, part=None) -> str:
    return _with_part(task_result(dataset_root, use_slug(slug)), part)


def model_dir(dataset_root: str, slug=None, part=None) -> str:
    return _with_part(task_model(dataset_root, use_slug(slug)), part)


def vis_dir(dataset_root: str, slug=None, part=None) -> str:
    return _with_part(task_vis(dataset_root, use_slug(slug)), part)


def qa_jsons_dir(dataset_root: str, slug=None, part=None) -> str:
    return os.path.join(pkg_result(dataset_root, slug, part), "jsons")


def summary_path(dataset_root: str, slug=None, part=None) -> str:
    return os.path.join(pkg_result(dataset_root, slug, part), "summary.json")


def repro_version_dir(masks: str, dataset_root: str = "") -> str:
    """变化检测产物根：优先 `repro/<版本>`，否则 `bcd_map` 的上一级，再否则数据集根。不写 draft。"""
    raw = os.path.abspath(str(masks or "").strip())
    p = Path(raw) if raw else None
    if p and p.is_file():
        p = p.parent
    if p:
        if p.name in {"bcd_map", "bcd_map_cd"}:
            return str(p.parent)
        if (p / "bcd_map").is_dir():
            return str(p)
    root = os.path.abspath(str(dataset_root or "").strip())
    return root


def cd_layout(masks: str, dataset_root: str = ""):
    """变化检测：窗以 crop/vismask_crop 为准；Qwen 看同名 crop/analysis_crop。漏检补标调整在版本下 draft/。"""
    ver = repro_version_dir(masks, dataset_root)
    if not ver:
        return None
    analysis = os.path.join(ver, "analysis")
    crop_root = os.path.join(ver, "crop")
    return {
        "version": ver,
        "crop": os.path.join(crop_root, "analysis_crop"),
        "analysis_crop": os.path.join(crop_root, "analysis_crop"),
        "vismask_crop": os.path.join(crop_root, "vismask_crop"),
        "analysis": analysis,
        "jsons": os.path.join(analysis, "jsons"),
        "analysis_json": os.path.join(analysis, "analysis.json"),
        "to_check": os.path.join(ver, "to_check"),
        "miss": os.path.join(ver, "draft", "miss"),
        "fill": os.path.join(ver, "draft", "fill"),
        "adjust": os.path.join(ver, "draft", "adjust"),
    }


def crop_name_for(stem: str, index) -> str:
    return f"{stem}_{int(index) + 1:02d}.jpg"


def progress_path(dataset_root: str, slug=None, part=None) -> str:
    return pkg_draft_progress(dataset_root, slug, part)


def pkg_draft_progress(dataset_root: str, slug=None, part=None) -> str:
    name = str(part or "").strip()
    filename = f"progress-{name}.json" if name else "progress.json"
    return os.path.join(dataset_root, "draft", use_slug(slug), filename)


def resolve_jsons_dir(dataset_root: str, jsons: str) -> str:
    raw = (jsons or "").strip() or "jsons-det-pre"
    path = Path(raw)
    if not path.is_absolute():
        path = Path(dataset_root) / path
    return str(path.resolve())


def resolve_image(dataset_root: str, json_path: str, data: dict, images_dir: str) -> str:
    stem = Path(json_path).stem
    rel = str((data or {}).get("imagePath") or "").strip()
    if rel:
        cand = os.path.normpath(os.path.join(os.path.dirname(json_path), rel))
        if os.path.isfile(cand):
            return cand
    for ext in (".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"):
        cand = os.path.join(images_dir, stem + ext)
        if os.path.isfile(cand):
            return cand
    root_flat = os.path.join(dataset_root, stem)
    for ext in (".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"):
        cand = root_flat + ext
        if os.path.isfile(cand):
            return cand
    raise FileNotFoundError(f"找不到原图: {stem}")
def shape_xyxy(shape: dict):
    pts = shape.get("points") or []
    if not pts:
        return None
    xs = [float(p[0]) for p in pts]
    ys = [float(p[1]) for p in pts]
    if len(pts) == 2 and str(shape.get("shape_type") or "").lower() in {"", "rectangle"}:
        x0, y0 = xs[0], ys[0]
        x1, y1 = xs[1], ys[1]
        return [min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)]
    return [min(xs), min(ys), max(xs), max(ys)]


def shape_kind(shape: dict) -> str:
    st = str(shape.get("shape_type") or "").lower()
    pts = shape.get("points") or []
    if st == "polygon" and len(pts) >= 3:
        return "polygon"
    if st not in {"", "rectangle"} and len(pts) >= 3:
        return "polygon"
    return "rectangle"


def polygon_xy(shape: dict):
    pts = []
    for p in shape.get("points") or []:
        if isinstance(p, (list, tuple)) and len(p) >= 2:
            pts.append((float(p[0]), float(p[1])))
    return pts


def view_kind(shapes) -> str:
    kinds = {shape_kind(s) for s in shapes}
    if kinds == {"polygon"}:
        return "polygon"
    if "polygon" in kinds:
        return "mixed"
    return "rectangle"

def crop_with_margin(bgr, xyxy, scale=CROP_SCALE):
    h, w = bgr.shape[:2]
    x0, y0, x1, y1 = [float(v) for v in xyxy]
    bw = max(1.0, x1 - x0)
    bh = max(1.0, y1 - y0)
    cx = (x0 + x1) / 2.0
    cy = (y0 + y1) / 2.0
    half_w = bw * float(scale) / 2.0
    half_h = bh * float(scale) / 2.0
    nx0 = int(round(cx - half_w))
    ny0 = int(round(cy - half_h))
    nx1 = int(round(cx + half_w))
    ny1 = int(round(cy + half_h))
    nx0 = max(0, nx0)
    ny0 = max(0, ny0)
    nx1 = min(w, nx1)
    ny1 = min(h, ny1)
    if nx1 <= nx0 or ny1 <= ny0:
        raise ValueError("crop 为空")
    crop = bgr[ny0:ny1, nx0:nx1].copy()
    box = (x0 - nx0, y0 - ny0, x1 - nx0, y1 - ny0)
    return crop, box


def upscale_min_side(bgr, min_side=MIN_CROP_SIDE):
    h, w = bgr.shape[:2]
    if min(h, w) >= int(min_side):
        return bgr, 1.0
    scale = float(min_side) / float(min(h, w))
    out = cv2.resize(
        bgr,
        (int(round(w * scale)), int(round(h * scale))),
        interpolation=cv2.INTER_CUBIC,
    )
    return out, scale


def draw_thin_box(vis, xyxy, color, thickness=HINT_THICKNESS):
    x0, y0, x1, y1 = [int(round(v)) for v in xyxy]
    cv2.rectangle(vis, (x0, y0), (x1, y1), color, thickness, lineType=cv2.LINE_AA)
    return vis


def draw_model_box(vis, xyxy, color, fill=True):
    """发给模型的框。颜色类只描边，其余在内部铺淡色。"""
    x0, y0, x1, y1 = [int(round(v)) for v in xyxy]
    h, w = vis.shape[:2]
    x0, x1 = sorted((max(0, min(w - 1, x0)), max(0, min(w, x1))))
    y0, y1 = sorted((max(0, min(h - 1, y0)), max(0, min(h, y1))))
    if not fill or x1 - x0 < 2 or y1 - y0 < 2:
        return draw_thin_box(vis, xyxy, color)
    layer = vis.copy()
    cv2.rectangle(layer, (x0, y0), (x1, y1), color, thickness=-1)
    blended = cv2.addWeighted(layer, BOX_ALPHA, vis, 1.0 - BOX_ALPHA, 0)
    vis[:] = blended
    cv2.rectangle(vis, (x0, y0), (x1, y1), color, HINT_THICKNESS, lineType=cv2.LINE_AA)
    return vis


def draw_vis_box(vis, xyxy, color):
    """给人看的框：按图短边加粗，先描黑边再铺亮色。发给模型的图不用这个。"""
    h, w = vis.shape[:2]
    thick = max(4, int(round(min(h, w) / 280)))
    x0, y0, x1, y1 = [int(round(v)) for v in xyxy]
    cv2.rectangle(vis, (x0, y0), (x1, y1), (0, 0, 0), thick + thick // 2 + 2, lineType=cv2.LINE_AA)
    cv2.rectangle(vis, (x0, y0), (x1, y1), color, thick, lineType=cv2.LINE_AA)
    return vis


def cover_gray(bgr, shapes, color=(144, 144, 144), pad=4):
    """按多边形掩膜涂实心灰，不描边。矩形要先收成掩膜再进来。"""
    vis = bgr.copy()
    if vis.size == 0 or not shapes:
        return vis
    h, w = vis.shape[:2]
    mask = np.zeros((h, w), np.uint8)
    for shape in shapes:
        pts = _placed_pts(shape, (0.0, 0.0), 1.0)
        if len(pts) < 3:
            continue
        arr = np.round(np.asarray(pts, dtype=np.float32)).astype(np.int32)
        cv2.fillPoly(mask, [arr], 255)
    if not mask.any():
        return vis
    if pad > 0:
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (pad * 2 + 1, pad * 2 + 1))
        mask = cv2.dilate(mask, kernel)
    vis[mask > 0] = color
    return vis


def cover_mask(vis, pts, color, alpha=MASK_ALPHA):
    """只铺淡色掩膜，不描边。"""
    if len(pts) < 3:
        return vis
    arr = np.round(np.asarray(pts, dtype=np.float32)).astype(np.int32)
    layer = vis.copy()
    cv2.fillPoly(layer, [arr], color)
    blended = cv2.addWeighted(layer, float(alpha), vis, 1.0 - float(alpha), 0)
    vis[:] = blended
    return vis


def box_corners(xyxy):
    x0, y0, x1, y1 = [float(v) for v in xyxy]
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def draw_polygon_mask(vis, pts, color, alpha=MASK_ALPHA, fill=True):
    if len(pts) < 3:
        return vis
    arr = np.round(np.asarray(pts, dtype=np.float32)).astype(np.int32)
    if fill:
        layer = vis.copy()
        cv2.fillPoly(layer, [arr], color)
        blended = cv2.addWeighted(layer, float(alpha), vis, 1.0 - float(alpha), 0)
        vis[:] = blended
    cv2.polylines(vis, [arr], True, (20, 20, 20), MASK_THICKNESS + 2, lineType=cv2.LINE_AA)
    cv2.polylines(vis, [arr], True, color, MASK_THICKNESS, lineType=cv2.LINE_AA)
    return vis


def _placed_pts(shape, origin, scale):
    ox, oy = origin
    s = float(scale)
    if shape_kind(shape) == "polygon":
        return [((x - ox) * s, (y - oy) * s) for x, y in polygon_xy(shape)]
    xyxy = shape_xyxy(shape)
    if xyxy is None:
        return []
    box = (
        (xyxy[0] - ox) * s,
        (xyxy[1] - oy) * s,
        (xyxy[2] - ox) * s,
        (xyxy[3] - oy) * s,
    )
    return box_corners(box)


def render_shape(vis, shape, color, origin=(0.0, 0.0), scale=1.0, for_vis=False, fill=True, as_mask=False):
    if as_mask:
        pts = _placed_pts(shape, origin, scale)
        if len(pts) >= 3:
            return cover_mask(vis, pts, color)
        return vis
    ox, oy = origin
    s = float(scale)
    if shape_kind(shape) == "polygon":
        pts = [((x - ox) * s, (y - oy) * s) for x, y in polygon_xy(shape)]
        if len(pts) >= 3:
            return draw_polygon_mask(vis, pts, color, fill=fill)
    xyxy = shape_xyxy(shape)
    if xyxy is None:
        return vis
    box = (
        (xyxy[0] - ox) * s,
        (xyxy[1] - oy) * s,
        (xyxy[2] - ox) * s,
        (xyxy[3] - oy) * s,
    )
    if for_vis:
        return draw_vis_box(vis, box, color)
    return draw_model_box(vis, box, color, fill=fill)


def instance_crop_view(bgr, shape, color, fill=True) -> np.ndarray:
    xyxy = shape_xyxy(shape)
    if xyxy is None:
        raise ValueError("无框")
    crop, box = crop_with_margin(bgr, xyxy)
    vis, scale = upscale_min_side(crop)
    origin = (xyxy[0] - box[0], xyxy[1] - box[1])
    return render_shape(vis, shape, color, origin=origin, scale=scale, fill=fill)


def draw_shapes(bgr, shapes, highlight=None, as_mask=False) -> np.ndarray:
    vis = bgr.copy()
    items = list(shapes or [])
    if highlight is not None:
        if highlight < 0 or highlight >= len(items):
            return vis
        items = [items[highlight]]
        colors = [PALETTE[highlight % len(PALETTE)]]
    else:
        colors = [PALETTE[i % len(PALETTE)] for i in range(len(items))]
    for inst, color in zip(items, colors):
        if as_mask:
            render_shape(vis, inst, color, as_mask=True)
        else:
            render_shape(vis, inst, color, fill=not needs_true_color(inst.get("label")))
    return vis


def write_qwen_view(bgr, max_side=QWEN_MAX_SIDE, path="") -> str:
    if bgr is None or bgr.size == 0:
        raise ValueError("空图")
    h, w = bgr.shape[:2]
    if max(h, w) > max_side:
        scale = max_side / float(max(h, w))
        bgr = cv2.resize(
            bgr, (int(round(w * scale)), int(round(h * scale))),
            interpolation=cv2.INTER_AREA,
        )
    if not path:
        fd, path = tempfile.mkstemp(suffix=".jpg")
        os.close(fd)
    else:
        ensure_dir(os.path.dirname(path) or ".")
    ok, buf = cv2.imencode(".jpg", bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
    if not ok:
        raise RuntimeError("无法写叠图缩图")
    buf.tofile(path)
    return path


def save_jpg(path: str, bgr) -> None:
    ensure_dir(os.path.dirname(path) or ".")
    ok, buf = cv2.imencode(".jpg", bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
    if not ok:
        raise RuntimeError(f"无法写叠图: {path}")
    buf.tofile(path)
def model_name_for(stem: str, index) -> str:
    if index is None:
        return f"{stem}.jpg"
    return f"{stem}__{int(index):03d}.jpg"


def save_change_overview(before, after, comps, items, stem, v_dir) -> str:
    """两期整图按档位涂色后左右拼接。不调用模型。"""
    from cd_pair import paint_mask, stitch
    from label_grade import verdict_color

    left, right = before.copy(), after.copy()
    for comp, item in zip(comps, items):
        color = verdict_color(item)
        left = paint_mask(left, comp["mask"], color)
        right = paint_mask(right, comp["mask"], color)
    path = os.path.join(v_dir, f"{stem}.jpg")
    save_jpg(path, stitch(left, right))
    return path


def save_change_item_view(before, after, comp, item, stem, v_dir) -> str:
    """全景只画当前这一块连通域。给人审和按文件挪档用。"""
    from cd_pair import paint_mask, stitch
    from label_grade import verdict_color

    color = verdict_color(item)
    left = paint_mask(before.copy(), comp["mask"], color)
    right = paint_mask(after.copy(), comp["mask"], color)
    idx = item.get("index")
    path = os.path.join(v_dir, model_name_for(stem, idx))
    save_jpg(path, stitch(left, right))
    return path
