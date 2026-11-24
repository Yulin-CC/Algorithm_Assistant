"""
# @Author: 算法组
# @Date: 2026-05-29
# @Description: 变化检测图像自适应切片，同步处理 label / json。
#   从 A_cropped/ B_cropped 读图，切片写入输出目录的 A/ B/。
#   自动计算步长使所有 tile 恰好铺满图像，不溢出、不补边。
#   若存在 label/ 目录则同步裁切 label mask；
#   若存在 json/ 目录则同步生成 tile 级 JSON（过滤/偏移多边形坐标）。
# @Naming : 图像原名_s001.jpg, 图像原名_s002.jpg ...
# @Command: python util/cd_image_tiling.py --input-dir /path/to/data --output-dir /path/to/0-tiles
"""

import os
import math
import json
import argparse
from os.path import join

import cv2
import numpy as np
from tqdm import tqdm

#==============================#
# 接口配置
#==============================#
INPUT_DIR = r"/path/to/data\1-ChangeDetect\TestSet\0-Feedback\260616\rm"          # 多文件夹: 根目录 (遍历子文件夹)；单文件夹: 具体 GEOAI 目录
OUTPUT_DIR = r"/path/to/data\1-ChangeDetect\TestSet\0-Feedback\260616\rm\0-tiles"   # 输出根目录，自动追加原文件夹名
Mutil_DIR = False          # True: 遍历 INPUT_DIR 下所有子文件夹；False: 只处理 INPUT_DIR 自身
TILE_SIZE = 1024          # 切片尺寸（正方形）
SRC_A, SRC_B = "A_cropped", "B_cropped"   # 切片输入（配准裁剪结果）
OUT_A, OUT_B = "A", "B"                   # 切片输出目录名
#==============================#

IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".PNG", ".JPG", ".JPEG")


def imread_unicode(path: str, flags=cv2.IMREAD_COLOR):
    """Windows 中文路径下 cv2.imread 会失败，改用 fromfile + imdecode。"""
    try:
        buf = np.fromfile(path, dtype=np.uint8)
    except OSError:
        return None
    if buf.size == 0:
        return None
    return cv2.imdecode(buf, flags)


def imwrite_unicode(path: str, img: np.ndarray, jpeg_quality: int = 95) -> bool:
    ext = os.path.splitext(path)[1].lower()
    if ext in (".jpg", ".jpeg"):
        ok, enc = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), jpeg_quality])
    elif ext == ".png":
        ok, enc = cv2.imencode(".png", img)
    else:
        ok, enc = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), jpeg_quality])
    if not ok or enc is None:
        return False
    try:
        enc.tofile(path)
    except OSError:
        return False
    return True


def _compute_layout(length: int) -> tuple[int, float]:
    """计算单方向上的 tile 数量及自适应步长。"""
    n = max(1, math.ceil(length / TILE_SIZE))
    stride = (length - TILE_SIZE) / (n - 1) if n > 1 else float(TILE_SIZE)
    return n, stride


def _iter_tile_positions(w: int, h: int):
    """生成器：为图像尺寸 (w, h) 产出 (全局索引, x, y) 三元组，步长自适应。"""
    cols, stride_x = _compute_layout(w)
    rows, stride_y = _compute_layout(h)
    idx = 0
    for row in range(rows):
        y = round(row * stride_y)
        y = min(y, h - TILE_SIZE)
        for col in range(cols):
            x = round(col * stride_x)
            x = min(x, w - TILE_SIZE)
            idx += 1
            yield idx, x, y


def _polygon_overlaps(points, x, y) -> bool:
    """判断多边形是否与矩形 [x, x+TILE_SIZE] x [y, y+TILE_SIZE] 重叠。"""
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    poly_xmin, poly_xmax = min(xs), max(xs)
    poly_ymin, poly_ymax = min(ys), max(ys)
    tile_xmin, tile_xmax = x, x + TILE_SIZE
    tile_ymin, tile_ymax = y, y + TILE_SIZE
    return not (poly_xmax <= tile_xmin or poly_xmin >= tile_xmax or
                poly_ymax <= tile_ymin or poly_ymin >= tile_ymax)


def _offset_and_clip_polygon(points, x, y) -> list | None:
    """平移多边形坐标到 tile 局部坐标，用 Sutherland-Hodgman 裁剪到 tile 内。
    若有效顶点 < 3 则返回 None。
    """
    x_min, x_max = 0.0, float(TILE_SIZE)
    y_min, y_max = 0.0, float(TILE_SIZE)

    offset_pts = [[p[0] - x, p[1] - y] for p in points]

    # Sutherland-Hodgman：逐边裁剪
    def _clip_by_edge(pts, is_x: bool, bound: float, keep_ge: bool):
        """沿一条裁剪边裁剪多边形。keep_ge=True: 保留 >= bound; False: 保留 <= bound"""
        if not pts:
            return []
        output = []
        n = len(pts)
        for i in range(n):
            curr = pts[i]
            prev = pts[(i - 1 + n) % n]
            c_val = curr[0] if is_x else curr[1]
            p_val = prev[0] if is_x else prev[1]

            c_inside = c_val >= bound if keep_ge else c_val <= bound
            p_inside = p_val >= bound if keep_ge else p_val <= bound

            if c_inside:
                if not p_inside:
                    t = (bound - p_val) / (c_val - p_val) if c_val != p_val else 0.0
                    ix = prev[0] + t * (curr[0] - prev[0])
                    iy = prev[1] + t * (curr[1] - prev[1])
                    output.append([ix, iy])
                output.append(curr)
            elif p_inside:
                t = (bound - p_val) / (c_val - p_val) if c_val != p_val else 0.0
                ix = prev[0] + t * (curr[0] - prev[0])
                iy = prev[1] + t * (curr[1] - prev[1])
                output.append([ix, iy])
        return output

    # 依次裁剪：左(x>=0), 右(x<=1024), 下(y>=0), 上(y<=1024)
    clipped = offset_pts
    clipped = _clip_by_edge(clipped, True, x_min, True)   # x >= 0
    clipped = _clip_by_edge(clipped, True, x_max, False)  # x <= 1024
    clipped = _clip_by_edge(clipped, False, y_min, True)  # y >= 0
    clipped = _clip_by_edge(clipped, False, y_max, False) # y <= 1024

    # 去重（相邻点距离过近）
    deduped = []
    for pt in clipped:
        if not deduped or (abs(pt[0] - deduped[-1][0]) > 0.5 or
                           abs(pt[1] - deduped[-1][1]) > 0.5):
            deduped.append(pt)

    # 首尾相近，去掉尾点
    if len(deduped) >= 2:
        dx = abs(deduped[0][0] - deduped[-1][0])
        dy = abs(deduped[0][1] - deduped[-1][1])
        if dx < 0.5 and dy < 0.5:
            deduped = deduped[:-1]

    return deduped if len(deduped) >= 3 else None


# ========================
# 核心处理函数
# ========================

def _make_tile_stem(orig_name: str, idx: int) -> str:
    """生成 tile 基础名（不含扩展名）。"""
    stem, _ = os.path.splitext(orig_name)
    return f"{stem}_s{idx:03d}"


def crop_image(img: np.ndarray, x: int, y: int, save_path: str):
    """裁剪一个 tile 并保存为 JPEG。"""
    tile = img[y: y + TILE_SIZE, x: x + TILE_SIZE]
    if tile.shape[0] != TILE_SIZE or tile.shape[1] != TILE_SIZE:
        raise ValueError(f"tile 尺寸异常 {tile.shape[:2]} @ {save_path}")
    if not imwrite_unicode(save_path, tile, jpeg_quality=95):
        raise OSError(f"写入失败: {save_path}")


def crop_label(mask: np.ndarray, x: int, y: int, save_path: str):
    """裁剪一个 label tile 并保存为 PNG。"""
    tile = mask[y: y + TILE_SIZE, x: x + TILE_SIZE]
    if not imwrite_unicode(save_path, tile):
        raise OSError(f"写入失败: {save_path}")


def make_tile_json(
    orig_json: dict,
    x: int, y: int,
    tile_name: str,
    tile_mask_name: str | None,
    out_path: str,
):
    """根据原始 JSON 生成对应 tile 的 JSON（过滤/平移多边形）。"""
    new_shapes = []
    for shape in orig_json.get("shapes", []):
        points = shape.get("points", [])
        if not points:
            continue
        if not _polygon_overlaps(points, x, y):
            continue

        new_pts = _offset_and_clip_polygon(points, x, y)
        if new_pts is None:
            continue

        new_shape = dict(shape)
        new_shape["points"] = new_pts
        new_shapes.append(new_shape)

    tile_json = {
        "version": orig_json.get("version", "0.1.4"),
        "flags": orig_json.get("flags", {}),
        "shapes": new_shapes,
        "imagePath": tile_name,
        "imageData": None,
        "imageHeight": TILE_SIZE,
        "imageWidth": TILE_SIZE,
        "change_detection": orig_json.get("change_detection", True),
        "imagePathA": tile_name,
        "imagePathB": tile_name,
        "maskPath": tile_mask_name or "",
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(tile_json, f, indent=2, ensure_ascii=False)


# ========================
# 单目录切片
# ========================

def tile_one_folder(input_dir: str, output_dir: str) -> int:
    """对单个 GEOAI 目录执行切片，返回 tile 总数。"""
    has_label = os.path.isdir(join(input_dir, "label"))
    has_json = os.path.isdir(join(input_dir, "json"))
    out_subs = [OUT_A, OUT_B]
    if has_label:
        out_subs.append("label")
    if has_json:
        out_subs.append("json")

    print(f"  输入：{input_dir}")
    print(f"  输出：{output_dir}")
    print(f"  源目录：{SRC_A}/ + {SRC_B}/ → {OUT_A}/ + {OUT_B}/")
    print(f"  label/  : {'[有]' if has_label else '[无]'}")
    print(f"  json/   : {'[有]' if has_json else '[无]'}")
    print("  " + "-" * 40)

    for sub in (SRC_A, SRC_B):
        src = join(input_dir, sub)
        if not os.path.isdir(src):
            print(f"  [错误] 缺少 {src}")
            return 0
    for sub in out_subs:
        os.makedirs(join(output_dir, sub), exist_ok=True)

    a_dir = join(input_dir, SRC_A)
    img_names = sorted([f for f in os.listdir(a_dir) if f.lower().endswith(IMAGE_EXTS)])
    print(f"  基准（{SRC_A}/）共 {len(img_names)} 张图像")

    total_tiles = 0
    skipped_small = 0
    for fname in tqdm(img_names, desc="  切片进度", unit="img"):
        img_a = imread_unicode(join(input_dir, SRC_A, fname))
        img_b = imread_unicode(join(input_dir, SRC_B, fname))
        if img_a is None or img_b is None:
            print(f"  [跳过] 无法读取 {SRC_A}/{SRC_B}: {fname}")
            continue
        h, w = img_a.shape[:2]
        if h < TILE_SIZE or w < TILE_SIZE:
            skipped_small += 1
            tqdm.write(f"  [跳过] 小于 {TILE_SIZE}: {fname}  {w}x{h}")
            continue

        # label（可选；须与 cropped 同尺寸才同步有意义）
        mask = None
        if has_label:
            mask_path = join(input_dir, "label", fname)
            if not os.path.isfile(mask_path):
                stem, _ = os.path.splitext(fname)
                for ext in IMAGE_EXTS:
                    mp = join(input_dir, "label", stem + ext)
                    if os.path.isfile(mp):
                        mask_path = mp
                        break
            if os.path.isfile(mask_path):
                mask = imread_unicode(mask_path, cv2.IMREAD_GRAYSCALE)

        # JSON（可选）
        jdata = None
        if has_json:
            json_path = join(input_dir, "json", os.path.splitext(fname)[0] + ".json")
            if os.path.isfile(json_path):
                with open(json_path, "r", encoding="utf-8") as f:
                    jdata = json.load(f)

        for idx, x, y in _iter_tile_positions(w, h):
            stem = _make_tile_stem(fname, idx)
            crop_image(img_a, x, y, join(output_dir, OUT_A, stem + ".jpg"))
            crop_image(img_b, x, y, join(output_dir, OUT_B, stem + ".jpg"))
            if mask is not None:
                crop_label(mask, x, y, join(output_dir, "label", stem + ".png"))
            if jdata is not None:
                mask_name = stem + ".png" if mask is not None else None
                make_tile_json(jdata, x, y, stem + ".jpg", mask_name,
                               join(output_dir, "json", stem + ".json"))
            total_tiles += 1

    for sub in out_subs:
        out_dir = join(output_dir, sub)
        if os.path.isdir(out_dir):
            cnt = len([f for f in os.listdir(out_dir) if not f.startswith(".")])
            print(f"    {sub}/ → {cnt} 个文件")
    print(f"    tile 总数：{total_tiles}")
    if skipped_small:
        print(f"    小于 {TILE_SIZE} 已跳过：{skipped_small}")
    return total_tiles


# ========================
# 主流程
# ========================

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="变化检测图像自适应切片，同步处理 label / json")
    parser.add_argument("--input-dir", dest="input_dir", default=INPUT_DIR, help="输入目录（多文件夹: 根目录；单文件夹: 具体 GEOAI 目录）")
    parser.add_argument("--output-dir", dest="output_dir", default=OUTPUT_DIR, help="输出根目录，自动追加原文件夹名")
    parser.add_argument("--tile-size", dest="tile_size", type=int, default=TILE_SIZE, help="切片尺寸，默认 1024")
    parser.add_argument("--src-a", dest="src_a", default=SRC_A, help="切片输入 A 目录名，默认 A_cropped")
    parser.add_argument("--src-b", dest="src_b", default=SRC_B, help="切片输入 B 目录名，默认 B_cropped")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    input_dir = args.input_dir
    output_dir = args.output_dir
    # 支持命令行覆盖 TILE_SIZE（需全局生效，直接修改模块级常量）
    if args.tile_size != TILE_SIZE:
        globals()["TILE_SIZE"] = args.tile_size
    if args.src_a != SRC_A:
        globals()["SRC_A"] = args.src_a
    if args.src_b != SRC_B:
        globals()["SRC_B"] = args.src_b

    print(f"输入根目录：{input_dir}")
    print(f"输出根目录：{output_dir}")
    print(f"多文件夹模式：{'开启' if Mutil_DIR else '关闭'}")
    print(f"切片尺寸：{TILE_SIZE}x{TILE_SIZE}")
    print("-" * 50)

    if Mutil_DIR:
        subdirs = sorted(
            d for d in os.listdir(input_dir)
            if os.path.isdir(join(input_dir, d))
        )
        if not subdirs:
            print("  根目录下无子文件夹。")
            return
        print(f"发现 {len(subdirs)} 个子文件夹：")
        for d in subdirs:
            print(f"  ╰ {d}")
        print("-" * 50)

        grand_total = 0
        for d in subdirs:
            print(f"\n>>> {d}")
            in_dir = join(input_dir, d)
            out_dir = join(output_dir, d)
            cnt = tile_one_folder(in_dir, out_dir)
            grand_total += cnt
        print(f"\n{'=' * 50}")
        print(f"全部完成！总计 {grand_total} 个 tile")
    else:
        folder_name = os.path.basename(input_dir)
        out_dir = join(output_dir, folder_name)
        tile_one_folder(input_dir, out_dir)
        print(f"完成！输出 → {out_dir}")


if __name__ == "__main__":
    main()
