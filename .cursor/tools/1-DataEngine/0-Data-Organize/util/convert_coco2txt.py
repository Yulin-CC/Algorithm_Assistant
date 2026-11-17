"""
# @Author: 算法组
# @Date: 2026-07-13
# @Description: COCO instances JSON -> YOLO txt（detect=bbox / segment=polygon）
# @Command: python util/convert_coco2txt.py --dataset /path/to/data --task segment --flatten
"""

import argparse
import json
import re
import shutil
from pathlib import Path

SUPPORTED_TASKS = ("detect", "segment")
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}
SPLIT_PATTERN = re.compile(r"(train|val|test)(\d{4})?", re.IGNORECASE)


def write_txt(txt_path: Path, instances: list[list[float]]) -> None:
    """写入 YOLO txt，每行一个实例。"""
    txt_path.parent.mkdir(parents=True, exist_ok=True)
    with open(txt_path, "w", encoding="utf-8") as f:
        for obj in instances:
            f.write(" ".join(f"{x:.6g}" for x in obj) + "\n")


def build_category_map(categories: list[dict]) -> dict[int, int]:
    """COCO category_id -> YOLO 连续 class_id（按 id 排序）。"""
    sorted_cats = sorted(categories, key=lambda x: x["id"])
    return {cat["id"]: idx for idx, cat in enumerate(sorted_cats)}


def build_category_names(categories: list[dict]) -> list[str]:
    """COCO categories -> YOLO names 列表（按 class_id 排序）。"""
    sorted_cats = sorted(categories, key=lambda x: x["id"])
    return [cat["name"] for cat in sorted_cats]


def write_dataset_yaml(dataset: Path, names: list[str], task: str) -> Path:
    """根据 COCO categories 生成 dataset.yaml。"""
    yaml_path = dataset / "dataset.yaml"
    lines = [
        f"# COCO -> YOLO {task}",
        f"# Usage: yolo train data={yaml_path} task={task}",
        "",
        f"path: {dataset}",
        "train: train.txt",
        "val: val.txt",
        "",
        f"nc: {len(names)}",
        "names:",
    ]
    for idx, name in enumerate(names):
        lines.append(f"  {idx}: {name}")
    yaml_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return yaml_path


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def ann_to_detect(ann: dict, cat_map: dict[int, int], width: int, height: int) -> list[float] | None:
    """COCO bbox -> YOLO detect。"""
    bbox = ann.get("bbox")
    if not bbox or len(bbox) != 4:
        return None
    x, y, bw, bh = bbox
    if bw <= 0 or bh <= 0:
        return None
    cls_id = cat_map.get(ann["category_id"])
    if cls_id is None:
        return None
    return [
        cls_id,
        clamp01((x + bw / 2) / width),
        clamp01((y + bh / 2) / height),
        clamp01(bw / width),
        clamp01(bh / height),
    ]


def polygon_to_segment(poly: list[float], cls_id: int, width: int, height: int) -> list[float] | None:
    """单个多边形 -> YOLO segment 行。"""
    if len(poly) < 6 or len(poly) % 2 != 0:
        return None
    row = [cls_id]
    for i in range(0, len(poly), 2):
        row.append(clamp01(poly[i] / width))
        row.append(clamp01(poly[i + 1] / height))
    return row


def ann_to_segment(ann: dict, cat_map: dict[int, int], width: int, height: int) -> list[list[float]]:
    """COCO segmentation -> 一条或多条 YOLO segment 行。"""
    if ann.get("iscrowd", 0):
        return []
    cls_id = cat_map.get(ann["category_id"])
    if cls_id is None:
        return []

    segs = ann.get("segmentation") or []
    rows = []
    for seg in segs:
        if not isinstance(seg, list):
            continue
        row = polygon_to_segment(seg, cls_id, width, height)
        if row is not None:
            rows.append(row)
    return rows


def infer_split_name(json_path: Path) -> str | None:
    """从 instances_train2017.json 等文件名推断 split 子目录名。"""
    match = SPLIT_PATTERN.search(json_path.stem)
    if not match:
        return None
    prefix, year = match.group(1).lower(), match.group(2) or ""
    return f"{prefix}{year}"


def discover_coco_jsons(dataset: Path, json_dir: Path | None) -> list[Path]:
    """发现 COCO instances JSON 文件。"""
    if json_dir:
        return sorted(json_dir.glob("*.json"))
    annot_dir = dataset / "annotations"
    if annot_dir.is_dir():
        files = sorted(annot_dir.glob("instances*.json"))
        if files:
            return files
    return sorted(dataset.glob("instances*.json"))


def discover_image_splits(dataset: Path) -> list[str]:
    """发现 images/ 下的 split 子目录（如 train2017、val2017）。"""
    img_root = dataset / "images"
    if not img_root.is_dir():
        return []
    splits = []
    for child in sorted(img_root.iterdir()):
        if child.is_dir() and any(p.suffix.lower() in IMAGE_EXTS for p in child.iterdir()):
            splits.append(child.name)
    return splits


def list_images(folder: Path) -> dict[str, str]:
    """stem -> filename"""
    out = {}
    if not folder.is_dir():
        return out
    for path in folder.iterdir():
        if path.suffix.lower() in IMAGE_EXTS:
            out[path.stem] = path.name
    return out


def convert_coco_json(
    json_path: Path,
    labels_dir: Path,
    task: str,
    split_name: str | None = None,
    write_empty: bool = False,
) -> dict:
    """单个 COCO JSON -> labels/（可写入 split 子目录）。"""
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    cat_map = build_category_map(data.get("categories", []))
    images = {img["id"]: img for img in data.get("images", [])}
    ann_fn = ann_to_detect if task == "detect" else ann_to_segment

    grouped: dict[str, list[list[float]]] = {}
    stats = {
        "images": len(images),
        "annotations": 0,
        "instances": 0,
        "skip_crowd": 0,
        "skip_empty": 0,
        "written": 0,
        "empty_written": 0,
        "categories": build_category_names(data.get("categories", [])),
    }

    out_root = labels_dir / split_name if split_name else labels_dir
    out_root.mkdir(parents=True, exist_ok=True)

    for ann in data.get("annotations", []):
        stats["annotations"] += 1
        if ann.get("iscrowd", 0) and task == "segment":
            stats["skip_crowd"] += 1
            continue

        img = images.get(ann["image_id"])
        if img is None:
            continue

        stem = Path(img["file_name"]).stem
        width, height = img["width"], img["height"]

        if task == "detect":
            row = ann_fn(ann, cat_map, width, height)
            rows = [row] if row is not None else []
        else:
            rows = ann_fn(ann, cat_map, width, height)

        if not rows:
            stats["skip_empty"] += 1
            continue

        grouped.setdefault(stem, []).extend(rows)
        stats["instances"] += len(rows)

    if write_empty:
        for img in images.values():
            stem = Path(img["file_name"]).stem
            if stem not in grouped:
                grouped[stem] = []
                stats["empty_written"] += 1

    for stem, instances in grouped.items():
        write_txt(out_root / f"{stem}.txt", instances)
        stats["written"] += 1

    return stats


def flatten_coco_splits(dataset: Path, splits: list[str]) -> dict:
    """将 images/{split}、labels/{split} 平铺，并按原 split 写 train.txt / val.txt。"""
    img_dir = dataset / "images"
    lbl_dir = dataset / "labels"

    train_stems: set[str] = set()
    val_stems: set[str] = set()
    moved = 0
    skipped_unpaired = 0

    for split in splits:
        split_lower = split.lower()
        if split_lower.startswith("train"):
            target_stems = train_stems
        elif split_lower.startswith("val"):
            target_stems = val_stems
        elif split_lower.startswith("test"):
            target_stems = set()
        else:
            target_stems = train_stems

        src_img = img_dir / split
        src_lbl = lbl_dir / split
        imgs = list_images(src_img)
        lbls = {p.stem: p.name for p in src_lbl.glob("*.txt")} if src_lbl.is_dir() else {}
        paired = set(imgs) & set(lbls)

        for stem in sorted(paired):
            shutil.move(str(src_img / imgs[stem]), str(img_dir / imgs[stem]))
            shutil.move(str(src_lbl / lbls[stem]), str(lbl_dir / lbls[stem]))
            target_stems.add(stem)
            moved += 1

        img_only = set(imgs) - paired
        skipped_unpaired += len(img_only)
        for stem in img_only:
            (src_img / imgs[stem]).unlink(missing_ok=True)

        if src_lbl.is_dir() and src_lbl.exists() and not any(src_lbl.iterdir()):
            src_lbl.rmdir()
        if src_img.exists() and not any(src_img.iterdir()):
            src_img.rmdir()

    def write_split(name: str, stems: set[str]) -> int:
        img_map = list_images(img_dir)
        lines = [f"./images/{img_map[stem]}" for stem in sorted(stems) if stem in img_map]
        (dataset / name).write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        return len(lines)

    train_n = write_split("train.txt", train_stems) if train_stems else 0
    val_n = write_split("val.txt", val_stems) if val_stems else 0

    return {
        "moved": moved,
        "skipped_unpaired": skipped_unpaired,
        "train": train_n,
        "val": val_n,
        "images": len(list_images(img_dir)),
        "labels": len({p.stem for p in lbl_dir.glob("*.txt")}),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="COCO instances JSON -> YOLO txt")
    parser.add_argument("--dataset", required=True, help="数据集根目录")
    parser.add_argument("--task", default="segment", choices=SUPPORTED_TASKS, help="detect=bbox, segment=polygon")
    parser.add_argument("--json-dir", default=None, help="COCO JSON 目录，默认 {dataset}/annotations")
    parser.add_argument("--labels-dir", default=None, help="labels 输出目录，默认 {dataset}/labels")
    parser.add_argument("--flatten", action="store_true", help="转换后平铺 images/labels 并写 train.txt/val.txt")
    parser.add_argument("--write-yaml", action="store_true", help="根据 COCO categories 生成 dataset.yaml")
    parser.add_argument("--write-empty", action="store_true", help="为 JSON 中无有效标注的图像写空 txt")
    return parser


def main(argv=None) -> None:
    args = build_parser().parse_args(argv)
    dataset = Path(args.dataset).resolve()
    labels_dir = Path(args.labels_dir) if args.labels_dir else dataset / "labels"
    json_files = discover_coco_jsons(dataset, Path(args.json_dir) if args.json_dir else None)

    if not json_files:
        raise SystemExit(f"未找到 COCO instances JSON: {dataset}")

    image_splits = discover_image_splits(dataset)
    split_map = {}
    for jf in json_files:
        split = infer_split_name(jf)
        if split and split in image_splits:
            split_map[jf] = split
        elif len(json_files) == 1 and len(image_splits) == 1:
            split_map[jf] = image_splits[0]
        else:
            split_map[jf] = split

    print(f"数据集: {dataset}")
    print(f"任务: {args.task}")
    print(f"JSON 文件: {len(json_files)}")
    print("-" * 50)

    total_written = 0
    category_names: list[str] = []
    for jf in json_files:
        split = split_map.get(jf)
        print(f"转换: {jf.name}" + (f" -> labels/{split}/" if split else " -> labels/"))
        stats = convert_coco_json(
            jf, labels_dir, args.task, split_name=split, write_empty=args.write_empty
        )
        total_written += stats["written"]
        if stats["categories"]:
            category_names = stats["categories"]
        empty_msg = f"，空标签 {stats['empty_written']}" if args.write_empty else ""
        print(
            f"  图像 {stats['images']}，标注 {stats['annotations']}，"
            f"写出 {stats['written']} 个 txt，实例 {stats['instances']}，"
            f"跳过 crowd {stats['skip_crowd']}，无效实例 {stats['skip_empty']}{empty_msg}"
        )

    if args.flatten:
        splits = image_splits or sorted({s for s in split_map.values() if s})
        if not splits:
            raise SystemExit("未找到 images/ 下的 split 子目录，无法 flatten")
        print("-" * 50)
        print(f"平铺 split: {', '.join(splits)}")
        flat_stats = flatten_coco_splits(dataset, splits)
        print(
            f"  移动 {flat_stats['moved']} 对，跳过无标注图 {flat_stats['skipped_unpaired']}，"
            f"train {flat_stats['train']} / val {flat_stats['val']}"
        )
        print(f"  images {flat_stats['images']}，labels {flat_stats['labels']}")

    if args.write_yaml and category_names:
        yaml_path = write_dataset_yaml(dataset, category_names, args.task)
        print("-" * 50)
        print(f"已生成 dataset.yaml: {yaml_path}（nc={len(category_names)}）")

    print("-" * 50)
    print(f"完成，共写出 {total_written} 个标签文件。")


if __name__ == "__main__":
    main()
