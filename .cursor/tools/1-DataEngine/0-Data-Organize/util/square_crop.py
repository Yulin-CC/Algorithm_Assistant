"""
# @Author: 算法组
# @Date: 2026-09-27
# @Description: 目标框先外扩，再按长边裁成正方形
# @Command: python util/square_crop.py --image a.jpg --box 10 20 110 60 --out b.jpg --expand 2
"""

from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np


def clip_box(x1: float, y1: float, x2: float, y2: float, width: int, height: int):
    x1 = min(max(x1, 0), width - 1)
    y1 = min(max(y1, 0), height - 1)
    x2 = min(max(x2, 0), width)
    y2 = min(max(y2, 0), height)
    return x1, y1, x2, y2


def read_image(path: Path):
    data = np.fromfile(str(path), dtype=np.uint8)
    if data.size == 0:
        return None
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


def save_image(path: Path, image) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ok, encoded = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
    if not ok:
        raise SystemExit(f"写出失败: {path}")
    encoded.tofile(str(path))


#-------------#
# 正方形裁剪
#-------------#
def crop_square(image, box: tuple, expand: float = 2.0, color: tuple | None = None):
    """外扩 expand 倍后，以长边为边长裁正方形，并平移到图内。"""
    height, width = image.shape[:2]
    x1, y1, x2, y2 = clip_box(box[0], box[1], box[2], box[3], width, height)
    box_w = max(x2 - x1, 1.0)
    box_h = max(y2 - y1, 1.0)
    side = int(round(float(expand) * max(box_w, box_h)))
    side = max(1, min(side, width, height))
    cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
    left = min(max(int(round(cx - side / 2.0)), 0), width - side)
    top = min(max(int(round(cy - side / 2.0)), 0), height - side)
    crop = image[top:top + side, left:left + side].copy()
    if color is not None:
        thick = max(2, int(round(min(box_w, box_h) * 0.02)))
        p1 = (int(round(x1 - left)), int(round(y1 - top)))
        p2 = (int(round(x2 - left)), int(round(y2 - top)))
        cv2.rectangle(crop, p1, p2, color, thick)
    return crop


def parse_args():
    parser = argparse.ArgumentParser(description="外扩后按长边裁正方形")
    parser.add_argument("--image", required=True)
    parser.add_argument("--box", nargs=4, type=float, required=True, metavar=("X1", "Y1", "X2", "Y2"))
    parser.add_argument("--out", required=True)
    parser.add_argument("--expand", type=float, default=2.0)
    parser.add_argument("--draw", action="store_true", help="在裁图上画出原框")
    return parser.parse_args()


def main():
    args = parse_args()
    image = read_image(Path(args.image))
    if image is None:
        raise SystemExit(f"读图失败: {args.image}")
    color = (144, 238, 144) if args.draw else None
    crop = crop_square(image, tuple(args.box), args.expand, color)
    save_image(Path(args.out), crop)
    print(f"写出 {args.out}  {crop.shape[1]}x{crop.shape[0]}")


if __name__ == "__main__":
    main()
