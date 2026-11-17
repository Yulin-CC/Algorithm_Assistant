"""
# @Author: Yullin
# @Date: 2026-08-31
# @Description: 图像二/多分类：sample 试分 → 校验后提炼知识 → 全量 → 不确定桶人工校验 → 交付
# @Command: python util/classify.py sample --dataset /path --classes a,b --n 12
# @Command: python util/classify.py review --dataset /path --accept-all
# @Command: python util/classify.py knowledge --dataset /path
# @Command: python util/classify.py run --dataset /path
# @Command: python util/classify.py hold --dataset /path
# @Command: python util/classify.py deliver --dataset /path
"""

import argparse
import json
import os
import random
import re
import shutil
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

_PKG_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
_REPO = os.path.normpath(os.path.join(_PKG_ROOT, "..", "..", "..", ".."))
_MODEL_UTIL = os.path.join(_REPO, "model", "util")
if _MODEL_UTIL not in sys.path:
    sys.path.insert(0, _MODEL_UTIL)

from tqdm import tqdm

tqdm.monitor_interval = 0

from common import (
    IMG_EXTS,
    ensure_dir,
    list_image_files,
    load_json,
    load_json_first,
    resolve_images_dir,
    task_cache,
    task_draft,
    task_result,
    write_json,
)

TASK_SLUG = "classify"
from servers_io import get_default_service
from vllm_client import VLLMClient, extract_json_object


SYSTEM_CLASSIFY = (
    "你是图像分类助手。只根据图中可见内容，从给定类别中选且只选一个。"
    "不要编造看不见的细节。只输出 JSON。"
    "证据不够时必须把 confidence 标为 low，不要硬标 high。"
)

SYSTEM_KNOWLEDGE = (
    "你是视觉分类知识整理助手。根据已人工校验的样本图像，归纳各类的可见判别线索。"
    "只依据图中可见差异，不要编造。只输出 JSON。"
)


FAILED_DIR = "_failed"
HOLD_DIR = "_待审"


def normalize_confidence(raw) -> str:
    if isinstance(raw, bool):
        return "high" if raw else "low"
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return "high" if float(raw) >= 0.7 else "low"
    text = str(raw or "").strip().lower()
    if text in {"high", "h", "sure", "certain", "ok", "confident"}:
        return "high"
    if text in {"low", "l", "mid", "medium", "unsure", "uncertain", "hold", "weak"}:
        return "low"
    return ""


def parse_confidence(data: dict) -> str:
    conf = normalize_confidence((data or {}).get("confidence"))
    if conf:
        return conf
    u = (data or {}).get("uncertain")
    if u is True or str(u).strip().lower() in {"true", "yes", "1"}:
        return "low"
    if u is False or str(u).strip().lower() in {"false", "no", "0"}:
        return "high"
    return "low"


def is_hold(rec) -> bool:
    if not rec or rec.get("validated") or is_placeholder(rec):
        return False
    if rec.get("hold") is True:
        return True
    conf = normalize_confidence(rec.get("confidence"))
    if conf == "low":
        return True
    uncertain = rec.get("uncertain")
    if uncertain is True or str(uncertain).strip().lower() in {"true", "1", "yes"}:
        return True
    return False


def classify_root(dataset_root: str) -> str:
    return task_draft(dataset_root, TASK_SLUG)


def cache_dir(dataset_root: str) -> str:
    return task_cache(dataset_root, TASK_SLUG)


def config_path(dataset_root: str) -> str:
    return os.path.join(cache_dir(dataset_root), "config.json")


def sample_view_dir(dataset_root: str) -> str:
    return os.path.join(cache_dir(dataset_root), "sample")


def result_view_dir(dataset_root: str) -> str:
    return task_result(dataset_root, TASK_SLUG)


def result_under_name(dataset_root: str) -> str:
    """复核隔离目录名：结果写到 result/<under>/<类名>/，不污染顶层同类文件夹。"""
    cfg = load_json_first([
        config_path(dataset_root),
        _legacy_config_path(dataset_root),
    ]) or {}
    return str(cfg.get("result_under") or "").strip()


def active_result_view(dataset_root: str) -> str:
    base = result_view_dir(dataset_root)
    under = result_under_name(dataset_root)
    if under:
        return os.path.join(base, safe_dirname(under))
    return base


def records_dir(dataset_root: str) -> str:
    return os.path.join(cache_dir(dataset_root), "jsons")


def sample_meta_dir(dataset_root: str) -> str:
    return records_dir(dataset_root)


def labels_meta_dir(dataset_root: str) -> str:
    """优先沿用已有 `_meta/labels`，避免中途改路径后把已跑结果当成未分类。"""
    legacy = _legacy_labels_meta(dataset_root)
    if os.path.isdir(legacy):
        try:
            with os.scandir(legacy) as it:
                for ent in it:
                    if ent.is_file(follow_symlinks=False) and ent.name.lower().endswith(".json"):
                        return legacy
        except OSError:
            pass
    return records_dir(dataset_root)


def knowledge_path(dataset_root: str) -> str:
    return os.path.join(cache_dir(dataset_root), "knowledge.json")


def knowledge_md_path(dataset_root: str) -> str:
    return os.path.join(cache_dir(dataset_root), "knowledge.md")


def _legacy_config_path(dataset_root: str) -> str:
    return os.path.join(classify_root(dataset_root), "config.json")


def _legacy_knowledge_paths(dataset_root: str) -> list:
    root = classify_root(dataset_root)
    return [
        knowledge_path(dataset_root),
        os.path.join(root, "knowledge.json"),
        os.path.join(root, "_meta", "knowledge.json"),
    ]


def _legacy_sample_meta(dataset_root: str) -> str:
    return os.path.join(classify_root(dataset_root), "_meta", "sample")


def _legacy_labels_meta(dataset_root: str) -> str:
    return os.path.join(classify_root(dataset_root), "_meta", "labels")


def _legacy_sample_view(dataset_root: str) -> str:
    return os.path.join(classify_root(dataset_root), "sample")


def safe_dirname(label: str) -> str:
    raw = (label or "").strip() or FAILED_DIR
    s = "".join(c if c.isalnum() or c in "-_." else "_" for c in raw)
    return s or FAILED_DIR


def class_folder(view_root: str, label: str) -> str:
    name = FAILED_DIR if not (label or "").strip() else safe_dirname(label)
    return os.path.join(view_root, name)


def place_image(src: str, dest_dir: str, filename: str = "") -> str:
    if not src or not os.path.isfile(src):
        return ""
    ensure_dir(dest_dir)
    dest = os.path.join(dest_dir, filename or os.path.basename(src))
    if os.path.normcase(os.path.abspath(src)) == os.path.normcase(os.path.abspath(dest)):
        return dest
    if os.path.isfile(dest):
        return dest
    try:
        os.link(src, dest)
    except OSError:
        shutil.copy2(src, dest)
    return dest


def remove_from_view(view_root: str, filename: str, keep_label: str = None):
    if not view_root or not os.path.isdir(view_root) or not filename:
        return
    keep = safe_dirname(keep_label) if keep_label else None
    # 清理直接落在 view_root/ 下的旧文件（复核前扁平放置）
    direct = os.path.join(view_root, filename)
    if os.path.isfile(direct):
        try:
            os.remove(direct)
        except OSError:
            pass
    try:
        children = os.listdir(view_root)
    except OSError:
        return
    for child in children:
        if keep and child == keep:
            continue
        cand = os.path.join(view_root, child, filename)
        if os.path.isfile(cand):
            try:
                os.remove(cand)
            except OSError:
                pass


def put_record_image(rec: dict, view_root: str, allow_hold: bool = True) -> str:
    src = rec.get("image_abs") or ""
    if not src or not os.path.isfile(src):
        rel = rec.get("image") or ""
        if rel:
            src = rel if os.path.isabs(rel) else ""
    if not src or not os.path.isfile(src):
        return ""
    filename = os.path.basename(src)
    if is_placeholder(rec):
        dest_dir = class_folder(view_root, "")
        keep = FAILED_DIR
    elif allow_hold and is_hold(rec):
        dest_dir = os.path.join(view_root, HOLD_DIR)
        keep = HOLD_DIR
    else:
        label = rec.get("label") or ""
        dest_dir = class_folder(view_root, label)
        keep = safe_dirname(label) if label else FAILED_DIR
    remove_from_view(view_root, filename, keep_label=keep)
    placed = place_image(src, dest_dir, filename)
    rec["placed"] = placed
    return placed


def labels_from_view(view_root: str, classes) -> dict:
    """文件夹名 → 类别；用户把图挪到别的类文件夹后以此为准。"""
    canon = {safe_dirname(c): c for c in (classes or [])}
    out = {}
    if not view_root or not os.path.isdir(view_root):
        return out
    try:
        children = os.listdir(view_root)
    except OSError:
        return out
    for child in children:
        folder = os.path.join(view_root, child)
        if not os.path.isdir(folder) or child in {FAILED_DIR, HOLD_DIR}:
            continue
        label = canon.get(child) or canonical_label(child, classes)
        if not label:
            continue
        try:
            files = os.listdir(folder)
        except OSError:
            continue
        for name in files:
            if Path(name).suffix.lower() not in IMG_EXTS:
                continue
            out[Path(name).stem] = label
    return out


def list_class_folders(view_root: str, classes, extras=None) -> list:
    names = [safe_dirname(c) for c in (classes or [])] + [FAILED_DIR]
    for extra in extras or []:
        if extra and extra not in names:
            names.append(extra)
    seen = []
    out = []
    for name in names:
        if name in seen:
            continue
        seen.append(name)
        path = os.path.join(view_root, name)
        if os.path.isdir(path):
            n = sum(1 for p in Path(path).iterdir() if p.is_file())
            out.append((name, path, n))
    return out


def _count_images(folder: str) -> int:
    if not folder or not os.path.isdir(folder):
        return 0
    n = 0
    try:
        with os.scandir(folder) as it:
            for ent in it:
                if ent.is_file(follow_symlinks=False) and Path(ent.name).suffix.lower() in IMG_EXTS:
                    n += 1
    except OSError:
        return 0
    return n


def move_file(src: str, dest: str) -> str:
    """把文件挪到 dest；同源硬链接则只删多余路径。"""
    if not src or not os.path.isfile(src):
        return ""
    src_a = os.path.normcase(os.path.abspath(src))
    dest_a = os.path.normcase(os.path.abspath(dest))
    if src_a == dest_a:
        return dest
    ensure_dir(os.path.dirname(dest))
    if os.path.isfile(dest):
        try:
            if os.path.samefile(src, dest):
                os.remove(src)
                return dest
        except OSError:
            pass
        os.remove(dest)
    os.replace(src, dest)
    return dest


def hold_dir(dataset_root: str) -> str:
    return os.path.join(active_result_view(dataset_root), HOLD_DIR)


def count_hold_images(dataset_root: str) -> int:
    return _count_images(hold_dir(dataset_root))


def deliver_result_to_root(dataset_root: str, classes, images_dirname="images"):
    """确认 result/ 分桶完成。不再挪到数据集根、不删 draft。"""
    dataset_root = os.path.realpath(dataset_root)
    view = result_view_dir(dataset_root)
    if not os.path.isdir(view):
        raise FileNotFoundError(f"没有 result 文件夹，请先 run：{view}")
    n_hold = count_hold_images(dataset_root)
    if n_hold:
        raise SystemExit(
            f"还有 {n_hold} 张在 {HOLD_DIR}/，请先挪到类别文件夹后跑 hold：{hold_dir(dataset_root)}"
        )

    names = [safe_dirname(c) for c in (classes or [])]
    if FAILED_DIR not in names:
        names.append(FAILED_DIR)
    counted = Counter()
    for name in names:
        counted[name] = _count_images(os.path.join(view, name))
    return counted


def parse_classes(raw) -> list:
    if isinstance(raw, (list, tuple)):
        parts = [str(x) for x in raw]
    else:
        parts = re.split(r"[,|，、;；]+", str(raw or ""))
    out, seen = [], set()
    for p in parts:
        name = str(p).strip()
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(name)
    return out


def load_config(dataset_root: str) -> dict:
    cfg = load_json_first([
        config_path(dataset_root),
        _legacy_config_path(dataset_root),
    ])
    if not cfg:
        raise FileNotFoundError(f"缺少配置，请先 sample：{config_path(dataset_root)}")
    classes = parse_classes(cfg.get("classes") or [])
    if len(classes) < 2:
        raise ValueError("配置中类别不足 2 个")
    cfg["classes"] = classes
    return cfg


def write_config(dataset_root: str, data: dict):
    write_json(config_path(dataset_root), data)


def canonical_label(raw, classes) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    for name in classes:
        if text == name:
            return name
    low = text.lower()
    hits = [name for name in classes if name.lower() == low]
    if len(hits) == 1:
        return hits[0]
    hits = [name for name in classes if name.lower() in low or low in name.lower()]
    if len(hits) == 1:
        return hits[0]
    return ""


def parse_fixes(raw: str) -> dict:
    """stem=label 或 stem:label，逗号/空白分隔。"""
    out = {}
    for chunk in re.split(r"[,;\s]+", str(raw or "").strip()):
        if not chunk:
            continue
        if "=" in chunk:
            stem, label = chunk.split("=", 1)
        elif ":" in chunk:
            stem, label = chunk.split(":", 1)
        else:
            raise ValueError(f"无法解析修正项（需要 stem=类别）: {chunk}")
        stem, label = stem.strip(), label.strip()
        if stem and label:
            out[stem] = label
    return out


def _resolve_service(base_url, model):
    url = (base_url or "").strip()
    name = (model or "").strip()
    if not url or not name:
        svc = get_default_service() or {}
        url = url or (svc.get("base_url") or "").strip()
        name = name or (svc.get("model") or "").strip()
    if not url or not name:
        raise RuntimeError(
            "未指定 --base_url/--model，且 model/config/vllm_server.json 无 default 服务"
        )
    return url.rstrip("/"), name


def _make_client(base_url="", model="", timeout=600):
    url, model_name = _resolve_service(base_url, model)
    client = VLLMClient(
        base_url=url, model=model_name, timeout=timeout, enable_thinking=False,
    )
    if not client.health_check():
        raise RuntimeError(f"vLLM 不可用: {url}")
    return client, model_name


def knowledge_text(dataset_root: str) -> str:
    data = load_json_first(_legacy_knowledge_paths(dataset_root), default=None) or {}
    if not data:
        return ""
    parts = []
    guide = str(data.get("guide") or "").strip()
    if guide:
        parts.append("总判别要点：\n" + guide)
    per = data.get("per_class") or {}
    if isinstance(per, dict) and per:
        lines = ["各类可见线索："]
        for k, v in per.items():
            lines.append(f"- {k}: {v}")
        parts.append("\n".join(lines))
    return "\n\n".join(parts).strip()


def class_guide_text(dataset_root: str) -> str:
    cfg = load_json_first([
        config_path(dataset_root),
        _legacy_config_path(dataset_root),
    ], default=None) or {}
    return str(cfg.get("class_guide") or "").strip()


def classify_one(client: VLLMClient, image_abs: str, classes, knowledge="", guide=""):
    listed = " / ".join(classes)
    extra_parts = []
    if guide and str(guide).strip():
        extra_parts.append("判别口径：\n" + str(guide).strip())
    if knowledge and str(knowledge).strip():
        extra_parts.append("已校验样本归纳的临时知识（优先遵循）：\n" + str(knowledge).strip())
    extra = ("\n" + "\n\n".join(extra_parts) + "\n") if extra_parts else ""
    prompt = (
        f"从下列类别中选且只选一个：{listed}\n"
        f"{extra}"
        "只返回 JSON，例如 "
        '{"label":"' + classes[0] + '","reason":"一句可见依据","confidence":"high"}。\n'
        "label 必须是上列类别之一；reason 用一句中文写可见依据。\n"
        "confidence 只能是 high 或 low："
        "证据清楚、几乎不会判错标 high；"
        "看不清、被挡、两类都说得通、只能猜测时必须标 low。"
        "不确定时宁可 low。"
    )
    raw = client.describe_image(
        image_abs, prompt, system=SYSTEM_CLASSIFY,
        max_tokens=256, temperature=0.2,
    )
    data = extract_json_object(raw)
    label = canonical_label(data.get("label"), classes)
    if not label:
        raise ValueError(f"模型类别不在给定集合中: {data}")
    reason = str(data.get("reason") or "").strip()
    conf = parse_confidence(data)
    return {
        "label": label,
        "reason": reason,
        "confidence": conf,
        "hold": conf == "low",
        "source": "vllm",
        "error": None,
    }


def is_placeholder(rec) -> bool:
    if not rec:
        return True
    src = (rec.get("source") or "").lower()
    if src in {"failed", "placeholder"}:
        return True
    return not str(rec.get("label") or "").strip()


def list_json_records(folder: str) -> list:
    if not folder or not os.path.isdir(folder):
        return []
    rows = []
    for path in sorted(Path(folder).glob("*.json")):
        rec = load_json(str(path), default=None)
        if rec:
            rec["_path"] = str(path)
            rows.append(rec)
    return rows


def list_sample_records(dataset_root: str) -> list:
    meta = ensure_dir(sample_meta_dir(dataset_root))
    view = sample_view_dir(dataset_root)
    for folder in (view, _legacy_sample_view(dataset_root)):
        if not os.path.isdir(folder):
            continue
        for path in Path(folder).glob("*.json"):
            if not path.is_file():
                continue
            dest = os.path.join(meta, path.name)
            if os.path.isfile(dest):
                continue
            try:
                os.replace(str(path), dest)
            except OSError:
                shutil.copy2(str(path), dest)
                try:
                    os.remove(str(path))
                except OSError:
                    pass
    rows = [r for r in list_json_records(meta) if r.get("stage") == "sample"]
    if rows:
        return rows
    return list_json_records(_legacy_sample_meta(dataset_root))


def write_sample_md(dataset_root: str, classes, rows):
    view = sample_view_dir(dataset_root)
    out_p = os.path.join(cache_dir(dataset_root), "sample.md")
    lines = [
        "# Sample 试分类",
        "",
        f"- **classes**: {', '.join(classes)}",
        f"- **n**: {len(rows)}",
        f"- **请打开文件夹核对图像**：`{view}`",
        "",
    ]
    for name, path, n in list_class_folders(view, classes):
        lines.append(f"- `{name}/`  {n} 张  → `{path}`")
    lines += [
        "",
        "把分错的图**挪到正确类别文件夹**，或回复 `stem=类别` / `全部通过`。",
        "",
        "| stem | 预测 | 依据 | 已校验 |",
        "| --- | --- | --- | --- |",
    ]
    for rec in rows:
        reason = str(rec.get("reason") or "").replace("|", "\\|")
        ok = "是" if rec.get("validated") else "否"
        lines.append(
            f"| {rec.get('stem','')} | {rec.get('label','')} | {reason} | {ok} |"
        )
    ensure_dir(os.path.dirname(out_p))
    with open(out_p, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return out_p


def cmd_sample(args):
    dataset_root = os.path.realpath(args.dataset)
    classes = parse_classes(args.classes)
    if len(classes) < 2:
        raise SystemExit("请提供至少 2 个类别，例如 --classes a,b")
    img_dir = resolve_images_dir(dataset_root, args.images)
    files = list_image_files(img_dir)
    if not files:
        raise SystemExit(f"未找到图像: {img_dir}")
    n = max(1, int(args.n or 12))
    n = min(n, len(files))
    rng = random.Random(int(args.seed))
    picked = rng.sample(files, n)

    ensure_dir(sample_meta_dir(dataset_root))
    ensure_dir(sample_view_dir(dataset_root))
    guide = str(getattr(args, "guide", "") or "").strip()
    write_config(dataset_root, {
        "classes": classes,
        "n_classes": len(classes),
        "sample_n": n,
        "seed": int(args.seed),
        "images_dirname": args.images,
        "img_dir": img_dir,
        "dataset_root": dataset_root,
        "class_guide": guide,
    })
    list_sample_records(dataset_root)

    client, model_name = _make_client(args.base_url, args.model, args.timeout)
    jobs = []
    for path in picked:
        stem = Path(path).stem
        out_p = os.path.join(sample_meta_dir(dataset_root), f"{stem}.json")
        existing = load_json(out_p) if os.path.isfile(out_p) else None
        if not args.force and existing is not None and not is_placeholder(existing):
            continue
        jobs.append({
            "stem": stem,
            "image_abs": path,
            "image_rel": os.path.relpath(path, dataset_root),
            "out_p": out_p,
        })

    print(
        f"sample 待分类: {len(jobs)} / 抽 {n} 张（全集 {len(files)}，"
        f"classes={classes}, model={model_name}）"
    )

    def _one(job):
        try:
            rec = classify_one(client, job["image_abs"], classes, guide=guide)
        except Exception as e:
            rec = {
                "label": "",
                "reason": "",
                "confidence": "",
                "hold": False,
                "source": "failed",
                "error": str(e),
            }
        rec.update({
            "stem": job["stem"],
            "image": job["image_rel"],
            "image_abs": job["image_abs"],
            "validated": False,
            "stage": "sample",
        })
        put_record_image(rec, sample_view_dir(dataset_root), allow_hold=False)
        write_json(job["out_p"], rec)
        return rec

    n_fail = 0
    if jobs:
        with ThreadPoolExecutor(max_workers=max(1, int(args.workers))) as pool:
            futs = [pool.submit(_one, job) for job in jobs]
            for fut in tqdm(as_completed(futs), total=len(futs), desc="sample"):
                rec = fut.result()
                if rec.get("source") == "failed":
                    n_fail += 1

    rows = list_sample_records(dataset_root)
    for rec in rows:
        put_record_image(rec, sample_view_dir(dataset_root), allow_hold=False)
        rec.pop("_path", None)
    md = write_sample_md(dataset_root, classes, list_sample_records(dataset_root))
    view = sample_view_dir(dataset_root)
    print(f"sample 完成 → 请打开文件夹核对图像：")
    for name, path, n in list_class_folders(view, classes):
        print(f"  {name}/  {n} 张  {path}")
    print(f"索引：{md}")
    if n_fail:
        print(f"⚠ 其中 {n_fail} 张失败（可再跑 sample，不要加 --force）")
    print("确认后再 review / knowledge。")


def ingest_view_samples(dataset_root: str, classes) -> int:
    """把用户拷进类别文件夹、但不在 sample 台账里的图收进来。"""
    cfg = load_json_first([
        config_path(dataset_root),
        _legacy_config_path(dataset_root),
    ], default={}) or {}
    img_dir = cfg.get("img_dir") or dataset_root
    existing = {}
    for rec in list_sample_records(dataset_root):
        stem = rec.get("stem")
        if stem:
            existing[stem] = rec
    n_new = 0
    view = sample_view_dir(dataset_root)
    if not os.path.isdir(view):
        return 0
    canon = {safe_dirname(c): c for c in classes}
    for child in os.listdir(view):
        folder = os.path.join(view, child)
        if not os.path.isdir(folder) or child in {FAILED_DIR, HOLD_DIR}:
            continue
        label = canon.get(child) or canonical_label(child, classes)
        if not label:
            continue
        for name in os.listdir(folder):
            if Path(name).suffix.lower() not in IMG_EXTS:
                continue
            stem = Path(name).stem
            if stem in existing:
                continue
            src = ""
            for ext in IMG_EXTS:
                cand = os.path.join(img_dir, stem + ext)
                if os.path.isfile(cand):
                    src = cand
                    break
            if not src:
                src = os.path.join(folder, name)
            try:
                rel = os.path.relpath(src, dataset_root)
            except ValueError:
                rel = os.path.basename(src)
            rec = {
                "label": label,
                "reason": "user copied into class folder",
                "source": "user",
                "error": None,
                "stem": stem,
                "image": rel,
                "image_abs": os.path.abspath(src),
                "validated": True,
                "stage": "sample",
            }
            write_json(os.path.join(sample_meta_dir(dataset_root), f"{stem}.json"), rec)
            existing[stem] = rec
            n_new += 1
    return n_new


def cmd_review(args):
    dataset_root = os.path.realpath(args.dataset)
    cfg = load_config(dataset_root)
    classes = cfg["classes"]
    rows = list_sample_records(dataset_root)
    n_ingest = ingest_view_samples(dataset_root, classes)
    if n_ingest:
        rows = list_sample_records(dataset_root)
    if not rows:
        raise SystemExit("没有 sample 记录，请先 sample")
    folder_labels = labels_from_view(sample_view_dir(dataset_root), classes)
    fixes = parse_fixes(args.fix) if args.fix else {}
    n_fix, n_ok, n_move = 0, 0, 0
    for rec in rows:
        stem = rec.get("stem") or Path(rec["_path"]).stem
        changed = False
        if stem in fixes:
            label = canonical_label(fixes[stem], classes)
            if not label:
                raise SystemExit(f"修正类别不在集合中: {stem}={fixes[stem]}；可选 {classes}")
            rec["label"] = label
            rec["source"] = "user"
            rec["error"] = None
            rec["validated"] = True
            changed = True
            n_fix += 1
        elif stem in folder_labels and folder_labels[stem] != rec.get("label"):
            rec["label"] = folder_labels[stem]
            rec["source"] = "user"
            rec["error"] = None
            rec["validated"] = True
            changed = True
            n_move += 1
        elif args.accept_all and not is_placeholder(rec):
            rec["validated"] = True
            changed = True
            n_ok += 1
        if changed:
            rec.pop("_path", None)
            put_record_image(rec, sample_view_dir(dataset_root), allow_hold=False)
            write_json(os.path.join(sample_meta_dir(dataset_root), f"{stem}.json"), rec)
    rows = list_sample_records(dataset_root)
    for rec in rows:
        put_record_image(rec, sample_view_dir(dataset_root), allow_hold=False)
    md = write_sample_md(dataset_root, classes, list_sample_records(dataset_root))
    n_val = sum(1 for r in list_sample_records(dataset_root) if r.get("validated"))
    view = sample_view_dir(dataset_root)
    print(f"review 完成：新收入 {n_ingest}，修正 {n_fix}，挪文件夹 {n_move}，接受 {n_ok}，已校验 {n_val} → {view}")
    print(f"索引：{md}")


def cmd_knowledge(args):
    dataset_root = os.path.realpath(args.dataset)
    cfg = load_config(dataset_root)
    classes = cfg["classes"]
    if args.accept_all:
        args.fix = args.fix or ""
        cmd_review(args)

    rows = [r for r in list_sample_records(dataset_root) if r.get("validated") and not is_placeholder(r)]
    if not rows:
        raise SystemExit("没有已校验 sample。请先 review --accept-all 或 --fix")

    by_cls = defaultdict(list)
    for rec in rows:
        by_cls[rec["label"]].append(rec)

    missing = [c for c in classes if c not in by_cls]
    exemplars = []
    captions = []
    per_max = max(1, int(args.per_class_max or 3))
    cap = max(1, int(args.max_images or 8))
    for name in classes:
        group = by_cls.get(name) or []
        take = group[:per_max]
        for rec in take:
            if len(exemplars) >= cap:
                break
            path = rec.get("image_abs") or os.path.join(dataset_root, rec.get("image") or "")
            if not os.path.isfile(path):
                continue
            idx = len(exemplars) + 1
            exemplars.append(path)
            captions.append(f"图{idx} → 类别「{name}」（文件 {rec.get('stem')}）")
        if len(exemplars) >= cap:
            break

    inventory = "\n".join(
        f"- {r.get('stem')}: {r.get('label')}；依据：{r.get('reason') or '（无）'}"
        for r in rows
    )
    miss_line = (
        f"下列类别在校验样本中尚未出现，请按类名字面给出谨慎线索：{', '.join(missing)}"
        if missing else "每个给定类别在样本中均有至少 1 张。"
    )
    prompt = (
        f"给定类别：{' / '.join(classes)}\n"
        f"{miss_line}\n"
        "已人工校验的样本清单：\n"
        f"{inventory}\n"
        "附图按编号对应上述「图N」。请归纳可复用的分类知识。\n"
        "只返回 JSON："
        '{"guide":"总判别要点","per_class":{"类名":"该类可见线索"}}。\n'
        "per_class 必须覆盖每一个给定类别。"
    )
    if not exemplars:
        raise SystemExit("校验样本图像文件都不存在，无法提炼知识")

    client, model_name = _make_client(args.base_url, args.model, args.timeout)
    print(f"knowledge：{len(rows)} 张已校验，附图 {len(exemplars)}，model={model_name}")
    raw = client.describe_images(
        exemplars, prompt, system=SYSTEM_KNOWLEDGE,
        max_tokens=1024, temperature=0.3,
    )
    data = extract_json_object(raw)
    per = data.get("per_class") or {}
    if not isinstance(per, dict):
        per = {}
    per_out = {}
    for name in classes:
        per_out[name] = str(per.get(name) or "").strip()
    rec = {
        "classes": classes,
        "guide": str(data.get("guide") or "").strip(),
        "per_class": per_out,
        "n_samples": len(rows),
        "n_images": len(exemplars),
        "missing_in_sample": missing,
        "source": "vllm",
        "error": None,
    }
    write_json(knowledge_path(dataset_root), rec)
    md_p = knowledge_md_path(dataset_root)
    if os.path.isfile(md_p):
        os.remove(md_p)
    print(f"knowledge 完成 → {knowledge_path(dataset_root)}")
    print("请把知识给用户过目后再 run 全量。")


def cmd_run(args):
    dataset_root = os.path.realpath(args.dataset)
    cfg = load_config(dataset_root)
    classes = cfg["classes"]
    know = knowledge_text(dataset_root)
    if not know:
        raise SystemExit(f"缺少 knowledge。请先 knowledge，或检查 {knowledge_path(dataset_root)}")
    guide = class_guide_text(dataset_root)

    img_dir = resolve_images_dir(dataset_root, args.images or cfg.get("images_dirname") or "images")
    files = list_image_files(img_dir)
    if not files:
        raise SystemExit(f"未找到图像: {img_dir}")

    validated = {
        r["stem"]: r for r in list_sample_records(dataset_root)
        if r.get("validated") and not is_placeholder(r)
    }
    out_dir = ensure_dir(labels_meta_dir(dataset_root))
    under = result_under_name(dataset_root)
    view = ensure_dir(active_result_view(dataset_root))
    jobs = []
    n_copy = 0
    lim = int(args.limit) if args.limit else None
    for path in files:
        if lim is not None and len(jobs) >= lim:
            break
        stem = Path(path).stem
        out_p = os.path.join(out_dir, f"{stem}.json")
        if stem in validated and not args.force:
            if lim is not None:
                continue
            rec = dict(validated[stem])
            rec.pop("_path", None)
            rec["stage"] = "sample"
            rec["source"] = rec.get("source") or "sample"
            rec["image_abs"] = rec.get("image_abs") or path
            if not under:
                put_record_image(rec, view)
            write_json(out_p, rec)
            n_copy += 1
            continue
        existing = load_json(out_p) if os.path.isfile(out_p) else None
        if not args.force and existing is not None and not is_placeholder(existing):
            if lim is None and not under:
                put_record_image(existing, view)
            continue
        jobs.append({
            "stem": stem,
            "image_abs": path,
            "image_rel": os.path.relpath(path, dataset_root),
            "out_p": out_p,
        })

    client, model_name = _make_client(args.base_url, args.model, args.timeout)
    print(
        f"run 待分类: {len(jobs)}（沿用校验 sample {n_copy}，全集本批 {len(files)}，"
        f"model={model_name}"
        + (f"，result_under={under}" if under else "")
        + "）"
    )

    def _one(job):
        try:
            rec = classify_one(client, job["image_abs"], classes, knowledge=know, guide=guide)
        except Exception as e:
            rec = {
                "label": "",
                "reason": "",
                "confidence": "",
                "hold": False,
                "source": "failed",
                "error": str(e),
            }
        rec.update({
            "stem": job["stem"],
            "image": job["image_rel"],
            "image_abs": job["image_abs"],
            "validated": False,
            "stage": "run",
        })
        put_record_image(rec, view)
        write_json(job["out_p"], rec)
        return rec

    n_fail = 0
    if jobs:
        with ThreadPoolExecutor(max_workers=max(1, int(args.workers))) as pool:
            futs = [pool.submit(_one, job) for job in jobs]
            for fut in tqdm(as_completed(futs), total=len(futs), desc="classify"):
                rec = fut.result()
                if rec.get("source") == "failed":
                    n_fail += 1

    all_recs = []
    for path in Path(out_dir).glob("*.json"):
        rec = load_json(str(path), default=None)
        if rec:
            all_recs.append(rec)
    counts = Counter()
    n_failed_all = 0
    n_hold_all = 0
    for rec in all_recs:
        if is_placeholder(rec):
            n_failed_all += 1
            counts["failed"] += 1
        elif is_hold(rec):
            n_hold_all += 1
            counts[HOLD_DIR] += 1
        else:
            counts[rec.get("label") or "failed"] += 1
    summary = {
        "classes": classes,
        "counts": dict(counts),
        "n_total": len(all_recs),
        "n_from_sample": n_copy,
        "n_inferred": len(jobs),
        "n_failed": n_failed_all,
        "n_hold": n_hold_all,
        "result_dir": view,
        "hold_dir": hold_dir(dataset_root) if n_hold_all else "",
    }
    write_json(os.path.join(cache_dir(dataset_root), "summary.json"), summary)
    hold_md = write_hold_md(dataset_root, classes, all_recs)
    print(f"全量完成 → 请打开结果文件夹：")
    for name, path, n in list_class_folders(view, classes, extras=[HOLD_DIR]):
        print(f"  {name}/  {n} 张  {path}")
    print("计数:", json.dumps(dict(counts), ensure_ascii=False))
    if n_fail:
        print(f"⚠ 其中 {n_fail} 张失败（可再跑 run，不要加 --force）")

    skip_deliver = bool(getattr(args, "no_deliver", False) or args.limit)
    if n_hold_all:
        print(f"不确定桶 {n_hold_all} 张 → 请打开核对：{hold_dir(dataset_root)}")
        if hold_md:
            print(f"索引：{hold_md}")
        print("把图挪到正确类别文件夹后跑 hold；未清空前不会交付。")
    if n_failed_all:
        print("有失败记录，未标记交付（修好后续跑 run，不要加 --force）")
    elif n_hold_all:
        print("未标记交付（待审未清空）")
    elif skip_deliver:
        print("未标记交付（--limit / --no-deliver）")
    else:
        cmd_deliver(args)


def list_label_records(dataset_root: str) -> list:
    rows = list_json_records(labels_meta_dir(dataset_root))
    if rows:
        return rows
    return list_json_records(_legacy_labels_meta(dataset_root))


def write_hold_md(dataset_root: str, classes, rows=None) -> str:
    view = active_result_view(dataset_root)
    hold_p = hold_dir(dataset_root)
    recs = rows if rows is not None else [r for r in list_label_records(dataset_root)]
    hold_recs = [r for r in recs if is_hold(r)]
    out_p = os.path.join(cache_dir(dataset_root), "hold.md")
    lines = [
        "# 待审（不确定桶）",
        "",
        f"- **n**: {len(hold_recs)}",
        f"- **请打开文件夹核对图像**：`{hold_p}`",
        "",
        "把分错或不接受模型猜测的图**挪到与 `_待审` 同级的正确类别文件夹**。",
        "全部挪完回复「校验完了」；剩下按模型预测收下则回复「其余按模型」。",
        "",
    ]
    for name, path, n in list_class_folders(view, classes, extras=[HOLD_DIR]):
        lines.append(f"- `{name}/`  {n} 张  → `{path}`")
    lines += [
        "",
        "| stem | 模型猜测 | 依据 |",
        "| --- | --- | --- |",
    ]
    preview = hold_recs[:80]
    for rec in preview:
        reason = str(rec.get("reason") or "").replace("|", "\\|")
        lines.append(
            f"| {rec.get('stem','')} | {rec.get('label','')} | {reason} |"
        )
    if len(hold_recs) > len(preview):
        lines.append(f"| … | 其余 {len(hold_recs) - len(preview)} 张见文件夹 | |")
    ensure_dir(os.path.dirname(out_p))
    with open(out_p, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return out_p


def cmd_hold(args):
    dataset_root = os.path.realpath(args.dataset)
    cfg = load_config(dataset_root)
    classes = cfg["classes"]
    view = active_result_view(dataset_root)
    out_dir = labels_meta_dir(dataset_root)
    if not os.path.isdir(view) or not os.path.isdir(out_dir):
        raise SystemExit("没有 result / 标签记录，请先 run")

    folder_labels = labels_from_view(view, classes)
    fixes = parse_fixes(args.fix) if args.fix else {}
    n_fix, n_move, n_ok = 0, 0, 0
    for rec in list_label_records(dataset_root):
        stem = rec.get("stem") or Path(rec["_path"]).stem
        changed = False
        if stem in fixes:
            label = canonical_label(fixes[stem], classes)
            if not label:
                raise SystemExit(f"修正类别不在集合中: {stem}={fixes[stem]}；可选 {classes}")
            rec["label"] = label
            rec["source"] = "user"
            rec["error"] = None
            rec["validated"] = True
            rec["hold"] = False
            changed = True
            n_fix += 1
        elif stem in folder_labels:
            new_label = folder_labels[stem]
            was_hold = is_hold(rec)
            label_changed = new_label != rec.get("label")
            if was_hold or label_changed:
                rec["label"] = new_label
                rec["validated"] = True
                rec["hold"] = False
                rec["error"] = None
                if label_changed:
                    rec["source"] = "user"
                changed = True
                n_move += 1
        elif getattr(args, "accept_all", False) and is_hold(rec) and rec.get("label"):
            rec["validated"] = True
            rec["hold"] = False
            rec["error"] = None
            changed = True
            n_ok += 1
        if changed:
            rec.pop("_path", None)
            put_record_image(rec, view)
            write_json(os.path.join(out_dir, f"{stem}.json"), rec)

    leftover = count_hold_images(dataset_root)
    hold_md = write_hold_md(dataset_root, classes)
    print(
        f"hold 完成：修正 {n_fix}，挪文件夹 {n_move}，按模型收下 {n_ok}，"
        f"仍待审 {leftover} → {hold_dir(dataset_root)}"
    )
    print(f"索引：{hold_md}")
    skip_deliver = bool(getattr(args, "no_deliver", False))
    if leftover:
        print(f"还有 {leftover} 张在 {HOLD_DIR}/，未交付。请继续挪图，或加 --accept-all 按模型猜测收下。")
        return
    if skip_deliver:
        print("不确定桶已空，未交付（--no-deliver）")
        return
    cmd_deliver(args)


def cmd_deliver(args):
    dataset_root = os.path.realpath(args.dataset)
    cfg = load_config(dataset_root)
    classes = cfg["classes"]
    moved = deliver_result_to_root(
        dataset_root, classes,
        images_dirname=getattr(args, "images", None) or cfg.get("images_dirname") or "images",
    )
    print("交付完成 → 类别文件夹在 draft/classify/result/（未挪到数据集根，未删 draft）：")
    view = result_view_dir(dataset_root)
    for name in [safe_dirname(c) for c in classes] + [FAILED_DIR]:
        path = os.path.join(view, name)
        n = _count_images(path)
        if n or os.path.isdir(path):
            print(f"  {name}/  {n} 张  {path}")
    print("计数:", json.dumps(dict(moved), ensure_ascii=False))


def _add_shared(p):
    p.add_argument("--dataset", required=True, help="数据集根目录")
    p.add_argument("--images", default="images", help="图像子目录名，默认 images")
    p.add_argument("--base_url", default="", help="空则读 model/config/vllm_server.json 的 default")
    p.add_argument("--model", default="")
    p.add_argument("--timeout", type=int, default=600)
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--force", action="store_true")


def parse_args():
    p = argparse.ArgumentParser(description="图像二/多分类：sample → review → knowledge → run → hold → deliver")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("sample", help="随机抽样本试分类")
    _add_shared(s)
    s.add_argument("--classes", required=True, help="类别，逗号分隔，至少 2 个")
    s.add_argument("--n", type=int, default=12, help="抽样张数，默认 12")
    s.add_argument("--seed", type=int, default=0)
    s.add_argument("--guide", default="", help="类别口径，sample/run 都会写入 prompt")

    r = sub.add_parser("review", help="写入用户校验/修正")
    _add_shared(r)
    r.add_argument("--accept-all", action="store_true", help="未点名的成功样本全部视为通过")
    r.add_argument("--fix", default="", help="修正：stem=类别,stem2=类别")

    k = sub.add_parser("knowledge", help="读取已校验样本，提炼临时分类知识")
    _add_shared(k)
    k.add_argument("--accept-all", action="store_true", help="提炼前先把成功 sample 标为已校验")
    k.add_argument("--fix", default="", help="同 review --fix")
    k.add_argument("--per-class-max", type=int, default=3)
    k.add_argument("--max-images", type=int, default=8)

    u = sub.add_parser("run", help="用临时知识对全量图像分类；确定的进类文件夹，不确定的进 _待审")
    _add_shared(u)
    u.add_argument("--limit", type=int, default=None)
    u.add_argument("--no-deliver", action="store_true", help="只写 result/ 分桶，不跑交付确认")

    h = sub.add_parser("hold", help="消化不确定桶：用户把 _待审 中的图挪到类别文件夹后执行；桶空则交付")
    _add_shared(h)
    h.add_argument("--accept-all", action="store_true", help="仍留在 _待审 的按模型猜测收下")
    h.add_argument("--fix", default="", help="修正：stem=类别,stem2=类别")
    h.add_argument("--no-deliver", action="store_true", help="消化完也不交付")

    d = sub.add_parser("deliver", help="确认 result/<类名>/ 分桶完成；_待审 非空则拒绝。不挪到数据集根、不删 draft")
    _add_shared(d)
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    if args.cmd == "sample":
        cmd_sample(args)
    elif args.cmd == "review":
        cmd_review(args)
    elif args.cmd == "knowledge":
        cmd_knowledge(args)
    elif args.cmd == "run":
        cmd_run(args)
    elif args.cmd == "hold":
        cmd_hold(args)
    elif args.cmd == "deliver":
        cmd_deliver(args)
    else:
        raise SystemExit("未知子命令")
