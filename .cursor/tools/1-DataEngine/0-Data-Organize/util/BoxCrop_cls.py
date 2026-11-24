"""
# @Author: Yullin
# @Date: 2026-10-21
# @Description: 裁检测框到 img_crop/<类名>/，人工挪文件夹后回写 LabelMe json 或 YOLO txt
# @Command: python util/BoxCrop_cls.py --Path /data/set --status crop --format auto
"""

import argparse
import json
import os
import shutil
from os.path import join
from pathlib import Path

from PIL import Image
from tqdm import tqdm

IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff")
CROP_DIRNAME = "img_crop"


#-------------#
# 类别表
#-------------#
def load_id2name(yaml_path):
    import yaml

    with open(yaml_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    names = data["names"] if isinstance(data, dict) and "names" in data else data
    if isinstance(names, dict):
        return {int(k): str(v) for k, v in names.items()}
    return {i: str(n) for i, n in enumerate(names)}


def invert_id2name(id2name):
    return {v: k for k, v in id2name.items()}


#-------------#
# 格式与路径
#-------------#
def resolve_format(path, fmt):
    if fmt and fmt != "auto":
        return fmt
    if os.path.isdir(join(path, "jsons")):
        n = sum(1 for n in os.listdir(join(path, "jsons")) if n.endswith(".json"))
        if n:
            return "labelme"
    if os.path.isdir(join(path, "labels")):
        return "yolo"
    if os.path.isdir(join(path, "detect", "labels")):
        return "yolo"
    raise FileNotFoundError(f"Cannot detect format under {path}: need jsons/ or labels/")


def resolve_yolo_lbl_dir(path):
    if os.path.isdir(join(path, "labels")):
        return join(path, "labels")
    detect_lbl = join(path, "detect", "labels")
    if os.path.isdir(detect_lbl):
        return detect_lbl
    raise FileNotFoundError(f"No labels/ under {path}")


def find_image(img_dir, stem):
    for ext in IMAGE_EXTS:
        for candidate in (join(img_dir, stem + ext), join(img_dir, stem + ext.upper())):
            if os.path.isfile(candidate):
                return candidate
    return None


def infer_yaml(path, yaml_path):
    if yaml_path:
        return yaml_path
    candidate = join(path, "classes.yaml")
    return candidate if os.path.isfile(candidate) else None


#-------------#
# 框几何
#-------------#
def expand_xyxy(x1, y1, x2, y2, imgw, imgh, expand_ratio):
    cx = (x1 + x2) / 2
    cy = (y1 + y2) / 2
    ew = (x2 - x1) * expand_ratio
    eh = (y2 - y1) * expand_ratio
    x1e = int(max(0, cx - ew / 2))
    y1e = int(max(0, cy - eh / 2))
    x2e = int(min(imgw, cx + ew / 2))
    y2e = int(min(imgh, cy + eh / 2))
    return x1e, y1e, x2e, y2e


def save_crop(img, save_dir, savename, x1, y1, x2, y2, expand_ratio, imgw, imgh):
    x1e, y1e, x2e, y2e = expand_xyxy(x1, y1, x2, y2, imgw, imgh, expand_ratio)
    if x2e <= x1e or y2e <= y1e:
        print(f"\nWarning: Skip empty crop {savename} ({x1e},{y1e},{x2e},{y2e})")
        return False
    crop = img.crop([x1e, y1e, x2e, y2e])
    if crop.size[0] == 0 or crop.size[1] == 0:
        print(f"\nWarning: Skip empty image {savename} size={crop.size}")
        return False
    if crop.mode not in ("RGB", "L"):
        crop = crop.convert("RGB")
    os.makedirs(save_dir, exist_ok=True)
    crop.save(join(save_dir, savename))
    return True


def shape_xyxy(shape):
    points = shape.get("points") or []
    if len(points) < 2:
        return None
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    x1, x2 = min(xs), max(xs)
    y1, y2 = min(ys), max(ys)
    if x2 <= x1 or y2 <= y1:
        return None
    return x1, y1, x2, y2


#-------------#
# 裁图：按当前类名建文件夹
#-------------#
def crop_yolo(path, img_dir, lbl_dir, expand_ratio, id2name):
    save_folder = join(path, CROP_DIRNAME)
    count = 0
    for filename in tqdm(os.listdir(lbl_dir)):
        if not filename.endswith(".txt"):
            continue
        stem = Path(filename).stem
        img_path = find_image(img_dir, stem)
        if img_path is None:
            continue
        img = Image.open(img_path)
        imgw, imgh = img.size
        with open(join(lbl_dir, filename), "r", encoding="utf-8") as f:
            lines = f.readlines()
        for idx, line in enumerate(lines):
            parts = line.strip().split()
            if len(parts) != 5:
                continue
            cls_id = int(float(parts[0]))
            xc, yc, bw, bh = map(float, parts[1:5])
            cls_name = id2name.get(cls_id, str(cls_id)) if id2name else str(cls_id)
            x1 = (xc - bw / 2) * imgw
            y1 = (yc - bh / 2) * imgh
            x2 = (xc + bw / 2) * imgw
            y2 = (yc + bh / 2) * imgh
            savename = f"{stem}_{idx:02d}.jpg"
            if save_crop(img, join(save_folder, cls_name), savename, x1, y1, x2, y2, expand_ratio, imgw, imgh):
                count += 1
    print(f"\nCrop {count} images in total.\n")


def crop_labelme(path, img_dir, json_dir, expand_ratio):
    save_folder = join(path, CROP_DIRNAME)
    count = 0
    for filename in tqdm(os.listdir(json_dir)):
        if not filename.endswith(".json"):
            continue
        json_path = join(json_dir, filename)
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
        stem = Path(data.get("imagePath") or filename).stem
        img_path = find_image(img_dir, stem)
        if img_path is None:
            img_path = find_image(img_dir, Path(filename).stem)
        if img_path is None:
            continue
        img = Image.open(img_path)
        imgw, imgh = img.size
        for idx, shape in enumerate(data.get("shapes") or []):
            xyxy = shape_xyxy(shape)
            if xyxy is None:
                continue
            cls_name = str(shape.get("label") or "unknown")
            savename = f"{stem}_{idx:02d}.jpg"
            if save_crop(img, join(save_folder, cls_name), savename, *xyxy, expand_ratio, imgw, imgh):
                count += 1
    print(f"\nCrop {count} images in total.\n")


#-------------#
# 按文件夹找新类
#-------------#
def lookup_crop_folder(crop_dir, filename):
    hits = []
    if not os.path.isdir(crop_dir):
        return None
    for folder in os.listdir(crop_dir):
        folder_path = join(crop_dir, folder)
        if not os.path.isdir(folder_path):
            continue
        if os.path.isfile(join(folder_path, filename)):
            hits.append(folder)
    if len(hits) > 1:
        print(f"\nWarning: {filename} found in multiple folders {hits}, use {hits[0]}")
    if not hits:
        return None
    folder = hits[0]
    if folder.startswith("_"):
        return None
    return folder


def folder_to_yolo_id(folder, name2id):
    if name2id and folder in name2id:
        return name2id[folder]
    try:
        return int(float(folder))
    except ValueError:
        raise ValueError(
            f"Folder '{folder}' is not a class id and not in classes.yaml; "
            "add the name to yaml or use numeric folder names"
        )


#-------------#
# 回写标签
#-------------#
def update_yolo(path, src_dir, id2name):
    crop_dir = join(path, CROP_DIRNAME)
    tgt_dir = join(path, "labels_new")
    name2id = invert_id2name(id2name) if id2name else {}
    assert os.path.isdir(src_dir)
    assert os.path.isdir(crop_dir)
    os.makedirs(tgt_dir, exist_ok=True)

    count = 0
    for filename in tqdm(os.listdir(src_dir)):
        if not filename.endswith(".txt"):
            continue
        stem = Path(filename).stem
        with open(join(src_dir, filename), "r", encoding="utf-8") as f:
            lines = f.readlines()
        out_lines = []
        for idx, line in enumerate(lines):
            raw = line.strip()
            if not raw:
                continue
            parts = raw.split()
            if len(parts) != 5:
                continue
            rest = parts[1:5]
            crop_name = f"{stem}_{idx:02d}.jpg"
            folder = lookup_crop_folder(crop_dir, crop_name)
            if folder is None:
                continue
            cls_new = folder_to_yolo_id(folder, name2id)
            out_lines.append(f"{cls_new} {' '.join(rest)}\n")
            count += 1
        with open(join(tgt_dir, filename), "w", encoding="utf-8") as f:
            f.writelines(out_lines)

    dest = join(path, "labels")
    if os.path.isdir(dest):
        shutil.rmtree(dest)
    os.replace(tgt_dir, dest)
    print(f"\nUpdate {count} labels in total -> {dest}\n")


def update_labelme(path, json_dir):
    crop_dir = join(path, CROP_DIRNAME)
    assert os.path.isdir(json_dir)
    assert os.path.isdir(crop_dir)

    count = 0
    kept_files = 0
    for filename in tqdm(os.listdir(json_dir)):
        if not filename.endswith(".json"):
            continue
        json_path = join(json_dir, filename)
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
        stem = Path(data.get("imagePath") or filename).stem
        new_shapes = []
        for idx, shape in enumerate(data.get("shapes") or []):
            crop_name = f"{stem}_{idx:02d}.jpg"
            folder = lookup_crop_folder(crop_dir, crop_name)
            if folder is None:
                continue
            shape["label"] = folder
            new_shapes.append(shape)
            count += 1
        data["shapes"] = new_shapes
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        kept_files += 1
    print(f"\nUpdate {count} shapes in {kept_files} jsons.\n")


#-------------#
# 参数
#-------------#
def parse_opt():
    parser = argparse.ArgumentParser(description="Crop boxes for class-folder relabel, then write back.")
    parser.add_argument("--Path", required=True, help="Dataset root (images/ + jsons/ or labels/)")
    parser.add_argument("--status", type=str, default="crop", choices=["crop", "update"], help="crop or update")
    parser.add_argument("--format", type=str, default="auto", choices=["auto", "labelme", "yolo"])
    parser.add_argument("--yaml", type=str, default="", help="classes.yaml for YOLO name folders (optional)")
    parser.add_argument("--expand_ratio", type=float, default=1.5)
    return parser.parse_args()


if __name__ == "__main__":
    opt = parse_opt()
    path = opt.Path
    img_dir = join(path, "images")
    fmt = resolve_format(path, opt.format)
    yaml_path = infer_yaml(path, opt.yaml or None)
    id2name = load_id2name(yaml_path) if yaml_path else {}
    if yaml_path:
        print(f"classes.yaml: {yaml_path}")
    print(f"format={fmt}  status={opt.status}")

    if opt.status == "crop":
        if fmt == "yolo":
            crop_yolo(path, img_dir, resolve_yolo_lbl_dir(path), opt.expand_ratio, id2name)
        else:
            crop_labelme(path, img_dir, join(path, "jsons"), opt.expand_ratio)
    elif opt.status == "update":
        if fmt == "yolo":
            update_yolo(path, resolve_yolo_lbl_dir(path), id2name)
        else:
            update_labelme(path, join(path, "jsons"))
