"""
# @Author: Yullin
# @Date: 2026-08-05
# @Description: YOLO txt → LabelMe JSON（detect=rectangle / segment=polygon）
# @Command: python util/convert_txt2json.py --dataset /path/to/data --yaml classes.yaml --task segment
"""

import argparse
import json
from pathlib import Path

import yaml
from PIL import Image
from tqdm import tqdm

SUPPORTED_TASKS = ("detect", "segment")
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff")


#-------------#
# 读取类别表
#-------------#
def load_id2name(yaml_path: str | Path) -> dict[int, str]:
    """names 字典保留原始 class id；列表则按 enumerate 编号。"""
    with open(yaml_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    names = data["names"] if isinstance(data, dict) and "names" in data else data
    if isinstance(names, dict):
        return {int(k): str(v) for k, v in names.items()}
    return {i: str(n) for i, n in enumerate(names)}


#-------------#
# 查找图片
#-------------#
def find_image(images_dir: Path, stem: str) -> Path | None:
    for ext in IMAGE_EXTS:
        for candidate in (images_dir / f"{stem}{ext}", images_dir / f"{stem}{ext.upper()}"):
            if candidate.is_file():
                return candidate
    return None


#-------------#
# YOLO 行 → LabelMe shape
#-------------#
def line_to_detect_shape(parts: list[str], w: int, h: int, id2name: dict[int, str]) -> dict | None:
    """YOLO detect: class cx cy bw bh → rectangle（两点对角）。"""
    if len(parts) != 5:
        return None
    cls_id = int(float(parts[0]))
    if cls_id not in id2name:
        return None
    cx, cy, bw, bh = map(float, parts[1:5])
    x1 = (cx - bw / 2.0) * w
    y1 = (cy - bh / 2.0) * h
    x2 = (cx + bw / 2.0) * w
    y2 = (cy + bh / 2.0) * h
    if x2 <= x1 or y2 <= y1:
        return None
    return {
        "label": id2name[cls_id],
        "points": [[float(x1), float(y1)], [float(x2), float(y2)]],
        "group_id": None,
        "description": "",
        "difficult": False,
        "shape_type": "rectangle",
        "flags": {},
        "attributes": {},
    }


def line_to_segment_shape(parts: list[str], w: int, h: int, id2name: dict[int, str]) -> dict | None:
    """YOLO segment: class x1 y1 x2 y2 ... → polygon。"""
    if len(parts) < 7:
        return None
    cls_id = int(float(parts[0]))
    if cls_id not in id2name:
        return None
    coords = [float(v) for v in parts[1:]]
    if len(coords) % 2 != 0 or len(coords) < 6:
        return None
    points = [[coords[i] * w, coords[i + 1] * h] for i in range(0, len(coords), 2)]
    return {
        "label": id2name[cls_id],
        "points": points,
        "group_id": None,
        "description": "",
        "difficult": False,
        "shape_type": "polygon",
        "flags": {},
        "attributes": {},
    }


#-------------#
# 写出 LabelMe JSON
#-------------#
def write_labelme(json_path: Path, image_name: str, w: int, h: int, shapes: list[dict]) -> None:
    meta = {
        "version": "0.1.4",
        "flags": {},
        "shapes": shapes,
        "imagePath": image_name,
        "imageData": None,
        "imageHeight": h,
        "imageWidth": w,
        "text": "",
    }
    json_path.parent.mkdir(parents=True, exist_ok=True)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


#-------------#
# 批量转换
#-------------#
def txt2labelme(
    txt_dir: str | Path,
    json_dir: str | Path,
    images_dir: str | Path,
    yaml_path: str | Path,
    task: str = "segment",
) -> dict:
    """
    YOLO txt 目录 → LabelMe json 目录。
    detect: bbox → rectangle；segment: polygon → polygon。
    """
    task = task.lower()
    if task not in SUPPORTED_TASKS:
        raise ValueError(f"Unsupported task '{task}', choose from {SUPPORTED_TASKS}")

    txt_dir = Path(txt_dir)
    json_dir = Path(json_dir)
    images_dir = Path(images_dir)
    id2name = load_id2name(yaml_path)
    json_dir.mkdir(parents=True, exist_ok=True)
    shape_fn = line_to_detect_shape if task == "detect" else line_to_segment_shape

    stats = {
        "total": 0,
        "ok": 0,
        "skip_no_image": 0,
        "skip_unknown_class": 0,
        "skip_shape": 0,
        "shapes": 0,
    }

    for tp in tqdm(sorted(txt_dir.glob("*.txt")), desc=f"txt2labelme-{task}"):
        stats["total"] += 1
        img = find_image(images_dir, tp.stem)
        if img is None:
            stats["skip_no_image"] += 1
            continue

        with Image.open(img) as im:
            w, h = im.size

        shapes = []
        for line in tp.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            cls_id = int(float(parts[0]))
            if cls_id not in id2name:
                stats["skip_unknown_class"] += 1
                continue
            shape = shape_fn(parts, w, h, id2name)
            if shape is None:
                stats["skip_shape"] += 1
                continue
            shapes.append(shape)

        write_labelme(json_dir / f"{tp.stem}.json", img.name, w, h, shapes)
        stats["ok"] += 1
        stats["shapes"] += len(shapes)

    return stats


#-------------#
# 参数
#-------------#
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="YOLO txt → LabelMe JSON")
    parser.add_argument("--dataset", required=True, help="数据集根目录（含 images/、labels/）")
    parser.add_argument("--yaml", required=True, help="类别 yaml（含 names 字段）")
    parser.add_argument("--task", default="segment", choices=SUPPORTED_TASKS, help="detect=bbox, segment=polygon")
    parser.add_argument("--txt-dir", default=None, help="YOLO txt 目录，默认 {dataset}/labels")
    parser.add_argument("--json-dir", default=None, help="LabelMe 输出目录，默认 {dataset}/jsons-segm 或 jsons-detect")
    parser.add_argument("--images-dir", default=None, help="图片目录，默认 {dataset}/images")
    return parser


def default_json_dir(dataset: Path, task: str) -> Path:
    return dataset / ("jsons-segm" if task == "segment" else "jsons-detect")


#-------------#
# 入口
#-------------#
def main(argv=None):
    args = build_parser().parse_args(argv)
    dataset = Path(args.dataset)
    txt_dir = Path(args.txt_dir) if args.txt_dir else dataset / "labels"
    images_dir = Path(args.images_dir) if args.images_dir else dataset / "images"
    json_dir = Path(args.json_dir) if args.json_dir else default_json_dir(dataset, args.task)

    if not txt_dir.is_dir():
        raise FileNotFoundError(f"缺少 labels 目录: {txt_dir}")
    if not images_dir.is_dir():
        raise FileNotFoundError(f"缺少 images 目录: {images_dir}")

    stats = txt2labelme(txt_dir, json_dir, images_dir, args.yaml, task=args.task)
    print(
        f"txt2labelme ({args.task}) 完成: {stats['ok']}/{stats['total']} 张，"
        f"{stats['shapes']} 个目标 → {json_dir}\n"
        f"  无图跳过 {stats['skip_no_image']}，未知类别 {stats['skip_unknown_class']}，"
        f"形状跳过 {stats['skip_shape']}"
    )


if __name__ == "__main__":
    main()
