"""
# @Author: 算法组
# @Date: 2026-07-11
# @Description: 由 COCO Grounding segm json 生成训练用 .cache（须 ultralytics）。
# @Command: python util/grounding_generate_cache.py --json-path /path/to/train_segm.json --img-path /path/to/images
"""

import json
import os
from argparse import ArgumentParser
from pathlib import Path

import numpy as np
from tqdm import tqdm
from ultralytics.data.converter import merge_multi_segment
from ultralytics.utils.ops import segments2boxes, xyxy2xywhn


def count_instances(labels: list) -> int:
    instance_count = sum(label["bboxes"].shape[0] for label in labels)
    print(f"Instance count: {instance_count}")
    return instance_count


def generate_cache(json_path: str | Path, img_path: str | Path) -> list:
    labels = []
    with open(json_path, encoding="utf-8") as f:
        annotations = json.load(f)
    images = {f'{x["id"]:d}': x for x in annotations["images"]}

    img_to_anns = {int(k): [] for k in images.keys()}
    for ann in annotations["annotations"]:
        img_to_anns[ann["image_id"]].append(ann)

    for img_id, anns in tqdm(img_to_anns.items()):
        img = images[f"{img_id:d}"]
        h, w, f = int(img["height"]), int(img["width"]), img["file_name"]
        im_file = Path(img_path) / f
        if not im_file.exists():
            continue
        bboxes = []
        segments = []
        cat2id = {}
        texts = []
        for ann in anns:
            if ann.get("iscrowd"):
                continue
            box = np.array(ann["bbox"], dtype=np.float64)
            box[2] += box[0]
            box[3] += box[1]
            box = xyxy2xywhn(box, w=float(w), h=float(h), clip=True)
            if box[2] <= 0 or box[3] <= 0:
                continue

            cat_name = " ".join(
                img["caption"][t[0] : t[1]] for t in ann["tokens_positive"]
            ).lower().strip()
            if not cat_name:
                continue

            if cat_name not in cat2id:
                cat2id[cat_name] = len(cat2id)
                texts.append([cat_name])
            cls = cat2id[cat_name]
            row = [cls] + box.tolist()
            if row not in bboxes:
                bboxes.append(row)
                seg_data = ann.get("segmentation")
                if not seg_data:
                    continue
                if len(seg_data) > 1:
                    merged = merge_multi_segment(seg_data)
                    s = (np.concatenate(merged, axis=0) / np.array([w, h])).reshape(-1).tolist()
                else:
                    s = [j for i in seg_data for j in i]
                    s = (np.array(s).reshape(-1, 2) / np.array([w, h])).reshape(-1).tolist()
                segments.append([cls] + s)

        lb = np.array(bboxes, dtype=np.float32) if bboxes else np.zeros((0, 5), dtype=np.float32)
        seg_arrays = []
        if segments:
            classes = np.array([x[0] for x in segments], dtype=np.float32)
            seg_arrays = [np.array(x[1:], dtype=np.float32).reshape(-1, 2) for x in segments]
            lb = np.concatenate((classes.reshape(-1, 1), segments2boxes(seg_arrays)), 1)
        lb = np.array(lb, dtype=np.float32)

        labels.append(
            {
                "im_file": im_file,
                "shape": (h, w),
                "cls": lb[:, 0:1],
                "bboxes": lb[:, 1:],
                "segments": seg_arrays if segments else [],
                "normalized": True,
                "bbox_format": "xywh",
                "texts": texts,
            }
        )

    count_instances(labels)
    cache_path = Path(json_path).with_suffix(".cache")
    np.save(str(cache_path), labels)
    npy_path = cache_path.with_suffix(".cache.npy")
    if npy_path.exists():
        npy_path.rename(cache_path)
    print(f"Save cache → {cache_path}")
    return labels


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(description="Grounding segm json → .cache（需 yoloe + ultralytics）")
    parser.add_argument("--json-path", required=True, help="xxx_train_segm.json 路径")
    parser.add_argument("--img-path", required=True, help="images/ 目录路径")
    return parser


def main(argv=None):
    os.environ["PYTHONHASHSEED"] = "0"
    args = build_parser().parse_args(argv)
    generate_cache(args.json_path, args.img_path)


if __name__ == "__main__":
    main()
