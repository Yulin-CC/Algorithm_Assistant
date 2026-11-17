"""
# @Author: 算法组
# @Date: 2026-09-27
# @Description: 按强标签 / _m 弱标签统计正检、误检、漏检。弱标签未命中不计漏检
# @Command: python util/weak_label_report.py --gt-dir jsons-gt --pre-dir jsons-det-pre --alias alias.yaml
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

WEAK_SUFFIX = "_m"


def box_of(shape: dict) -> tuple[float, float, float, float]:
    points = shape.get("points") or []
    if shape.get("shape_type") == "rectangle" and len(points) == 2:
        (x1, y1), (x2, y2) = points
        return float(min(x1, x2)), float(min(y1, y2)), float(max(x1, x2)), float(max(y1, y2))
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return float(min(xs)), float(min(ys)), float(max(xs)), float(max(ys))


def box_iou(a: tuple, b: tuple) -> float:
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    if inter <= 0:
        return 0.0
    area_a = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    area_b = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def load_alias(path: str | None) -> dict[str, str]:
    if not path:
        return {}
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    if file.suffix.lower() == ".json":
        data = json.loads(text)
    else:
        import yaml
        data = yaml.safe_load(text) or {}
    return {str(key): str(value) for key, value in data.items()}


def split_label(label: str, alias: dict[str, str]) -> tuple[str, bool]:
    raw = str(label or "")
    weak = raw.endswith(WEAK_SUFFIX)
    base_raw = raw[: -len(WEAK_SUFFIX)] if weak else raw
    base = alias.get(base_raw, alias.get(raw, base_raw))
    if str(base).endswith(WEAK_SUFFIX):
        base = str(base)[: -len(WEAK_SUFFIX)]
        weak = True
    return str(base), weak


def load_shapes(json_path: Path, alias: dict[str, str]) -> list[dict]:
    meta = json.loads(json_path.read_text(encoding="utf-8"))
    items = []
    for shape in meta.get("shapes") or []:
        points = shape.get("points") or []
        if len(points) < 2:
            continue
        base, weak = split_label(str(shape.get("label") or ""), alias)
        items.append({
            "label": str(shape.get("label") or ""),
            "base": base,
            "weak": weak,
            "box": box_of(shape),
        })
    return items


#-------------#
# 逐图判定
#-------------#
def judge(gts: list[dict], preds: list[dict], thr: float) -> tuple[list, list, list]:
    """预测先对强标签，再对弱标签。IoU 大于 thr 为正检。未命中的强标签才是漏检。"""
    bases = {item["base"] for item in gts} | {item["base"] for item in preds}
    tp, fp, miss = [], [], []
    for base in bases:
        strong = [item for item in gts if item["base"] == base and not item["weak"]]
        weak = [item for item in gts if item["base"] == base and item["weak"]]
        used = set()
        for pred in [item for item in preds if item["base"] == base]:
            hit = False
            for index, gt in enumerate(strong):
                if box_iou(pred["box"], gt["box"]) > thr:
                    used.add(index)
                    hit = True
                    break
            if not hit:
                for gt in weak:
                    if box_iou(pred["box"], gt["box"]) > thr:
                        hit = True
                        break
            (tp if hit else fp).append(pred)
        for index, gt in enumerate(strong):
            if index not in used:
                miss.append(gt)
    return tp, fp, miss


def summarize(gt_dir: Path, pre_dir: Path, alias: dict[str, str], thr: float) -> dict[str, list[int]]:
    totals = defaultdict(lambda: [0, 0, 0, 0])
    for gt_json in sorted(gt_dir.glob("*.json")):
        pre_json = pre_dir / gt_json.name
        gts = load_shapes(gt_json, alias)
        preds = load_shapes(pre_json, alias) if pre_json.is_file() else []
        tp, fp, miss = judge(gts, preds, thr)
        for bucket, items in ((0, tp), (1, fp), (2, miss)):
            for item in items:
                totals[item["base"]][bucket] += 1
        for item in gts:
            if not item["weak"]:
                totals[item["base"]][3] += 1
    return totals


def format_report(totals: dict[str, list[int]], thr: float) -> str:
    lines = [
        f"IoU > {thr:.2f}。正检含强标签和弱标签。漏检只数没对上的强标签。",
        "",
        "|类|正检|误检|漏检|强标签数|误检率|漏检率|",
        "|-|-|-|-|-|-|-|",
    ]
    for base in sorted(totals):
        tp, fp, miss, strong = totals[base]
        fp_rate = f"{fp / (tp + fp):.2%}" if tp + fp else "—"
        miss_rate = f"{miss / strong:.2%}" if strong else "—"
        lines.append(f"|{base}|{tp}|{fp}|{miss}|{strong}|{fp_rate}|{miss_rate}|")
    return "\n".join(lines)


def parse_args():
    parser = argparse.ArgumentParser(description="强/弱标签正检误检漏检")
    parser.add_argument("--gt-dir", required=True)
    parser.add_argument("--pre-dir", required=True)
    parser.add_argument("--alias", default="", help="预测类名到真值类名，yaml 或 json")
    parser.add_argument("--iou", type=float, default=0.30)
    parser.add_argument("--save", default="")
    return parser.parse_args()


def main():
    args = parse_args()
    totals = summarize(Path(args.gt_dir), Path(args.pre_dir), load_alias(args.alias or None), args.iou)
    report = format_report(totals, args.iou)
    print(report)
    if args.save:
        Path(args.save).write_text(report + "\n", encoding="utf-8")
        print("写入", args.save)


if __name__ == "__main__":
    main()
