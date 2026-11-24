#!/usr/bin/env python3
"""
# @Author: 算法组
# @Date: 2026-08-07
# @Description: YOLO label → VOC XML 批量转换。
#   读取 labels/ 下 YOLO .txt 标注，生成 annotations/ 下的 VOC .xml。
#
# @Command: python util/convert_txt2xml.py /path/to/dataset --classes classes.yaml
"""

import argparse
import os
import sys
import xml.etree.ElementTree as ET
from xml.dom import minidom

from PIL import Image

# ==============================
# 接口配置
# ==============================
DATA_DIR = "/path/to/dataset"
CLASSES_PATH = None  # 类别 yaml / classes.txt 路径
# ==============================

IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff")


def load_classes(classes_path: str) -> list:
    """加载类别列表（yaml names 字典/列表，或 classes.txt 一行一类）。"""
    if not classes_path or not os.path.isfile(classes_path):
        return []

    if classes_path.lower().endswith((".yaml", ".yml")):
        import yaml

        with open(classes_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        names = data.get("names", data) if isinstance(data, dict) else data
        if isinstance(names, dict):
            return [names[k] for k in sorted(names, key=lambda x: int(x))]
        return list(names)

    with open(classes_path, encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


def find_image(images_dir: str, stem: str) -> str | None:
    for ext in IMAGE_EXTS:
        for candidate in (
            os.path.join(images_dir, stem + ext),
            os.path.join(images_dir, stem + ext.upper()),
        ):
            if os.path.isfile(candidate):
                return candidate
    return None


def yolo_to_bndbox(cx: float, cy: float, bw: float, bh: float, img_w: int, img_h: int) -> tuple:
    """YOLO 归一化 cx cy w h → 像素 xmin ymin xmax ymax（裁剪到图像范围）。"""
    xmin = (cx - bw / 2.0) * img_w
    ymin = (cy - bh / 2.0) * img_h
    xmax = (cx + bw / 2.0) * img_w
    ymax = (cy + bh / 2.0) * img_h

    xmin = max(0, min(img_w - 1, int(round(xmin))))
    ymin = max(0, min(img_h - 1, int(round(ymin))))
    xmax = max(0, min(img_w, int(round(xmax))))
    ymax = max(0, min(img_h, int(round(ymax))))
    if xmax <= xmin:
        xmax = min(img_w, xmin + 1)
    if ymax <= ymin:
        ymax = min(img_h, ymin + 1)
    return xmin, ymin, xmax, ymax


def indent_xml(elem: ET.Element) -> str:
    rough = ET.tostring(elem, encoding="utf-8")
    parsed = minidom.parseString(rough)
    return parsed.toprettyxml(indent="   ")


def build_annotation(filename: str, img_w: int, img_h: int, objects: list) -> ET.Element:
    annotation = ET.Element("annotation")
    ET.SubElement(annotation, "folder").text = "DATA"
    ET.SubElement(annotation, "filename").text = filename

    size = ET.SubElement(annotation, "size")
    ET.SubElement(size, "width").text = str(img_w)
    ET.SubElement(size, "height").text = str(img_h)
    ET.SubElement(size, "depth").text = "3"

    for name, xmin, ymin, xmax, ymax in objects:
        obj = ET.SubElement(annotation, "object")
        ET.SubElement(obj, "name").text = name
        bndbox = ET.SubElement(obj, "bndbox")
        ET.SubElement(bndbox, "xmin").text = str(xmin)
        ET.SubElement(bndbox, "ymin").text = str(ymin)
        ET.SubElement(bndbox, "xmax").text = str(xmax)
        ET.SubElement(bndbox, "ymax").text = str(ymax)

    return annotation


def convert_one(label_path: str, image_path: str, classes: list) -> tuple[str, dict]:
    """单文件 YOLO txt → VOC XML 文本。返回 (xml_text, stats)。"""
    with Image.open(image_path) as im:
        img_w, img_h = im.size

    objects = []
    stats = {"objects": 0, "unknown_class": 0, "bad_line": 0}

    with open(label_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            # detect: class cx cy w h（忽略 segment 多点行）
            if len(parts) != 5:
                stats["bad_line"] += 1
                continue
            cls_id = int(float(parts[0]))
            if cls_id < 0 or cls_id >= len(classes):
                stats["unknown_class"] += 1
                continue
            cx, cy, bw, bh = map(float, parts[1:5])
            xmin, ymin, xmax, ymax = yolo_to_bndbox(cx, cy, bw, bh, img_w, img_h)
            objects.append((classes[cls_id], xmin, ymin, xmax, ymax))
            stats["objects"] += 1

    root = build_annotation(os.path.basename(image_path), img_w, img_h, objects)
    # minidom 会带 xml 声明；规范示例无声明，去掉首行
    xml_text = indent_xml(root)
    lines = xml_text.splitlines()
    if lines and lines[0].startswith("<?xml"):
        lines = lines[1:]
    body = "\n".join(lines).strip() + "\n"
    return body, stats


def convert_all(data_dir: str, classes_path: str, overwrite: bool = False) -> dict:
    """批量 YOLO → VOC XML。"""
    label_dir = os.path.join(data_dir, "labels")
    images_dir = os.path.join(data_dir, "images")
    annot_dir = os.path.join(data_dir, "annotations")
    os.makedirs(annot_dir, exist_ok=True)

    classes = load_classes(classes_path)
    if not classes:
        raise FileNotFoundError(f"未能加载类别文件: {classes_path}")

    label_files = sorted(
        f for f in os.listdir(label_dir) if f.lower().endswith(".txt")
    ) if os.path.isdir(label_dir) else []

    stats = {
        "ok": 0,
        "total": len(label_files),
        "skipped": 0,
        "skip_no_image": 0,
        "objects": 0,
        "unknown_class": 0,
        "bad_line": 0,
    }

    for fn in label_files:
        stem = os.path.splitext(fn)[0]
        out_xml = os.path.join(annot_dir, stem + ".xml")
        if os.path.isfile(out_xml) and not overwrite:
            stats["skipped"] += 1
            continue

        image_path = find_image(images_dir, stem)
        if image_path is None:
            stats["skip_no_image"] += 1
            continue

        label_path = os.path.join(label_dir, fn)
        xml_text, one = convert_one(label_path, image_path, classes)
        with open(out_xml, "w", encoding="utf-8") as f:
            f.write(xml_text)

        stats["ok"] += 1
        stats["objects"] += one["objects"]
        stats["unknown_class"] += one["unknown_class"]
        stats["bad_line"] += one["bad_line"]

    return stats


def resolve_classes_path(data_dir: str, classes_path: str | None) -> str | None:
    if classes_path and os.path.isfile(classes_path):
        return classes_path
    for name in ("classes.yaml", "classes.yml", "classes.txt"):
        candidate = os.path.join(data_dir, name)
        if os.path.isfile(candidate):
            return candidate
    return classes_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="YOLO label → VOC XML 批量转换")
    parser.add_argument("dataset", help="YOLO 数据目录路径")
    parser.add_argument("--Path", "--path", dest="data_dir", default=DATA_DIR, help="覆盖 dataset 参数")
    parser.add_argument("--classes", default=CLASSES_PATH, help="类别 yaml 或 classes.txt")
    parser.add_argument("--overwrite", action="store_true", help="覆盖已有 XML")
    parser.add_argument("--dry-run", action="store_true", help="仅预览，不实际写出")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    data_dir = args.data_dir if args.data_dir != DATA_DIR else args.dataset
    classes_path = resolve_classes_path(data_dir, args.classes)

    print(f"数据目录：{data_dir}")
    print(f"类别文件：{classes_path or '(未找到)'}")
    print("-" * 50)

    step, total = 1, 3

    print(f"[{step}/{total}] 扫描 labels...")
    step += 1
    label_dir = os.path.join(data_dir, "labels")
    images_dir = os.path.join(data_dir, "images")
    if not os.path.isdir(label_dir):
        print(f"  [错误] 目录不存在: {label_dir}")
        sys.exit(1)
    if not os.path.isdir(images_dir):
        print(f"  [错误] 目录不存在: {images_dir}")
        sys.exit(1)
    if not classes_path or not os.path.isfile(classes_path):
        print("  [错误] 缺少类别文件（classes.yaml / classes.txt），请用 --classes 指定")
        sys.exit(1)

    txt_count = len([f for f in os.listdir(label_dir) if f.lower().endswith(".txt")])
    print(f"  发现 {txt_count} 个 txt")
    print(f"  类别数: {len(load_classes(classes_path))}")

    print(f"[{step}/{total}] 转换 YOLO → VOC XML...")
    step += 1
    if args.dry_run:
        print(f"  [预览] 将处理约 {txt_count} 个文件 → annotations/")
    else:
        stats = convert_all(data_dir, classes_path, overwrite=args.overwrite)
        print(f"  成功: {stats['ok']} / {stats['total']}")
        if stats["skipped"]:
            print(f"  跳过已存在: {stats['skipped']}")
        if stats["skip_no_image"]:
            print(f"  无对应图像: {stats['skip_no_image']}")
        print(f"  目标数: {stats['objects']}")
        if stats["unknown_class"]:
            print(f"  未知类别行: {stats['unknown_class']}")
        if stats["bad_line"]:
            print(f"  非 detect 行跳过: {stats['bad_line']}")

    print(f"[{step}/{total}] 完成")
    print("-" * 50)
    print("完成！")


if __name__ == "__main__":
    main()
