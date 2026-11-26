"""
# @Author: Yullin
# @Date: 2026-11-10
# @Description: 变化检测两期图左右拼接，以及二值掩膜连通域。左前右后。
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import cv2
import numpy as np

IMG_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
MIN_AREA = 32
STITCH_GAP = 8
# 连通域裁窗。发给 Qwen 的 overlay/model 用这个。3.5 仍偏紧，放到 4.5。
CROP_SCALE = 4.5
COVER_GRAY = (144, 144, 144)
_PROMPT_EMPTY = (
    "变化检测要先确认定位什么。把用户确认过的提示词传给 --prompt 或 --prompt-file。"
    "建筑变化、土地变化不要写死在脚本里。"
)

CD_DESCRIBE = (
    "左图是前时相，右图是后时相，两期已经对齐。"
    "用简洁中文说明看得见的变化：什么消失、什么新出现、什么明显改了。"
    "没有明显变化就直接说没有。2–6 句。不要编造看不清的细节。"
)

CD_MARK = (
    "两边同一位置有一条细线，圈出要判断的掩膜，内部只有很淡的着色。"
    "细线和淡色只是位置标记，不是地物。"
    "线的颜色、粗细和淡色填充都不是物体的颜色、材质或形状。"
    "不要因为线是红的，就把里面说成红色车辆或红色屋顶。"
    "看线里面原图的纹理和形状。"
    "图上没有文字，没有 T1、T2 或编号。"
)

CD_MASK = (
    "左图是前时相，右图是后时相，已经对齐。"
    + CD_MARK +
    "小连通域也要按地物判断，不要因为面积小就当噪声。"
    "判断这块在两期之间是不是真实变化，以及掩膜是否罩住变化范围。"
    "分两步。看不出变化（配准误差、季节、阴影、两期本来一样）：present=false，grade=wrong。"
    "能看出真实变化：present=true，不得给 wrong。"
    "是变化，掩膜内没变化的区域比变化本身还大：grade=adjust，issue=oversize。"
    "是变化，但有一大块真变化在掩膜外：grade=adjust，issue=incomplete。"
    "是变化，但掩膜明显错位：grade=adjust，issue=shifted。"
    "掩膜只比变化范围松或紧一圈：grade=fit，issue 为空。"
    "已经罩住变化不算贴合。过大、不完整、错位都不得打成 wrong。"
    '只返回 JSON：{"present":true,"grade":"fit","issue":"","reason":"..."}'
    ' 或 {"present":true,"grade":"adjust","issue":"oversize","reason":"..."}'
    ' 或 {"present":true,"grade":"adjust","issue":"incomplete","reason":"..."}'
    ' 或 {"present":true,"grade":"adjust","issue":"shifted","reason":"..."}'
    ' 或 {"present":false,"grade":"wrong","issue":"","reason":"..."}。'
)


def resolve_grade_prompt(prompt="", prompt_file="") -> str:
    """整段定档提示原样使用。短任务句再套上掩膜说明。"""
    text = require_task(prompt, prompt_file) if (prompt or prompt_file) else ""
    if "只返回 JSON" in text:
        return text
    return cd_grade_prompt(text)


def cd_grade_prompt(task: str = "") -> str:
    """定档提示。空则用 CD_MASK；有本单句子则只判该类变化。"""
    task = str(task or "").strip()
    if not task:
        return CD_MASK
    return (
        "左图是前时相，右图是后时相，已经对齐。"
        + CD_MARK +
        "小连通域也要按地物判断，不要因为面积小就当噪声。"
        f"本单只判断这类变化：{task}。"
        "分两步。看不出本单定义的变化"
        "（配准误差、季节、阴影、两期本来一样、"
        "只是外观或颜色变了但本单要的地物没变）：present=false，grade=wrong。"
        "能看出本单定义的变化：present=true，不得给 wrong。"
        "是本单定义的变化，掩膜内没变化的区域比变化本身还大：grade=adjust，issue=oversize。"
        "是本单定义的变化，但有一大块真变化在掩膜外：grade=adjust，issue=incomplete。"
        "是本单定义的变化，但掩膜明显错位：grade=adjust，issue=shifted。"
        "掩膜只比变化范围松或紧一圈：grade=fit，issue 为空。"
        "已经罩住变化不算贴合。过大、不完整、错位都不得打成 wrong。"
        '只返回 JSON：{"present":true,"grade":"fit","issue":"","reason":"..."}'
        ' 或 {"present":true,"grade":"adjust","issue":"oversize","reason":"..."}'
        ' 或 {"present":true,"grade":"adjust","issue":"incomplete","reason":"..."}'
        ' 或 {"present":true,"grade":"adjust","issue":"shifted","reason":"..."}'
        ' 或 {"present":false,"grade":"wrong","issue":"","reason":"..."}。'
    )


def read_bgr(path: str):
    data = np.fromfile(path, dtype=np.uint8)
    img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if img is None:
        raise FileNotFoundError(f"无法读图: {path}")
    return img


def locate_pair_file(path, dataset_root="") -> str:
    """原路径没有时，到数据集 A/B 以及上级 dsample/sample 里找同名（含挖掘前缀）。"""
    raw = str(path or "").strip()
    if raw and os.path.isfile(raw):
        return raw
    name = os.path.basename(raw)
    if not name:
        return ""
    side = Path(raw).parent.name if raw else ""
    if side.lower() not in {"a", "b"}:
        side = "A"
    roots = []
    if dataset_root:
        cur = Path(dataset_root)
        for _ in range(5):
            roots.append(cur)
            if cur.parent == cur:
                break
            cur = cur.parent
    for root in roots:
        direct = root / side / name
        if direct.is_file():
            return str(direct)
        for bucket in ("dsample", "sample"):
            folder = root / bucket / side
            if not folder.is_dir():
                continue
            exact = folder / name
            if exact.is_file():
                return str(exact)
            hits = list(folder.glob(f"*{name}"))
            if len(hits) == 1:
                return str(hits[0])
    return ""


def read_mask(path: str):
    data = np.fromfile(path, dtype=np.uint8)
    mask = cv2.imdecode(data, cv2.IMREAD_GRAYSCALE)
    if mask is None:
        raise FileNotFoundError(f"无法读掩膜: {path}")
    return mask


def child_dir(root: str, names) -> str:
    for name in names:
        path = os.path.join(root, name)
        if os.path.isdir(path):
            return path
    return ""


def pair_roots(dataset_root: str):
    before = child_dir(dataset_root, ("A", "a", "t1"))
    after = child_dir(dataset_root, ("B", "b", "t2"))
    if before and after:
        return before, after
    return "", ""


def list_pairs(before_dir: str, after_dir: str):
    after = {}
    for path in Path(after_dir).iterdir():
        if path.is_file() and path.suffix.lower() in IMG_EXTS:
            after[path.stem] = str(path)
    pairs = []
    for path in sorted(Path(before_dir).iterdir()):
        if path.is_file() and path.suffix.lower() in IMG_EXTS and path.stem in after:
            pairs.append((path.stem, str(path), after[path.stem]))
    return pairs


def stitch(left, right):
    if left.shape[0] != right.shape[0]:
        scale = left.shape[0] / float(right.shape[0])
        right = cv2.resize(
            right,
            (max(1, int(round(right.shape[1] * scale))), left.shape[0]),
            interpolation=cv2.INTER_AREA,
        )
    gap = np.full((left.shape[0], STITCH_GAP, 3), 255, np.uint8)
    return np.concatenate([left, gap, right], axis=1)


def write_view(bgr, path, max_side=1280, quality=85) -> str:
    h, w = bgr.shape[:2]
    if max(h, w) > max_side:
        scale = max_side / float(max(h, w))
        bgr = cv2.resize(
            bgr,
            (max(1, int(round(w * scale))), max(1, int(round(h * scale)))),
            interpolation=cv2.INTER_AREA,
        )
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    ok, buf = cv2.imencode(".jpg", bgr, [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)])
    if not ok:
        raise RuntimeError("无法写视图")
    buf.tofile(path)
    return path


def save_view(bgr, max_side=1280) -> str:
    fd, path = tempfile.mkstemp(suffix=".jpg")
    os.close(fd)
    return write_view(bgr, path, max_side=max_side)


def mask_components(mask, min_area=MIN_AREA):
    binary = (mask > 0).astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(binary, 8)
    found = []
    for idx in range(1, count):
        area = int(stats[idx, cv2.CC_STAT_AREA])
        if area < int(min_area):
            continue
        x = int(stats[idx, cv2.CC_STAT_LEFT])
        y = int(stats[idx, cv2.CC_STAT_TOP])
        w = int(stats[idx, cv2.CC_STAT_WIDTH])
        h = int(stats[idx, cv2.CC_STAT_HEIGHT])
        found.append({
            "xyxy": [x, y, x + w, y + h],
            "area": area,
            "mask": labels == idx,
        })
    return found


def crop_window(shape, xyxy, scale=CROP_SCALE):
    """外扩 scale 倍，按连通域长边裁正方形；贴边时往里挪，能方则方。"""
    h, w = shape[:2]
    x0, y0, x1, y1 = [float(v) for v in xyxy]
    bw = max(1.0, x1 - x0)
    bh = max(1.0, y1 - y0)
    side = max(bw, bh) * float(scale)
    cx = (x0 + x1) / 2.0
    cy = (y0 + y1) / 2.0
    nx0 = int(round(cx - side / 2.0))
    ny0 = int(round(cy - side / 2.0))
    side_i = max(1, int(round(side)))
    if nx0 < 0:
        nx0 = 0
    if ny0 < 0:
        ny0 = 0
    if nx0 + side_i > w:
        nx0 = max(0, w - side_i)
    if ny0 + side_i > h:
        ny0 = max(0, h - side_i)
    nx1 = min(w, nx0 + side_i)
    ny1 = min(h, ny0 + side_i)
    if nx1 <= nx0 or ny1 <= ny0:
        raise ValueError("crop 为空")
    return nx0, ny0, nx1, ny1


def paint_mask(bgr, mask_crop, color, alpha=0.15, edge=2, halo=4):
    """halo 是描边前的深色底。发给 Qwen 的图用 edge=1、halo=0，不再加粗。"""
    vis = bgr.copy()
    region = mask_crop.astype(bool)
    if not region.any():
        return vis
    layer = vis.copy()
    layer[region] = color
    blended = cv2.addWeighted(layer, float(alpha), vis, 1.0 - float(alpha), 0)
    vis[:] = blended
    if edge <= 0 and halo <= 0:
        return vis
    contours, _ = cv2.findContours(region.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if halo > 0:
        cv2.drawContours(vis, contours, -1, (20, 20, 20), int(halo), lineType=cv2.LINE_AA)
    if edge > 0:
        cv2.drawContours(vis, contours, -1, color, int(edge), lineType=cv2.LINE_AA)
    return vis


def pair_mask_view(before_bgr, after_bgr, comp, color):
    nx0, ny0, nx1, ny1 = crop_window(before_bgr.shape, comp["xyxy"])
    sl = (slice(ny0, ny1), slice(nx0, nx1))
    left = paint_mask(before_bgr[sl], comp["mask"][sl], color, edge=1, halo=0)
    right = paint_mask(after_bgr[sl], comp["mask"][sl], color, edge=1, halo=0)
    return stitch(left, right)


def pair_vismask_crop(before_bgr, after_bgr, mask, xyxy, color=(0, 0, 255), alpha=0.12, cc_mask=None):
    """与推理 analysis_crop 相同：只叠当前连通域，再按该块正方形裁、左右拼。"""
    region = cc_mask if cc_mask is not None else (mask > 0)
    left_full = paint_mask(before_bgr, region, color, alpha=alpha, edge=1, halo=0)
    right_full = paint_mask(after_bgr, region, color, alpha=alpha, edge=1, halo=0)
    nx0, ny0, nx1, ny1 = crop_window(before_bgr.shape, xyxy)
    sl = (slice(ny0, ny1), slice(nx0, nx1))
    return stitch(left_full[sl], right_full[sl])


def require_task(prompt="", prompt_file="") -> str:
    """用户确认过的定位句子。空则停，不替用户选建筑或土地。"""
    text = ""
    path = str(prompt_file or "").strip()
    if path:
        if not os.path.isfile(path):
            raise SystemExit(f"找不到提示词文件: {path}")
        with open(path, encoding="utf-8") as f:
            text = f.read().strip()
    if not text:
        text = str(prompt or "").strip()
    if not text:
        raise SystemExit(_PROMPT_EMPTY)
    return text


def cd_locate_prompt(task: str, kind: str = "miss") -> str:
    """固定规矩包住用户句子。kind=miss 报漏检，kind=adjust 只改当前这一块。"""
    task = str(task or "").strip()
    if not task:
        raise SystemExit(_PROMPT_EMPTY)
    if kind == "adjust":
        focus = (
            "细线和内部淡色只标出要改的这一块，颜色不是地物特征。"
            "只给一个点，点在这块真实变化的中心。"
            "没有符合本单的变化就返回 {\"miss\":[]}。"
        )
    else:
        focus = (
            "只报完全没被灰色罩住、且符合本单的变化。每个变化一个点。"
            "已经罩住一部分的不要报。"
            "没有漏检就返回 {\"miss\":[]}。"
        )
    return (
        "左图是前时相 T1，右图是后时相 T2，两期已经对齐。"
        f"本单只定位这类变化：{task}。"
        "灰色区域是已经标出的变化。不要在灰色上落点。灰色不是目标的颜色。"
        f"{focus}"
        "cx、cy 是相对这张拼图宽和高的 0 到 1，不要给框。"
        "label 写 change。reason 只写看到的事实。"
        '只返回 JSON：{"miss":[{"label":"change","cx":0.7,"cy":0.4,"reason":"..."}]}。'
    )


def paint_gray(bgr, mask, color=COVER_GRAY):
    vis = bgr.copy()
    region = np.asarray(mask) > 0
    if region.shape[:2] != vis.shape[:2]:
        raise ValueError("掩膜尺寸与图像不一致")
    vis[region] = color
    return vis


def point_is_gray(bgr, px, py, color=COVER_GRAY) -> bool:
    h, w = bgr.shape[:2]
    if h <= 0 or w <= 0:
        return True
    x = min(max(int(round(float(px))), 0), w - 1)
    y = min(max(int(round(float(py))), 0), h - 1)
    return bool(np.all(bgr[y, x] == np.array(color, dtype=bgr.dtype)))


def map_stitch_point(cx, cy, left_w, right_w, height, gap=STITCH_GAP):
    """拼图上的 0–1 坐标。左图为 t1，右图为 t2，白缝返回 None。px、py 是该时相里的像素。"""
    left_w = int(left_w)
    right_w = int(right_w)
    height = float(height)
    total_w = left_w + int(gap) + right_w
    if total_w <= 0 or height <= 0:
        return None
    px = float(cx) * total_w
    py = float(cy) * height
    if py < 0 or py > height:
        return None
    if px < left_w:
        return "t1", px, min(py, height - 1e-6)
    if px >= left_w + int(gap):
        return "t2", px - left_w - int(gap), min(py, height - 1e-6)
    return None
