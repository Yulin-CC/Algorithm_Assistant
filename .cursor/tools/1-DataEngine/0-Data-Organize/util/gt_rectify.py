"""
# @Author: 算法组
# @Date: 2026-09-27
# @Description: 把未命中预测裁到真误检；人工放入假误检后，追加为真值里的 _m 弱标签
# @Command: python util/gt_rectify.py dump --gt-dir <gt> --pre-dir <pre> --images <images> --out <误检目录>
# @Command: python util/gt_rectify.py apply --out <误检目录> --dry-run
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from square_crop import crop_square, read_image, save_image
from weak_label_report import WEAK_SUFFIX, box_iou, box_of, judge, load_alias, load_shapes, split_label

PRE_BGR = (144, 238, 144)
IMG_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}


def list_images(images_dir: Path) -> dict[str, Path]:
    found = {}
    if not images_dir.is_dir():
        return found
    for path in images_dir.iterdir():
        if path.suffix.lower() in IMG_EXTS:
            found[path.stem] = path
    return found


def resolve_image(gt_json: Path, images: dict[str, Path]) -> Path | None:
    if gt_json.stem in images:
        return images[gt_json.stem]
    try:
        meta = json.loads(gt_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    raw = meta.get("imagePath") or ""
    if not raw:
        return None
    candidate = (gt_json.parent / raw).resolve()
    if candidate.is_file():
        return candidate
    return images.get(Path(str(raw).replace("\\", "/")).stem)


def rect_points(box: tuple) -> list:
    x1, y1, x2, y2 = [float(v) for v in box]
    return [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]


def weak_shape(base: str, box: tuple) -> dict:
    return {
        "label": f"{base}{WEAK_SUFFIX}",
        "points": rect_points(box),
        "group_id": None,
        "description": "weak",
        "difficult": False,
        "shape_type": "rectangle",
        "flags": {},
    }


#-------------#
# 导出真误检
#-------------#
def dump_fp(gt_dir: Path, pre_dir: Path, images_dir: Path, out_dir: Path, alias: dict, thr: float, expand: float) -> None:
    fake_dir = out_dir / "假误检"
    if any(fake_dir.rglob("*.jpg")):
        raise SystemExit(f"假误检里已有挑选结果，停止重刷: {fake_dir}")
    true_dir = out_dir / "真误检"
    if true_dir.exists():
        shutil.rmtree(true_dir)
    images = list_images(images_dir)
    index = {"iou": thr, "expand": expand, "items": {}}
    counts = {}
    missing = 0
    for gt_json in sorted(gt_dir.glob("*.json")):
        image_path = resolve_image(gt_json, images)
        if image_path is None:
            missing += 1
            continue
        image = read_image(image_path)
        if image is None:
            missing += 1
            continue
        pre_json = pre_dir / gt_json.name
        gts = load_shapes(gt_json, alias)
        preds = load_shapes(pre_json, alias) if pre_json.is_file() else []
        _tp, fps, _miss = judge(gts, preds, thr)
        for order, pred in enumerate(fps, start=1):
            folder = f"cls-{pred['label']}"
            name = f"{gt_json.stem}_{order}.jpg"
            rel = f"{folder}/{name}"
            save_image(out_dir / "真误检" / rel, crop_square(image, pred["box"], expand, PRE_BGR))
            index["items"][rel] = {
                "gt_json": str(gt_json.resolve()),
                "label": pred["label"],
                "base": pred["base"],
                "box": [float(v) for v in pred["box"]],
            }
            counts[pred["label"]] = counts.get(pred["label"], 0) + 1
    fake_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    print("真误检", sum(counts.values()), counts)
    print("缺图", missing)
    print("目录", out_dir)


#-------------#
# 写回弱标签
#-------------#
def apply_weak(out_dir: Path, dry_run: bool) -> None:
    index_path = out_dir / "index.json"
    if not index_path.is_file():
        raise SystemExit(f"缺少索引: {index_path}")
    index = json.loads(index_path.read_text(encoding="utf-8"))
    picked = sorted((out_dir / "假误检").rglob("*.jpg"))
    if not picked:
        raise SystemExit(f"假误检为空: {out_dir / '假误检'}")
    pending = {}
    for path in picked:
        rel = path.relative_to(out_dir / "假误检").as_posix()
        item = index["items"].get(rel)
        if item is None:
            raise SystemExit(f"索引里没有这张图，请保持 cls 目录和文件名: {rel}")
        pending.setdefault(item["gt_json"], []).append(item)
    added = skipped = 0
    for gt_path, items in sorted(pending.items()):
        gt_json = Path(gt_path)
        meta = json.loads(gt_json.read_text(encoding="utf-8"))
        shapes = meta.setdefault("shapes", [])
        existing = []
        for shape in shapes:
            base, weak = split_label(str(shape.get("label") or ""), {})
            if weak:
                existing.append((base, box_of(shape)))
        for item in items:
            box = tuple(item["box"])
            base = item["base"]
            if any(old_base == base and box_iou(box, old_box) > 0.9 for old_base, old_box in existing):
                skipped += 1
                continue
            shapes.append(weak_shape(base, box))
            existing.append((base, box))
            added += 1
        if not dry_run:
            gt_json.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(("将写入" if dry_run else "已写入"), added, "跳过重复", skipped, "涉及 json", len(pending))


def parse_args():
    parser = argparse.ArgumentParser(description="真误检落盘，假误检写回弱标签")
    sub = parser.add_subparsers(dest="cmd", required=True)
    dump = sub.add_parser("dump")
    dump.add_argument("--gt-dir", required=True)
    dump.add_argument("--pre-dir", required=True)
    dump.add_argument("--images", required=True)
    dump.add_argument("--out", required=True, help=".../误检 目录，其下生成真误检、假误检、index.json")
    dump.add_argument("--alias", default="")
    dump.add_argument("--iou", type=float, default=0.30)
    dump.add_argument("--expand", type=float, default=2.0)
    apply = sub.add_parser("apply")
    apply.add_argument("--out", required=True)
    apply.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    if args.cmd == "dump":
        dump_fp(
            Path(args.gt_dir),
            Path(args.pre_dir),
            Path(args.images),
            Path(args.out),
            load_alias(args.alias or None),
            args.iou,
            args.expand,
        )
        return
    apply_weak(Path(args.out), args.dry_run)


if __name__ == "__main__":
    main()
