"""
# @Author: Yullin
# @Date: 2026-11-24
# @Description: 按定档结果去掉 grade=wrong 的框，写回 jsons-det-pre / jsons-seg-pre；不改原标注
# @Command: python util/label_filter.py --dataset /path --jsons jsons-det-pre-car --out jsons-det-pre-car
"""

from __future__ import annotations

import argparse
import json
import os
import sys

_PKG_ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)
_REPO = os.path.normpath(os.path.join(_PKG_ROOT, "..", "..", ".."))
_SERVER_UTIL = os.path.join(_REPO, "server", "util")
if _SERVER_UTIL not in sys.path:
    sys.path.insert(0, _SERVER_UTIL)

from common import (  # noqa: E402
    ensure_dir,
    load_json,
    resolve_images_dir,
    write_json,
)
from overlay import qa_jsons_dir, use_slug  # noqa: E402

# 视为误检的 grade
DROP_GRADES = {"wrong"}

# 旧结果里没有 grade 时的兼容判定
LEGACY_WRONG_KEYS = {"verdict": "wrong", "fit": "miss"}


def parse_args():
    p = argparse.ArgumentParser(
        description="按定档结果去掉误检框，写过滤后的 jsons。不改原标注目录。"
    )
    p.add_argument("--dataset", required=True, help="数据集根")
    p.add_argument("--jsons", required=True, help="源标注目录名，如 jsons-det-pre-car")
    p.add_argument("--out", default="", help="过滤结果写到哪个目录名；空则同 --jsons 加 -drop")
    p.add_argument("--slug", default="", help="定档产物的 slug，须与 label_grade 那次一致")
    p.add_argument("--part", default="", help="分段名，与 label_grade 一致")
    p.add_argument("--dry-run", action="store_true", help="只统计不写盘")
    return p.parse_args()


def is_wrong(item: dict) -> bool:
    """判定一条 shape 是否算误检。"""
    if not isinstance(item, dict):
        return False
    grade = str(item.get("grade") or "").strip().lower()
    if grade:
        return grade in DROP_GRADES
    # 没有 grade 时按旧口径
    for key, bad in LEGACY_WRONG_KEYS.items():
        if str(item.get(key) or "").strip().lower() == bad:
            return True
    return False


def filter_one(src_json: str, qa_json: str, out_path: str, dry_run: bool) -> dict:
    data = load_json(src_json, default={}) or {}
    shapes = data.get("shapes") if isinstance(data.get("shapes"), list) else []

    verdicts = {}
    if os.path.isfile(qa_json):
        qa = load_json(qa_json, default={}) or {}
        for it in qa.get("items") or []:
            try:
                idx = int(it.get("index"))
            except (TypeError, ValueError):
                continue
            verdicts[idx] = it

    kept, dropped = [], []
    for i, shape in enumerate(shapes):
        it = verdicts.get(i)
        if it is None:
            # 没判定的保留，不擅自删
            kept.append(shape)
            continue
        if is_wrong(it):
            dropped.append({"index": i, "label": shape.get("label"), "grade": it.get("grade") or ""})
        else:
            kept.append(shape)

    if not dry_run and dropped:
        out = dict(data)
        out["shapes"] = kept
        ensure_dir(os.path.dirname(out_path) or ".")
        write_json(out_path, out)

    return {
        "src": src_json,
        "out": out_path,
        "n_before": len(shapes),
        "n_after": len(kept),
        "n_dropped": len(dropped),
        "dropped": dropped,
        "has_verdict": os.path.isfile(qa_json),
    }


def main() -> int:
    args = parse_args()
    dataset_root = os.path.abspath(args.dataset)
    slug = use_slug(args.slug)
    part = str(args.part or "").strip() or None

    src_dir = os.path.join(dataset_root, args.jsons)
    if not os.path.isdir(src_dir):
        raise SystemExit(f"找不到源标注目录: {src_dir}")

    out_name = (args.out or "").strip() or f"{args.jsons}-drop"
    out_dir = os.path.join(dataset_root, out_name)
    qa_dir = qa_jsons_dir(dataset_root, slug, part)

    resolve_images_dir(dataset_root, "images")

    files = sorted(f for f in os.listdir(src_dir) if f.lower().endswith(".json"))
    if not files:
        print(f"{args.jsons}: 没有 json")
        return 0

    rows = []
    for fn in files:
        src_json = os.path.join(src_dir, fn)
        qa_json = os.path.join(qa_dir, fn)
        out_path = os.path.join(out_dir, fn)
        rows.append(filter_one(src_json, qa_json, out_path, args.dry_run))

    n_drop = sum(r["n_dropped"] for r in rows)
    n_before = sum(r["n_before"] for r in rows)
    n_after = sum(r["n_after"] for r in rows)
    no_verdict = sum(1 for r in rows if not r["has_verdict"])

    print(f"slug={slug} jsons={args.jsons} → {out_name}")
    print(f"  文件 {len(rows)} 张，框 {n_before} → {n_after}（去掉 {n_drop}）")
    if no_verdict:
        print(f"  注意：{no_verdict} 张没有定档结果，原样保留")
    if args.dry_run:
        print("  dry-run，未写盘")
    else:
        print(f"  写出 {out_dir}")

    # 逐张有删除的列出来
    for r in rows:
        if r["n_dropped"]:
            names = ", ".join(f"#{d['index']} {d['label']}" for d in r["dropped"][:6])
            more = "" if len(r["dropped"]) <= 6 else f" 等 {len(r['dropped'])} 个"
            print(f"  {os.path.basename(r['src'])}: -{r['n_dropped']}  {names}{more}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
