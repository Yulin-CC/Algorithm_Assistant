"""
# @Author: Yullin
# @Date: 2026-07-30
# @Description: LabelMe JSON → 多类 COCO instances（bbox；polygon 另写 segmentation），供 YOLO/SAM 链路使用
# @Command: python util/convert_labelme2coco.py --dataset /path/to/year --yaml classes.yaml --project smartwaterarea_2025
"""

import argparse
import json
from pathlib import Path

import yaml
from tqdm import tqdm

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tiff", ".tif"}


#-------------#
# 读取类别表
#-------------#
def load_names(yaml_path: str | Path) -> list[str]:
    with open(yaml_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    names = data["names"]
    if isinstance(names, dict):
        return [names[k] for k in sorted(names, key=lambda x: int(x))]
    return list(names)


def build_categories(names: list[str]) -> list[dict]:
    """COCO categories：id 从 1 起，与 names 顺序一致（YOLO class_id = id - 1）。"""
    return [{"id": i + 1, "name": name, "supercategory": "object"} for i, name in enumerate(names)]


#-------------#
# 解析图片路径
#-------------#
def resolve_image(images_dir: Path, stem: str, hint_name: str | None) -> Path | None:
    if hint_name:
        candidate = images_dir / Path(str(hint_name).replace("\\", "/")).name
        if candidate.is_file():
            return candidate
    for ext in IMAGE_EXTENSIONS:
        candidate = images_dir / f"{stem}{ext}"
        if candidate.is_file():
            return candidate
    return None


#-------------#
# points → bbox / polygon segmentation
#-------------#
def points_to_bbox(points: list[list[float]]) -> list[float] | None:
    if len(points) < 2:
        return None
    xs = [float(p[0]) for p in points]
    ys = [float(p[1]) for p in points]
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    bw, bh = xmax - xmin, ymax - ymin
    if bw <= 0 or bh <= 0:
        return None
    return [xmin, ymin, bw, bh]


def shape_to_segmentation(shape: dict) -> list[list[float]] | None:
    shape_type = (shape.get("shape_type") or "").lower()
    points = shape.get("points") or []
    if shape_type != "polygon" or len(points) < 3:
        return None
    return [[float(c) for pt in points for c in pt]]


#-------------#
# 单文件 LabelMe → COCO images/annotations
#-------------#
def parse_labelme_file(
    json_path: Path,
    images_dir: Path,
    name2id: dict[str, int],
) -> tuple[dict, list[dict]] | None:
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    image_file = resolve_image(images_dir, json_path.stem, data.get("imagePath"))
    if image_file is None:
        return None

    width = int(data["imageWidth"])
    height = int(data["imageHeight"])
    image = {
        "id": 0,
        "file_name": image_file.name,
        "width": width,
        "height": height,
    }

    annotations: list[dict] = []
    for shape in data.get("shapes") or []:
        label = shape.get("label")
        if label not in name2id:
            continue
        points = shape.get("points") or []
        bbox = points_to_bbox(points)
        if bbox is None:
            continue
        ann: dict = {
            "id": 0,
            "image_id": 0,
            "category_id": name2id[label],
            "bbox": bbox,
            "area": float(bbox[2] * bbox[3]),
            "iscrowd": 0,
        }
        segm = shape_to_segmentation(shape)
        if segm is not None:
            ann["segmentation"] = segm
        annotations.append(ann)

    return image, annotations


#-------------#
# 目录合并
#-------------#
def convert_dataset(
    dataset: Path,
    yaml_path: Path,
    output_path: Path,
    images_dir_name: str = "images",
    jsons_dir_name: str = "jsons",
) -> dict:
    images_dir = dataset / images_dir_name
    jsons_dir = dataset / jsons_dir_name
    if not images_dir.is_dir():
        raise FileNotFoundError(f"缺少图片目录: {images_dir}")
    if not jsons_dir.is_dir():
        raise FileNotFoundError(f"缺少标注目录: {jsons_dir}")

    names = load_names(yaml_path)
    categories = build_categories(names)
    name2id = {n: c["id"] for n, c in zip(names, categories)}

    json_files = sorted(jsons_dir.glob("*.json"))
    if not json_files:
        raise RuntimeError(f"未找到 json: {jsons_dir}")

    images: list[dict] = []
    annotations: list[dict] = []
    stats = {
        "total_json": len(json_files),
        "ok": 0,
        "skip_no_image": 0,
        "skip_unknown_label": 0,
        "empty_ann": 0,
        "boxes": 0,
    }
    unknown_labels: set[str] = set()

    for jp in tqdm(json_files, desc="labelme2coco"):
        with open(jp, encoding="utf-8") as f:
            raw = json.load(f)
        for shape in raw.get("shapes") or []:
            lab = shape.get("label")
            if lab and lab not in name2id:
                unknown_labels.add(lab)

        parsed = parse_labelme_file(jp, images_dir, name2id)
        if parsed is None:
            stats["skip_no_image"] += 1
            continue

        image, anns = parsed
        image["id"] = len(images)
        for ann in anns:
            ann["id"] = len(annotations)
            ann["image_id"] = image["id"]
            annotations.append(ann)
        images.append(image)
        stats["ok"] += 1
        stats["boxes"] += len(anns)
        if not anns:
            stats["empty_ann"] += 1

    stats["skip_unknown_label"] = len(unknown_labels)
    stats["unknown_labels"] = sorted(unknown_labels)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "info": {"description": "LabelMe -> multi-class COCO (bbox for SAM/YOLO)"},
                "licenses": [],
                "categories": categories,
                "images": images,
                "annotations": annotations,
            },
            f,
            ensure_ascii=False,
        )
    return stats


#-------------#
# 参数
#-------------#
def parse_args():
    parser = argparse.ArgumentParser(description="LabelMe → 多类 COCO instances（YOLO/SAM）")
    parser.add_argument("--dataset", required=True, help="年份/数据集根目录（含 images/ 与 jsons/）")
    parser.add_argument("--yaml", required=True, help="类别 yaml（names 字段，顺序即 class id）")
    parser.add_argument("--project", default="", help="输出文件前缀，默认取 dataset 目录名")
    parser.add_argument("--output", default="", help="输出 JSON 路径，默认 {dataset}/{project}_bbox.json")
    parser.add_argument("--images-dir", default="images", help="图片子目录名")
    parser.add_argument("--jsons-dir", default="jsons", help="LabelMe json 子目录名")
    return parser.parse_args()


def main():
    args = parse_args()
    dataset = Path(args.dataset).resolve()
    project = args.project or dataset.name
    output = Path(args.output) if args.output else dataset / f"{project}_bbox.json"

    stats = convert_dataset(
        dataset,
        Path(args.yaml),
        output,
        images_dir_name=args.images_dir,
        jsons_dir_name=args.jsons_dir,
    )
    print(f"✅ 写出: {output}")
    print(
        f"   图像 {stats['ok']}/{stats['total_json']}，框 {stats['boxes']}，"
        f"空标注图 {stats['empty_ann']}，缺图 {stats['skip_no_image']}"
    )
    if stats["unknown_labels"]:
        print(f"   ⚠️  yaml 未收录类别（已跳过）: {stats['unknown_labels']}")


if __name__ == "__main__":
    main()
