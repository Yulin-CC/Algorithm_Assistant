"""
# @Author: Yullin
# @Date: 2026-08-05
# @Description: 合并 jsons-det（rectangle）与 jsons-segm（polygon）为 jsons/，同文件保留两类 shape
# @Command: python util/merge_jsons_det_segm.py --dataset /path/to/data
"""

import argparse
import json
from pathlib import Path

from tqdm import tqdm


#-------------#
# 读取 LabelMe
#-------------#
def load_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


#-------------#
# 按类型取 shape
#-------------#
def shapes_of_type(shapes: list[dict], shape_type: str) -> list[dict]:
    want = shape_type.lower()
    return [s for s in (shapes or []) if (s.get("shape_type") or "").lower() == want]


#-------------#
# 合并单文件
#-------------#
def merge_one(det_path: Path | None, seg_path: Path | None) -> dict | None:
    if det_path is None and seg_path is None:
        return None

    det = load_json(det_path) if det_path else None
    seg = load_json(seg_path) if seg_path else None
    base = det or seg

    rects = shapes_of_type(det.get("shapes", []), "rectangle") if det else []
    polys = shapes_of_type(seg.get("shapes", []), "polygon") if seg else []

    out = {
        "version": base.get("version", "0.1.4"),
        "flags": base.get("flags", {}),
        "shapes": rects + polys,
        "imagePath": base.get("imagePath") or (seg or {}).get("imagePath", ""),
        "imageData": None,
        "imageHeight": base.get("imageHeight"),
        "imageWidth": base.get("imageWidth"),
        "text": base.get("text", ""),
    }

    if det and seg:
        if (seg.get("imageHeight"), seg.get("imageWidth")) != (out["imageHeight"], out["imageWidth"]):
            print(
                f"  ⚠️  尺寸不一致 {det_path.stem}: "
                f"det=({out['imageWidth']}x{out['imageHeight']}) "
                f"seg=({seg.get('imageWidth')}x{seg.get('imageHeight')})"
            )
    return out


#-------------#
# 批量合并
#-------------#
def merge_dirs(det_dir: Path, seg_dir: Path, out_dir: Path) -> dict:
    det_dir, seg_dir, out_dir = Path(det_dir), Path(seg_dir), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    stems = sorted(
        {p.stem for p in det_dir.glob("*.json")} | {p.stem for p in seg_dir.glob("*.json")}
    )
    stats = {"total": 0, "ok": 0, "n_rect": 0, "n_poly": 0, "only_det": 0, "only_seg": 0}

    for stem in tqdm(stems, desc="merge-det-segm"):
        stats["total"] += 1
        dp, sp = det_dir / f"{stem}.json", seg_dir / f"{stem}.json"
        det_path = dp if dp.is_file() else None
        seg_path = sp if sp.is_file() else None
        if det_path and not seg_path:
            stats["only_det"] += 1
        if seg_path and not det_path:
            stats["only_seg"] += 1

        merged = merge_one(det_path, seg_path)
        if merged is None:
            continue
        with open(out_dir / f"{stem}.json", "w", encoding="utf-8") as f:
            json.dump(merged, f, ensure_ascii=False, indent=2)
        stats["ok"] += 1
        stats["n_rect"] += sum(1 for s in merged["shapes"] if s.get("shape_type") == "rectangle")
        stats["n_poly"] += sum(1 for s in merged["shapes"] if s.get("shape_type") == "polygon")

    return stats


#-------------#
# 参数
#-------------#
def parse_args():
    p = argparse.ArgumentParser(description="合并 jsons-det + jsons-segm → jsons")
    p.add_argument("--dataset", required=True, help="数据集根目录")
    p.add_argument("--det-dir", default=None, help="检测 json 目录，默认 <dataset>/jsons-det-pre")
    p.add_argument("--seg-dir", default=None, help="分割 json 目录，默认 <dataset>/jsons-seg-pre")
    p.add_argument("--out-dir", default=None, help="输出目录，默认 <dataset>/jsons")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    dataset = Path(args.dataset)
    det_dir = Path(args.det_dir) if args.det_dir else dataset / "jsons-det-pre"
    seg_dir = Path(args.seg_dir) if args.seg_dir else dataset / "jsons-seg-pre"
    out_dir = Path(args.out_dir) if args.out_dir else dataset / "jsons"

    if not det_dir.is_dir() and not seg_dir.is_dir():
        raise FileNotFoundError(f"缺少 {det_dir} 与 {seg_dir}")

    stats = merge_dirs(det_dir, seg_dir, out_dir)
    print(
        f"合并完成: {stats['ok']}/{stats['total']} → {out_dir}\n"
        f"  rectangle {stats['n_rect']}，polygon {stats['n_poly']}；"
        f"仅 det {stats['only_det']}，仅 seg {stats['only_seg']}"
    )
