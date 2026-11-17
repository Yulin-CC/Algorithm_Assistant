"""
# @Author: Yullin
# @Date: 2026-09-11
# @Description: train/val 划分：YOLO images+labels，或 CD A/B/label
# @Command: python util/split.py --dataset /data --layout yolo --mode txt --split-ratio 0.9 --seed 42
# @Command: python util/split.py --dataset /data --layout cd --mode txt
"""

from __future__ import annotations

import argparse
import os
import random
import shutil
from os.path import join

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}
LABEL_TXT = {".txt"}
CD_LABEL_EXTS = (".png", ".jpg", ".jpeg")


def list_files(folder: str, exts: set) -> dict[str, str]:
    out = {}
    if not os.path.isdir(folder):
        return out
    for fn in os.listdir(folder):
        stem, ext = os.path.splitext(fn)
        if ext.lower() in exts:
            out[stem] = fn
    return out


def split_items(items: list, split_ratio: float, part_ratio: float, seed: int) -> tuple[list, list]:
    items = list(items)
    random.Random(int(seed)).shuffle(items)
    n = int(len(items) * part_ratio)
    items = items[:n] if n > 0 else items
    if len(items) <= 1:
        return items, []
    k = int(len(items) * split_ratio)
    k = max(1, min(k, len(items) - 1))
    return items[:k], items[k:]


def write_lines(path: str, lines: list[str]) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for ln in lines:
            f.write(ln + "\n")


def yolo_stems(data_dir: str) -> tuple[dict, dict, list[str]]:
    img_map = list_files(join(data_dir, "images"), IMAGE_EXTS)
    lab_map = list_files(join(data_dir, "labels"), LABEL_TXT)
    if not os.path.isdir(join(data_dir, "images")):
        raise SystemExit(f"无 images/: {data_dir}")
    if not os.path.isdir(join(data_dir, "labels")):
        raise SystemExit(f"无 labels/: {data_dir}")
    stems = sorted(set(img_map) & set(lab_map))
    return img_map, lab_map, stems


def cd_label_path(label_dir: str, img_name: str) -> str | None:
    p = join(label_dir, img_name)
    if os.path.isfile(p):
        return p
    stem, _ = os.path.splitext(img_name)
    for suf in CD_LABEL_EXTS:
        q = join(label_dir, stem + suf)
        if os.path.isfile(q):
            return q
        q = join(label_dir, stem + suf.upper())
        if os.path.isfile(q):
            return q
    return None


def cd_pairs(data_dir: str) -> list[str]:
    for sub in ("A", "B", "label"):
        if not os.path.isdir(join(data_dir, sub)):
            raise SystemExit(f"无 {sub}/: {data_dir}")
    a_dir, b_dir, lab_dir = join(data_dir, "A"), join(data_dir, "B"), join(data_dir, "label")
    out = []
    for fname in os.listdir(a_dir):
        if os.path.splitext(fname)[1].lower() not in IMAGE_EXTS:
            continue
        if not os.path.isfile(join(b_dir, fname)):
            continue
        if cd_label_path(lab_dir, fname) is None:
            continue
        out.append(fname)
    return sorted(out)


def run_yolo(data_dir: str, mode: str, split_ratio: float, part_ratio: float, seed: int) -> dict:
    img_map, lab_map, stems = yolo_stems(data_dir)
    train, val = split_items(stems, split_ratio, part_ratio, seed)
    if mode == "txt":
        write_lines(join(data_dir, "train.txt"), [f"./images/{img_map[s]}" for s in train])
        write_lines(join(data_dir, "val.txt"), [f"./images/{img_map[s]}" for s in val])
    else:
        base = join(data_dir, "for_training")
        for sp, group in (("train", train), ("val", val)):
            for sub in ("images", "labels"):
                os.makedirs(join(base, sp, sub), exist_ok=True)
            for s in group:
                shutil.copy2(join(data_dir, "images", img_map[s]), join(base, sp, "images", img_map[s]))
                shutil.copy2(join(data_dir, "labels", lab_map[s]), join(base, sp, "labels", lab_map[s]))
    return {"total": len(stems), "train": len(train), "val": len(val)}


def run_cd(data_dir: str, mode: str, split_ratio: float, part_ratio: float, seed: int) -> dict:
    names = cd_pairs(data_dir)
    train, val = split_items(names, split_ratio, part_ratio, seed)
    if mode == "txt":
        write_lines(join(data_dir, "train.txt"), train)
        write_lines(join(data_dir, "val.txt"), val)
    else:
        base = join(data_dir, "for_training")
        for sp, group in (("train", train), ("val", val)):
            for sub in ("A", "B", "label"):
                os.makedirs(join(base, sp, sub), exist_ok=True)
            for name in group:
                shutil.copy2(join(data_dir, "A", name), join(base, sp, "A", name))
                shutil.copy2(join(data_dir, "B", name), join(base, sp, "B", name))
                lab = cd_label_path(join(data_dir, "label"), name)
                shutil.copy2(lab, join(base, sp, "label", os.path.basename(lab)))
    return {"total": len(names), "train": len(train), "val": len(val)}


def parse_args():
    p = argparse.ArgumentParser(description="YOLO / CD train-val 划分")
    p.add_argument("--dataset", required=True)
    p.add_argument("--layout", required=True, choices=("yolo", "cd"))
    p.add_argument("--mode", default="txt", choices=("txt", "dir"))
    p.add_argument("--split-ratio", type=float, default=0.9)
    p.add_argument("--part-ratio", type=float, default=1.0)
    p.add_argument("--seed", type=int, default=42)
    return p.parse_args()


def main():
    args = parse_args()
    fn = run_yolo if args.layout == "yolo" else run_cd
    stats = fn(args.dataset, args.mode, args.split_ratio, args.part_ratio, args.seed)
    print(
        f"split {args.layout}/{args.mode} total={stats['total']} "
        f"train={stats['train']} val={stats['val']} → {args.dataset}"
    )


if __name__ == "__main__":
    main()
