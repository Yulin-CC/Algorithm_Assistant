"""
# @Author: Yullin
# @Date: 2026-11-10
# @Description: 汇总定档里的误检、不贴合，以及已有的漏检定位。不改标注，不再问模型。
# @Command: python util/analysis.py --dataset /path --pred jsons-seg-pre --gt jsons
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_PKG_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
_REPO = os.path.normpath(os.path.join(_PKG_ROOT, "..", "..", ".."))
_MODEL_UTIL = os.path.join(_REPO, "model", "util")
if _MODEL_UTIL not in sys.path:
    sys.path.insert(0, _MODEL_UTIL)

from common import load_json, task_result, task_vis, write_json
from label_grade import ensure_views, item_grade, run_change, run_dataset
from label_miss import MISS_SLUG
from overlay import cd_layout, qa_jsons_dir, resolve_jsons_dir

ANALYSIS_SLUG = "analysis"
PRED_PART = "pred"
GT_PART = "gt"
SAMPLE_N = 3


def result_dir(dataset_root: str) -> str:
    return task_result(dataset_root, ANALYSIS_SLUG)


def pred_jsons_dir(dataset_root: str, pred: str, part=None) -> str:
    folder = resolve_jsons_dir(dataset_root, pred)
    layout = cd_layout(folder, dataset_root)
    if layout:
        return layout["jsons"]
    return qa_jsons_dir(dataset_root, ANALYSIS_SLUG, part)


def analysis_md(dataset_root: str) -> str:
    return os.path.join(task_vis(dataset_root, ANALYSIS_SLUG), "analysis.md")


def analysis_json(dataset_root: str) -> str:
    return os.path.join(result_dir(dataset_root), "analysis.json")


def is_fp(item: dict) -> bool:
    return item_grade(item) == "wrong"


def is_adjust(item: dict) -> bool:
    return item_grade(item) == "adjust"


def is_label_issue(item: dict) -> bool:
    return item_grade(item) in {"wrong", "adjust"}


def is_change_report(fp_groups, adjust_groups, gt_groups) -> bool:
    labels = []
    for groups in (fp_groups, adjust_groups, gt_groups):
        labels.extend(row["label"] for row in groups)
    return bool(labels) and set(labels) <= {"change"}


def source_files(dataset_root: str, jsons: str, limit=None):
    folder = resolve_jsons_dir(dataset_root, jsons)
    if not os.path.isdir(folder):
        raise SystemExit(f"找不到标注目录: {folder}")
    files = sorted(Path(folder).glob("*.json"))
    kind = "json"
    if not files:
        files = sorted(
            p for p in Path(folder).iterdir()
            if p.is_file() and p.suffix.lower() in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}
        )
        kind = "mask"
    if limit:
        files = files[: int(limit)]
    if not files:
        raise SystemExit(f"目录里没有 json 或掩膜图: {folder}")
    return folder, files, kind


def qa_pending(dataset_root: str, files, slug: str, force: bool, part=None, jsons_dir="") -> bool:
    if force:
        return True
    folder = jsons_dir or qa_jsons_dir(dataset_root, slug, part)
    for jp in files:
        out_p = os.path.join(folder, f"{jp.stem}.json")
        existing = load_json(out_p) if os.path.isfile(out_p) else None
        if not existing or existing.get("source") in {"failed", "placeholder"}:
            return True
    return False


def ensure_qa(dataset_root, jsons, slug, files, limit, force, workers, timeout, base_url, model, kind="json", part=None):
    jdir = pred_jsons_dir(dataset_root, jsons, part) if kind == "mask" else ""
    if not files or not qa_pending(dataset_root, files, slug, force, part, jsons_dir=jdir):
        print(f"沿用已有质检 {slug}/{part or '-'} n={len(files)}")
        return
    if kind == "mask":
        run_change(
            dataset_root,
            masks=jsons,
            limit=limit,
            force=force,
            workers=workers,
            timeout=timeout,
            base_url=base_url,
            model=model,
            slug=slug,
            part=part,
        )
        return
    run_dataset(
        dataset_root,
        jsons=jsons,
        mode="instance",
        limit=limit,
        force=force,
        workers=workers,
        timeout=timeout,
        base_url=base_url,
        model=model,
        slug=slug,
        part=part,
    )


def load_records(dataset_root: str, files, slug: str, part=None, pred=""):
    records = []
    folder = pred_jsons_dir(dataset_root, pred, part) if pred else qa_jsons_dir(dataset_root, slug, part)
    for jp in files:
        out_p = os.path.join(folder, f"{jp.stem}.json")
        rec = load_json(out_p) if os.path.isfile(out_p) else None
        if isinstance(rec, dict):
            records.append(rec)
    return records


def group_items(records, keep) -> list:
    buckets = {}
    for rec in records:
        stem = str(rec.get("stem") or "")
        for item in rec.get("items") or []:
            if not keep(item):
                continue
            label = str(item.get("label") or "") or "(空)"
            bucket = buckets.setdefault(label, {"label": label, "n": 0, "samples": []})
            bucket["n"] += 1
            if len(bucket["samples"]) < SAMPLE_N:
                bucket["samples"].append({
                    "stem": stem,
                    "index": item.get("index"),
                    "grade": item_grade(item),
                    "issue": item.get("issue") or "",
                    "verdict": item.get("verdict") or "",
                    "reason": item.get("reason") or "",
                    "model": item.get("model") or item.get("overlay") or "",
                    "vis": rec.get("vis") or "",
                })
    return sorted(buckets.values(), key=lambda row: (-row["n"], row["label"]))


def suggestions(fp_groups, adjust_groups, gt_groups) -> list:
    change = is_change_report(fp_groups, adjust_groups, gt_groups)
    adjust_n = sum(row["n"] for row in adjust_groups)
    lines = []
    if fp_groups:
        top = fp_groups[0]
        if change:
            lines.append(f"假变化 {top['n']} 条。两期图里看不出这些变化，先查配准、阴影和季节。")
        else:
            lines.append(f"「{top['label']}」误检最多（{top['n']}），优先收紧该类或补负样本。")
    if adjust_n:
        if change:
            lines.append(f"变化是真的但掩膜不贴 {adjust_n} 条。先改掩膜，不要当成误检删掉。")
        else:
            lines.append(f"框或掩膜不贴 {adjust_n} 条（grade=adjust）。先改区域，不要当成误检删掉。")
    if gt_groups:
        top = gt_groups[0]
        if change:
            lines.append(f"GT 有 {top['n']} 条变化和两期图对不上。先改变化标签再谈模型。")
        else:
            lines.append(f"GT「{top['label']}」有 {top['n']} 条对不上画面。先改标签再谈模型。")
    if not lines:
        lines.append("没有集中的误检或标签问题。")
    return lines


ISSUE_ZH = {"oversize": "过大", "incomplete": "不完整", "shifted": "错位"}


def _sample_lines(samples) -> str:
    parts = []
    for sample in samples:
        reason = sample.get("reason") or "无理由"
        issue = ISSUE_ZH.get(str(sample.get("issue") or ""), "")
        if issue:
            reason = f"{issue}，{reason}"
        stem = sample.get("stem") or ""
        idx = sample.get("index")
        where = stem if idx is None else f"{stem}#{idx}"
        extra = ""
        if sample.get("vis"):
            extra += f" 整图 `{sample['vis']}`"
        if sample.get("model"):
            extra += f" 模型图 `{sample['model']}`"
        parts.append(f"{where}：{reason}{extra}")
    return "；".join(parts)


def render_md(report: dict) -> str:
    lines = [
        "# 框 / 掩膜结果分析",
        "",
        f"- 预测：`{report['pred']}`",
        f"- GT：`{report['gt']}`" if report.get("gt") else "- GT：未提供",
        "- 漏检：未做" if report.get("fn") == "未做" else f"- 漏检：{report['false_negative']['n']}",
        "- 发给模型的图在 `draft/analysis/model/`，整图在 `draft/analysis/vis/`",
        "",
        "## 误检",
        "",
    ]
    fp = report["false_positive"]["by_label"]
    if not fp:
        lines.append("无。")
    else:
        for row in fp:
            lines.append(f"- {row['label']}：{row['n']}。{_sample_lines(row['samples'])}")
    lines.extend(["", "## 区域要改", ""])
    adjust = report["adjust"]["by_label"]
    if not adjust:
        lines.append("无。不算误检。")
    else:
        lines.append("目标在，但框或掩膜过大、不完整或错位。不算误检。")
        lines.append("")
        for row in adjust:
            lines.append(f"- {row['label']}：{row['n']}。{_sample_lines(row['samples'])}")
    lines.extend(["", "## 标签问题", ""])
    if not report.get("gt"):
        lines.append("未提供 GT。")
    else:
        issues = report["label_issue"]["by_label"]
        if not issues:
            lines.append("无。")
        else:
            for row in issues:
                lines.append(f"- {row['label']}：{row['n']}。{_sample_lines(row['samples'])}")
    lines.extend(["", "## 漏检", ""])
    if report.get("fn") == "未做":
        lines.append("未做。先跑 label_miss.py。")
    else:
        missed = report["false_negative"]["by_label"]
        if not missed:
            lines.append("已查过，没有漏检中心。")
        else:
            lines.append("中心和裁图已有。补标走 opt_fill.py。")
            lines.append("")
            for row in missed:
                lines.append(f"- {row['label']}：{row['n']}。{_sample_lines(row['samples'])}")
    lines.extend(["", "## 建议", ""])
    for line in report["suggestions"]:
        lines.append(f"- {line}")
    lines.append("")
    return "\n".join(lines)


def group_miss(records) -> list:
    buckets = {}
    for rec in records or []:
        stem = str(rec.get("stem") or "")
        for i, item in enumerate(rec.get("miss") or []):
            label = str(item.get("label") or "") or "(空)"
            bucket = buckets.setdefault(label, {"label": label, "n": 0, "samples": []})
            bucket["n"] += 1
            if len(bucket["samples"]) < SAMPLE_N:
                bucket["samples"].append({
                    "stem": stem,
                    "index": i,
                    "grade": "",
                    "issue": "",
                    "verdict": "",
                    "reason": item.get("reason") or "",
                    "model": rec.get("model") or "",
                    "vis": rec.get("vis") or "",
                })
    return sorted(buckets.values(), key=lambda row: (-row["n"], row["label"]))


def load_miss(dataset_root: str, pred: str = ""):
    folder = ""
    if pred:
        layout = cd_layout(resolve_jsons_dir(dataset_root, pred), dataset_root)
        if layout:
            folder = os.path.join(layout["miss"], "jsons")
    if not folder:
        folder = qa_jsons_dir(dataset_root, MISS_SLUG)
    if not os.path.isdir(folder):
        return None
    records = []
    for path in sorted(Path(folder).glob("*.json")):
        rec = load_json(str(path))
        if isinstance(rec, dict) and rec.get("source") not in {"failed", "placeholder"}:
            records.append(rec)
    return records


def build_report(dataset_root, pred, gt, pred_records, gt_records, miss_records=None) -> dict:
    fp_groups = group_items(pred_records, is_fp)
    adjust_groups = group_items(pred_records, is_adjust)
    gt_groups = group_items(gt_records, is_label_issue) if gt else []
    adjust_n = sum(row["n"] for row in adjust_groups)
    report = {
        "dataset": dataset_root,
        "pred": pred,
        "gt": gt or "",
        "fn": "未做" if miss_records is None else "done",
        "false_negative": {
            "n": 0 if not miss_records else sum(len(rec.get("miss") or []) for rec in miss_records),
            "by_label": [] if miss_records is None else group_miss(miss_records),
        },
        "false_positive": {
            "n": sum(row["n"] for row in fp_groups),
            "by_label": fp_groups,
        },
        "adjust": {
            "n": adjust_n,
            "by_label": adjust_groups,
        },
        "label_issue": {
            "n": sum(row["n"] for row in gt_groups),
            "by_label": gt_groups,
        },
        "suggestions": suggestions(fp_groups, adjust_groups, gt_groups),
    }
    if miss_records is None:
        report["suggestions"].append("漏检未做。")
    elif report["false_negative"]["n"]:
        report["suggestions"].append(
            f"漏检 {report['false_negative']['n']} 处。裁图在 miss/crop/，用 opt_fill.py 定位再修边。"
        )
    else:
        report["suggestions"].append("漏检已查，没有新的中心。")
    return report


def _counts_from_records(records) -> dict:
    stats = {
        "fit": 0, "ok": 0, "wrong": 0, "adjust": 0, "n": 0,
        "images": 0, "fail": 0, "empty": 0,
    }
    for rec in records:
        stats["images"] += 1
        stats["n"] += int(rec.get("n") or 0)
        stats["fit"] += int(rec.get("fit") or 0)
        stats["ok"] += int(rec.get("ok") or 0)
        stats["wrong"] += int(rec.get("wrong") or 0)
        stats["adjust"] += int(rec.get("adjust") or 0)
        if rec.get("source") == "failed":
            stats["fail"] += 1
        if rec.get("source") == "empty":
            stats["empty"] += 1
    return stats


def analyze(dataset_root, pred, gt="", limit=None, force=False, workers=2,
            timeout=600, base_url="", model=""):
    _, pred_files, pred_kind = source_files(dataset_root, pred, limit)
    mask_dir = resolve_jsons_dir(dataset_root, pred)
    layout = cd_layout(mask_dir, dataset_root) if pred_kind == "mask" else None
    ensure_qa(
        dataset_root, pred, ANALYSIS_SLUG, pred_files, limit, force,
        workers, timeout, base_url, model, kind=pred_kind, part=PRED_PART,
    )
    if not layout:
        ensure_views(dataset_root, ANALYSIS_SLUG, PRED_PART)
    pred_records = load_records(
        dataset_root, pred_files, ANALYSIS_SLUG, PRED_PART, pred=pred,
    )
    gt_records = []
    if gt:
        _, gt_files, gt_kind = source_files(dataset_root, gt, limit)
        ensure_qa(
            dataset_root, gt, ANALYSIS_SLUG, gt_files, limit, force,
            workers, timeout, base_url, model, kind=gt_kind, part=GT_PART,
        )
        if not layout:
            ensure_views(dataset_root, ANALYSIS_SLUG, GT_PART)
        gt_records = load_records(dataset_root, gt_files, ANALYSIS_SLUG, GT_PART)
    report = build_report(
        dataset_root, pred, gt, pred_records, gt_records, load_miss(dataset_root, pred),
    )
    counts = _counts_from_records(pred_records)
    adjust_section = report.get("adjust")
    report.update(counts)
    if isinstance(adjust_section, dict):
        report["adjust"] = adjust_section
        report["adjust_grades"] = counts["adjust"]
    if layout:
        report["crop"] = layout["crop"]
        report["jsons"] = layout["jsons"]
        write_json(layout["analysis_json"], report)
        out = layout["analysis_json"]
    else:
        write_json(analysis_json(dataset_root), report)
        md_path = analysis_md(dataset_root)
        os.makedirs(os.path.dirname(md_path), exist_ok=True)
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(render_md(report))
        old_md = os.path.join(result_dir(dataset_root), "analysis.md")
        if os.path.isfile(old_md) and os.path.abspath(old_md) != os.path.abspath(md_path):
            os.remove(old_md)
        out = md_path
    adj_n = report["adjust"]["n"] if isinstance(report.get("adjust"), dict) else int(report.get("adjust") or 0)
    print(
        f"analysis 误检={report['false_positive']['n']} "
        f"不贴={adj_n} 标签问题={report['label_issue']['n']} "
        f"漏检={report['fn'] if report['fn'] == '未做' else report['false_negative']['n']} → {out}"
    )
    return report


def parse_args():
    p = argparse.ArgumentParser(description="汇总误检、不贴合和已有漏检。不改标注，不再问模型。")
    p.add_argument("--dataset", required=True)
    p.add_argument("--pred", required=True, help="预测 LabelMe 目录，相对 dataset 或绝对路径")
    p.add_argument("--gt", default="", help="GT LabelMe 目录。省略则不查标签")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--force", action="store_true")
    p.add_argument("--workers", type=int, default=2)
    p.add_argument("--timeout", type=int, default=600)
    p.add_argument("--base_url", default="")
    p.add_argument("--model", default="")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    analyze(
        args.dataset,
        pred=args.pred,
        gt=args.gt,
        limit=args.limit,
        force=args.force,
        workers=args.workers,
        timeout=args.timeout,
        base_url=args.base_url,
        model=args.model,
    )
