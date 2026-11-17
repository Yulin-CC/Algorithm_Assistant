#!/usr/bin/env python3
"""
# @Author: 算法组
# @Date: 2026-07-15
# @Description: 扫描 N+1 任务子集 YOLO 标签，核对基类覆盖，并输出子集概况 / 类别 pos-neg 表。
#
# @Command: python util/yolo_check_label.py --root /path/to/data --base 基类M.yaml --names classes.yaml
# @Command: python util/yolo_check_label.py --root /path/to/data --base 基类M.txt --names classes.yaml --save ./out
"""

import argparse
import os
import re
import sys
from collections import defaultdict
from os.path import join

# ==============================
# 接口配置
# ==============================
ROOT_DIR = "/path/to/data"
BASE_PATH = None          # 基类 M 列表：yaml / txt
NAMES_PATH = None         # 全量 id→name（classes.yaml 或 YOLO data yaml）；缺省时用 --base
COLLECTION = "collection" # 金标小合集文件夹名
SAVE_DIR = None           # 可选：保存 markdown 表
# ==============================

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}
CJK_RE = re.compile(r"[\u4e00-\u9fff]")


#-------------#
# 加载名称列表
#-------------#
def load_name_list(path: str) -> list:
    """加载类别名列表；支持 yaml names 字典/列表，或 txt 每行一类。"""
    if not path or not os.path.isfile(path):
        raise FileNotFoundError(f"类别文件不存在: {path}")

    if path.lower().endswith((".yaml", ".yml")):
        try:
            import yaml
        except ImportError as exc:
            raise ImportError("读取 yaml 需要 PyYAML：pip install pyyaml") from exc
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if data is None:
            return []
        names = data.get("names", data) if isinstance(data, dict) else data
        if isinstance(names, dict):
            return [names[k] for k in sorted(names, key=lambda x: int(x))]
        return [str(x).strip() for x in names if str(x).strip()]

    names = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            names.append(s)
    return names


#-------------#
# 发现任务子集
#-------------#
def discover_subsets(root: str) -> list:
    """根目录下一层含 images/ 或 labels/ 的文件夹，视为任务子集。"""
    if not os.path.isdir(root):
        raise FileNotFoundError(f"根目录不存在: {root}")
    subs = []
    for name in sorted(os.listdir(root)):
        path = join(root, name)
        if not os.path.isdir(path):
            continue
        if os.path.isdir(join(path, "images")) or os.path.isdir(join(path, "labels")):
            subs.append(name)
    return subs


#-------------#
# 列举文件 stem
#-------------#
def list_stems(folder: str, exts: set) -> set:
    """返回目录下指定后缀文件的 stem 集合。"""
    out = set()
    if not os.path.isdir(folder):
        return out
    for fn in os.listdir(folder):
        stem, ext = os.path.splitext(fn)
        if ext.lower() in exts:
            out.add(stem)
    return out


#-------------#
# 统计单子集标签
#-------------#
def analyze_subset(subset_dir: str, id2name: dict) -> dict:
    """统计单子集图像/标签/类别；返回结构化结果。"""
    img_dir = join(subset_dir, "images")
    lbl_dir = join(subset_dir, "labels")
    img_stems = list_stems(img_dir, IMAGE_EXTS)
    lbl_stems = list_stems(lbl_dir, {".txt"})

    paired = img_stems & lbl_stems
    only_img = img_stems - lbl_stems
    only_lbl = lbl_stems - img_stems
    denom = max(len(img_stems), len(lbl_stems), 1)
    match_rate = len(paired) / denom

    class_files = defaultdict(int)   # name -> 含该类的标签文件数
    class_boxes = defaultdict(int)   # name -> 框数
    unknown_ids = defaultdict(int)   # id -> 出现次数
    chinese_names = set()
    total_boxes = 0

    for stem in sorted(lbl_stems):
        path = join(lbl_dir, f"{stem}.txt")
        present = set()
        with open(path, encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) < 5:
                    continue
                try:
                    cid = int(float(parts[0]))
                except ValueError:
                    continue
                total_boxes += 1
                if cid not in id2name:
                    unknown_ids[cid] += 1
                    continue
                name = id2name[cid]
                if CJK_RE.search(name):
                    chinese_names.add(name)
                class_boxes[name] += 1
                present.add(name)
        for name in present:
            class_files[name] += 1

    return {
        "n_images": len(img_stems),
        "n_labels": len(lbl_stems),
        "n_paired": len(paired),
        "n_only_img": len(only_img),
        "n_only_lbl": len(only_lbl),
        "match_rate": match_rate,
        "class_files": dict(class_files),
        "class_boxes": dict(class_boxes),
        "classes": sorted(class_boxes.keys()),
        "unknown_ids": dict(unknown_ids),
        "chinese_names": sorted(chinese_names),
        "total_boxes": total_boxes,
    }


#-------------#
# 构建表格行
#-------------#
def build_tables(subsets: dict, base_names: list, collection: str) -> tuple:
    """构建子集概况表、类别 pos/neg 表，以及 collection 覆盖检查结果。"""
    subset_rows = []
    for i, (name, info) in enumerate(subsets.items(), 1):
        subset_rows.append({
            "idx": i,
            "subset": name,
            "n_images": info["n_images"],
            "n_labels": info["n_labels"],
            "match_rate": f"{info['match_rate'] * 100:.1f}%",
            "classes": ", ".join(info["classes"]) if info["classes"] else "-",
        })

    class_rows = []
    for i, c_i in enumerate(base_names, 1):
        pos, neg = [], []
        n_boxes = 0
        for sname, info in subsets.items():
            n = info["class_boxes"].get(c_i, 0)
            n_boxes += n
            if n > 0:
                pos.append(sname)
            else:
                neg.append(sname)
        class_rows.append({
            "idx": i,
            "class": c_i,
            "n_boxes": n_boxes,
            "pos": ", ".join(pos) if pos else "-",
            "neg": ", ".join(neg) if neg else "-",
        })

    coll = subsets.get(collection)
    if coll is None:
        cover_ok = False
        missing = list(base_names)
        cover_msg = f"❌ 未找到 collection 文件夹: {collection}"
    else:
        have = set(coll["classes"])
        missing = [c for c in base_names if c not in have]
        cover_ok = len(missing) == 0
        cover_msg = (
            f"✅ collection 已覆盖全部 M={len(base_names)} 基类"
            if cover_ok
            else f"❌ collection 缺少基类: {', '.join(missing)}"
        )

    return subset_rows, class_rows, cover_ok, missing, cover_msg


#-------------#
# 打印 markdown 表
#-------------#
def print_md_table(headers: list, rows: list, keys: list):
    """向 stdout 打印 markdown 表格。"""
    print("| " + " | ".join(headers) + " |")
    print("| " + " | ".join(["---"] * len(headers)) + " |")
    for row in rows:
        print("| " + " | ".join(str(row[k]) for k in keys) + " |")


#-------------#
# 保存 markdown
#-------------#
def save_tables(save_dir: str, subset_rows: list, class_rows: list, cover_msg: str):
    """将两张表写入 save_dir。"""
    os.makedirs(save_dir, exist_ok=True)
    path = join(save_dir, "yolo_check_label_report.md")
    lines = [
        "# yolo_check_label 报告\n",
        f"\n{cover_msg}\n",
        "\n## 子集概况\n\n",
        "| 序号 | N+1 任务子集 | 图像数据量 | 标签数据量 | 对齐率 | 全部类别 |\n",
        "| --- | --- | --- | --- | --- | --- |\n",
    ]
    for r in subset_rows:
        lines.append(
            f"| {r['idx']} | {r['subset']} | {r['n_images']} | {r['n_labels']} "
            f"| {r['match_rate']} | {r['classes']} |\n"
        )
    lines += [
        "\n## 类别_数据集\n\n",
        "| 序号 | 类别 C_i | 样本个数(框) | pos 任务子集 | neg 任务子集 |\n",
        "| --- | --- | --- | --- | --- |\n",
    ]
    for r in class_rows:
        lines.append(
            f"| {r['idx']} | {r['class']} | {r['n_boxes']} | {r['pos']} | {r['neg']} |\n"
        )
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(lines)
    print(f"\n📄 已保存: {path}")


#-------------#
# 参数
#-------------#
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="检查 YOLO 子集标签与基类覆盖，输出 pos/neg 表")
    p.add_argument("--root", default=ROOT_DIR, help="数据集根目录（含 N 子集 + collection）")
    p.add_argument("--base", default=BASE_PATH, required=BASE_PATH is None, help="基类 M 文件 yaml/txt")
    p.add_argument("--names", default=NAMES_PATH, help="全量 id→name；缺省则用 --base")
    p.add_argument("--collection", default=COLLECTION, help="金标小合集文件夹名")
    p.add_argument("--save", default=SAVE_DIR, help="可选，保存 markdown 报告目录")
    return p


#-------------#
# 主流程
#-------------#
def main(argv=None):
    args = build_parser().parse_args(argv)
    #----------------------------#
    root = args.root                    # 数据集根目录
    base_path = args.base               # 基类 M
    names_path = args.names or base_path
    collection = args.collection        # collection 名
    save_dir = args.save                # 报告目录
    #----------------------------#

    print(f"根目录     : {root}")
    print(f"基类文件   : {base_path}")
    print(f"名称映射   : {names_path}")
    print(f"collection : {collection}")
    print("-" * 60)

    base_names = load_name_list(base_path)
    all_names = load_name_list(names_path)
    if not base_names:
        print("❌ 基类列表为空")
        sys.exit(1)
    if not all_names:
        print("❌ 名称映射为空")
        sys.exit(1)

    id2name = {i: n for i, n in enumerate(all_names)}
    missing_in_names = [c for c in base_names if c not in all_names]
    if missing_in_names:
        print(f"⚠️ 基类未出现在 names 中: {', '.join(missing_in_names)}")

    chinese_in_vocab = [n for n in all_names if CJK_RE.search(n)]
    if chinese_in_vocab:
        print(f"⚠️ 类别名含中文: {', '.join(chinese_in_vocab)}")

    subset_names = discover_subsets(root)
    if not subset_names:
        print("❌ 未发现任何含 images/ 或 labels/ 的子集")
        sys.exit(1)
    print(f"发现子集 {len(subset_names)} 个: {', '.join(subset_names)}")

    subsets = {}
    for sname in subset_names:
        info = analyze_subset(join(root, sname), id2name)
        subsets[sname] = info
        if info["unknown_ids"]:
            unk = ", ".join(f"{k}:{v}" for k, v in sorted(info["unknown_ids"].items()))
            print(f"  ⚠️ [{sname}] 未知 class id → {unk}")
        if info["chinese_names"]:
            print(f"  ⚠️ [{sname}] 中文类名 → {', '.join(info['chinese_names'])}")

    subset_rows, class_rows, cover_ok, missing, cover_msg = build_tables(
        subsets, base_names, collection
    )

    print("\n## 子集概况")
    print_md_table(
        ["序号", "N+1 任务子集", "图像数据量", "标签数据量", "对齐率", "全部类别"],
        subset_rows,
        ["idx", "subset", "n_images", "n_labels", "match_rate", "classes"],
    )

    print("\n## 类别_数据集")
    print_md_table(
        ["序号", "类别 C_i", "样本个数(框)", "pos 任务子集", "neg 任务子集"],
        class_rows,
        ["idx", "class", "n_boxes", "pos", "neg"],
    )

    print("\n" + cover_msg)
    if save_dir:
        save_tables(save_dir, subset_rows, class_rows, cover_msg)

    print("-" * 60)
    if not cover_ok:
        print(f"⛔ 强约束未满足，缺少: {', '.join(missing)}")
        sys.exit(2)
    print("完成！")


if __name__ == "__main__":
    main()
