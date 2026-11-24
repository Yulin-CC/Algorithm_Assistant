"""
# @Author: Yullin
# @Date: 2026-11-06
# @Description: GroundingPI 给框 → detect 写 jsons-det-pre；segment 再走 Triton SAM 写 jsons-seg-pre
# @Command: python util/detect_segment.py sample --dataset /path --task detect --classes a --en-label a=LampPost --hint a=... --n 12
# @Command: python util/detect_segment.py run --dataset /path --task detect --classes a,b
"""

import argparse
import json
import os
import random
import re
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

_PKG_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
_REPO = os.path.normpath(os.path.join(_PKG_ROOT, "..", "..", "..", ".."))
_MODEL_UTIL = os.path.join(_REPO, "server", "util")
if _MODEL_UTIL not in sys.path:
    sys.path.insert(0, _MODEL_UTIL)

from tqdm import tqdm

tqdm.monitor_interval = 0

import cv2
import numpy as np

from common import (
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

TASK_SLUG = "detseg-groundingpi"
from sam_client import (
    _read_rgb,
    get_default_sam,
    make_client,
    mask_to_polygon,
    polygon_to_bbox_pts,
)
from groundingpi_client import GroundingPIClient, parse_boxes as parse_gpi_boxes
from vllm_client import extract_json_object


SYSTEM_BOX = (
    "视觉定位。禁止思考过程、禁止解释、禁止 markdown。"
    "第一个字符必须是 [ 。只输出 JSON 数组。坐标 0–1000 网格。"
)

SYSTEM_GATE = (
    "分割质检。禁止思考、禁止解释。只输出一个 JSON 对象。"
)

TASKS = ("detect", "segment")
JSON_DIRNAME = {"detect": "jsons-det-pre", "segment": "jsons-seg-pre"}
GATE_ROUNDS = 2
BOX_NMS_IOU = 0.8
REBOX_MIN_IOU = 0.35
REBOX_MAX_AREA_RATIO = 1.5
QWEN_MAX_SIDE = 1280
GATE_MODES = ("low", "all", "off")
_SAM_LOCK = threading.Lock()


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


def gate_mode(gate) -> str:
    if gate in (False, "off", "none", "0", 0):
        return "off"
    if gate in ("all", "always", "every"):
        return "all"
    return "low"


def thinking_on(raw) -> bool:
    return raw in (True, "on", "1", 1, "true", "yes")


def instance_needs_gate(rec, mode: str) -> bool:
    if mode == "off":
        return False
    if mode == "all":
        return True
    return parse_confidence(rec) != "high"


def pkg_draft(dataset_root: str) -> str:
    return task_draft(dataset_root, TASK_SLUG)


def pkg_cache(dataset_root: str) -> str:
    return task_cache(dataset_root, TASK_SLUG)


def pkg_result(dataset_root: str) -> str:
    return task_result(dataset_root, TASK_SLUG)


def config_path(dataset_root: str) -> str:
    return os.path.join(pkg_cache(dataset_root), "config.json")


def knowledge_json_path(dataset_root: str) -> str:
    return os.path.join(pkg_cache(dataset_root), "knowledge.json")


def knowledge_md_path(dataset_root: str) -> str:
    return os.path.join(pkg_cache(dataset_root), "knowledge.md")


def classes_json_path(dataset_root: str) -> str:
    return os.path.join(pkg_cache(dataset_root), "classes.json")


def cache_subdir(dataset_root: str, name: str = "sample") -> str:
    text = str(name or "sample").strip().replace("\\", "/").strip("/")
    if not text or text in {".", ".."} or "/" in text or ".." in text:
        raise SystemExit(f"非法 cache 子目录名: {name}")
    return os.path.join(pkg_cache(dataset_root), text)


def sample_root(dataset_root: str) -> str:
    return cache_subdir(dataset_root, "sample")


def sample_jsons_dir(dataset_root: str) -> str:
    return os.path.join(sample_root(dataset_root), "jsons")


def normalize_vis_name(name: str) -> str:
    return str(name or "vis").strip() or "vis"


def sample_vis_dir(dataset_root: str, name: str = "vis") -> str:
    return os.path.join(sample_root(dataset_root), normalize_vis_name(name))


def class_folder_name(name: str) -> str:
    text = str(name or "").strip()
    for ch in '<>:"/\\|?*':
        text = text.replace(ch, "_")
    text = text.strip(" .")
    if not text or text in {".", ".."}:
        raise SystemExit(f"非法类别目录名: {name}")
    return text


def sample_vis_class_dir(dataset_root: str, class_name: str, vis_name: str = "vis") -> str:
    return os.path.join(sample_vis_dir(dataset_root, vis_name), class_folder_name(class_name))


def rec_of_class(rec, class_name: str, classes) -> bool:
    return canonical_label((rec or {}).get("label"), classes) == class_name


def _pkg_json(dataset_root, filename: str):
    return load_json_first([
        os.path.join(pkg_cache(dataset_root), filename),
        os.path.join(pkg_draft(dataset_root), filename),
    ], default={}) or {}


def _has_cjk(text: str) -> bool:
    return bool(re.search(r"[\u3400-\u9fff]", str(text or "")))


def _norm_en_label(raw: str) -> str:
    text = str(raw or "").strip()
    if not text or _has_cjk(text):
        return ""
    if not re.match(r"^[A-Za-z][A-Za-z0-9_-]*$", text):
        return ""
    return text


def default_en_label(name: str) -> str:
    """类名本身已是英文标识符时，可直接当 json 标签。"""
    return _norm_en_label(name)


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


def _norm_prior(name: str, raw) -> dict:
    rec = dict(raw) if isinstance(raw, dict) else {}
    aliases = rec.get("aliases")
    if isinstance(aliases, str):
        aliases = [p for p in aliases.split() if p]
    elif not isinstance(aliases, list):
        aliases = [name]
    rec["aliases"] = [str(a).strip() for a in aliases if str(a).strip()]
    if name and name not in rec["aliases"]:
        rec["aliases"] = [name] + rec["aliases"]
    rec["hint"] = str(rec.get("hint") or "").strip()
    rec["en"] = _norm_en_label(rec.get("en") or "") or default_en_label(name)
    return rec


def seed_class_prior(name: str) -> dict:
    return _norm_prior(name, {"aliases": [name], "hint": ""})


def _dump_prior(name: str, rec: dict) -> dict:
    return {
        "aliases": list(rec.get("aliases") or [name]),
        "hint": str(rec.get("hint") or "").strip(),
        "en": str(rec.get("en") or "").strip(),
    }


def _class_map_from_blob(blob) -> dict:
    if not isinstance(blob, dict):
        return {}
    nested = blob.get("classes")
    if isinstance(nested, dict):
        return {str(k): v for k, v in nested.items() if isinstance(v, dict)}
    skip = {"box_modes", "hint_templates", "ocr_knowledge", "phone_names", "classes"}
    return {str(k): v for k, v in blob.items() if k not in skip and isinstance(v, dict)}


def _lookup_prior(store: dict, name: str):
    if not name:
        return None
    if name in store:
        return store[name]
    low = name.lower()
    hits = [v for k, v in store.items() if k.lower() == low]
    if len(hits) == 1:
        return hits[0]
    hits = [
        v for v in store.values()
        if isinstance(v, dict) and str(v.get("en") or "").strip().lower() == low
    ]
    return hits[0] if len(hits) == 1 else None


def _ingest_priors(merged: dict, extra):
    if not isinstance(extra, dict):
        return
    for k, v in extra.items():
        if not isinstance(v, dict):
            continue
        name = str(k)
        merged[name] = _norm_prior(name, {**(_lookup_prior(merged, name) or {}), **v})


def merge_class_priors(dataset_root, classes) -> dict:
    """cache/classes.json 为准；缺类时生成 aliases/hint/en。旧 knowledge.json、config 仅作迁移。"""
    merged = {}
    if dataset_root:
        blob = _pkg_json(dataset_root, "classes.json")
        _ingest_priors(merged, _class_map_from_blob(blob))
        know = _pkg_json(dataset_root, "knowledge.json")
        for k, v in (know.get("per_class") or {}).items() if isinstance(know.get("per_class"), dict) else []:
            if isinstance(v, dict) and _lookup_prior(merged, str(k)) is None:
                _ingest_priors(merged, {str(k): v})
        cfg = _pkg_json(dataset_root, "config.json")
        extra = cfg.get("class_priors")
        if isinstance(extra, dict):
            for k, v in extra.items():
                if isinstance(v, dict) and _lookup_prior(merged, str(k)) is None:
                    _ingest_priors(merged, {str(k): v})
    names = [c for c in (classes or []) if c] or list(merged.keys())
    out = {}
    for name in names:
        rec = _lookup_prior(merged, name)
        out[name] = rec if rec is not None else seed_class_prior(name)
    return out


class ClassPriors:
    def __init__(self, by_name=None):
        self.by_name = dict(by_name or {})

    def rec(self, name: str) -> dict:
        found = _lookup_prior(self.by_name, name)
        return found if found is not None else _norm_prior(name or "", {})

    def hint(self, name: str) -> str:
        return str(self.rec(name).get("hint") or "").strip()

    def en_label(self, name: str) -> str:
        rec = self.rec(name)
        return _norm_en_label(rec.get("en") or "") or default_en_label(name)

    def alias_blob(self, name: str) -> str:
        rec = self.rec(name)
        aliases = rec.get("aliases") or []
        parts = [str(a) for a in aliases] + [str(rec.get("en") or "")]
        return " ".join(p for p in parts if p)


_PRIORS = None


def current_priors() -> ClassPriors:
    global _PRIORS
    if _PRIORS is None:
        _PRIORS = ClassPriors({})
    return _PRIORS


def set_priors(by_name: dict) -> ClassPriors:
    global _PRIORS
    _PRIORS = ClassPriors(by_name)
    return _PRIORS


def drop_legacy_class_sidecars(dataset_root: str):
    """旧 cache/knowledge.json、knowledge.md 已并入 classes.json，写盘后删掉。"""
    if not dataset_root:
        return
    for path in (knowledge_json_path(dataset_root), knowledge_md_path(dataset_root)):
        if not os.path.isfile(path):
            continue
        try:
            os.remove(path)
        except OSError:
            pass


def write_classes_json(dataset_root, priors_map):
    ensure_dir(pkg_cache(dataset_root))
    path = classes_json_path(dataset_root)
    old = load_json(path, default={}) or {}
    kept = _class_map_from_blob(old)
    classes = {}
    for name, rec in kept.items():
        if name not in (priors_map or {}):
            classes[name] = _dump_prior(name, _norm_prior(name, rec))
    for name, rec in (priors_map or {}).items():
        classes[name] = _dump_prior(name, rec)
    write_json(path, {"classes": classes})
    return path


def parse_hint_args(items) -> dict:
    """解析重复 --hint 类名=提示（也接受 类名:提示）。"""
    out = {}
    for raw in items or []:
        text = str(raw or "").strip()
        if not text:
            continue
        if "=" in text:
            name, hint = text.split("=", 1)
        elif ":" in text:
            name, hint = text.split(":", 1)
        else:
            raise SystemExit(f"--hint 格式应为 类名=提示，收到: {text}")
        name = name.strip()
        hint = hint.strip()
        if not name:
            continue
        out[name] = hint
    return out


def apply_hint_overrides(priors_map, hints, dataset_root="") -> dict:
    if not hints:
        return priors_map
    for name, hint in hints.items():
        rec = dict(priors_map.get(name) or seed_class_prior(name))
        rec["hint"] = str(hint or "").strip()
        priors_map[name] = rec
    return priors_map


def apply_en_overrides(priors_map, mapping, dataset_root="") -> dict:
    if not mapping:
        return priors_map
    for name, en in mapping.items():
        rec = dict(priors_map.get(name) or seed_class_prior(name))
        rec["en"] = _norm_en_label(en)
        priors_map[name] = rec
    return priors_map


def require_en_labels(classes):
    missing, bad, seen = [], [], {}
    for name in classes or []:
        en = current_priors().en_label(name)
        if not en:
            missing.append(name)
            continue
        if _has_cjk(en):
            bad.append(f"{name}→{en}")
            continue
        key = en.lower()
        if key in seen:
            raise SystemExit(f"英文标签重复：{seen[key]} 与 {name} 都是 {en}")
        seen[key] = name
    if missing or bad:
        parts = []
        if missing:
            parts.append("缺英文标签：" + "、".join(missing))
        if bad:
            parts.append("含中文：" + "、".join(bad))
        raise SystemExit(
            "jsons 的 label 必须是英文标识符（字母开头，可含数字/_/-）。"
            + "；".join(parts)
            + "。请加 --en-label 中文名=EnglishName"
        )


def json_label(name: str) -> str:
    return current_priors().en_label(name)


def prepare_class_knowledge(
    dataset_root, task, classes, write=True,
    hint_overrides=None, en_overrides=None,
) -> ClassPriors:
    priors_map = merge_class_priors(dataset_root, classes)
    apply_hint_overrides(priors_map, hint_overrides, dataset_root=dataset_root)
    apply_en_overrides(priors_map, en_overrides, dataset_root=dataset_root)
    bound = set_priors(priors_map)
    require_en_labels(classes or list(priors_map.keys()))
    if write and dataset_root:
        write_classes_json(dataset_root, priors_map)
        drop_legacy_class_sidecars(dataset_root)
    return bound


def _alias_keys(name: str) -> set:
    blob = current_priors().alias_blob(name)
    keys = {str(name or "").strip().lower()}
    keys.update(p for p in blob.lower().split() if p)
    return keys


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
    hits = [name for name in classes if current_priors().en_label(name).lower() == low]
    if len(hits) == 1:
        return hits[0]
    hits = [name for name in classes if low in _alias_keys(name)]
    if len(hits) == 1:
        return hits[0]
    hits = [name for name in classes if name.lower() in low or low in name.lower()]
    if len(hits) == 1:
        return hits[0]
    return ""


def _make_gpi(base_url="", model="", timeout=600, thinking=False):
    del thinking
    client = GroundingPIClient(base_url=base_url, model=model, timeout=timeout)
    if not client.health_check():
        raise RuntimeError(f"GroundingPI 不可用: {client.base_url}")
    return client, client.model


def _as_point_list(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("objects", "boxes", "bboxes", "points", "instances", "items"):
            if isinstance(data.get(key), list):
                return data[key]
        return [data]
    return []


def _close_truncated_array(text: str):
    start = text.find("[")
    if start < 0:
        return None
    chunk = text[start:]
    last = chunk.rfind("}")
    if last < 0:
        return None
    cand = chunk[: last + 1] + "]"
    try:
        data = json.loads(cand)
        return data if isinstance(data, list) else None
    except json.JSONDecodeError:
        return None


def _salvage_bbox_dicts(text: str) -> list:
    pat = re.compile(
        r'\{\s*"label"\s*:\s*"([^"]+)"\s*,\s*"bbox_2d"\s*:\s*\[\s*([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)\s*\]'
        r'|\{\s*"bbox_2d"\s*:\s*\[\s*([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)\s*\]\s*,\s*"label"\s*:\s*"([^"]+)"',
        re.I,
    )
    out = []
    for m in pat.finditer(text or ""):
        if m.group(1) is not None:
            out.append({
                "label": m.group(1),
                "bbox_2d": [float(m.group(i)) for i in range(2, 6)],
            })
        else:
            out.append({
                "label": m.group(10),
                "bbox_2d": [float(m.group(i)) for i in range(6, 10)],
            })
    return out


def _salvage_point_dicts(text: str) -> list:
    pat = re.compile(
        r'\{\s*"label"\s*:\s*"([^"]+)"\s*,\s*"point_2d"\s*:\s*\[\s*([-\d.]+)\s*,\s*([-\d.]+)\s*\]'
        r'|\{\s*"point_2d"\s*:\s*\[\s*([-\d.]+)\s*,\s*([-\d.]+)\s*\]\s*,\s*"label"\s*:\s*"([^"]+)"',
        re.I,
    )
    out = []
    for m in pat.finditer(text or ""):
        if m.group(1) is not None:
            out.append({"label": m.group(1), "point_2d": [float(m.group(2)), float(m.group(3))]})
        else:
            out.append({"label": m.group(6), "point_2d": [float(m.group(4)), float(m.group(5))]})
    return out


def extract_json_list(text: str):
    if text is None:
        return []
    text = str(text).strip()
    for tag in ("</think>", "</reasoning>"):
        if tag in text:
            text = text.split(tag)[-1].strip()
    if text.startswith("```"):
        lines = [ln for ln in text.splitlines() if not ln.strip().startswith("```")]
        text = "\n".join(lines).strip()
    try:
        return _as_point_list(json.loads(text))
    except json.JSONDecodeError:
        pass
    a0, a1 = text.find("["), text.rfind("]")
    if a0 >= 0 and a1 > a0:
        try:
            return _as_point_list(json.loads(text[a0:a1 + 1]))
        except json.JSONDecodeError:
            pass
    closed = _close_truncated_array(text)
    if closed:
        return closed
    salvaged = _salvage_bbox_dicts(text) or _salvage_point_dicts(text)
    if salvaged:
        return salvaged
    try:
        return _as_point_list(extract_json_object(text))
    except Exception:
        return []


def extract_json_dict(text: str) -> dict:
    if text is None:
        return {}
    text = str(text).strip()
    for tag in ("</think>", "</reasoning>"):
        if tag in text:
            text = text.split(tag)[-1].strip()
    if text.startswith("```"):
        lines = [ln for ln in text.splitlines() if not ln.strip().startswith("```")]
        text = "\n".join(lines).strip()
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
        if isinstance(data, list) and data and isinstance(data[0], dict):
            return data[0]
    except json.JSONDecodeError:
        pass
    try:
        obj = extract_json_object(text)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def _to_grid(v: float) -> float:
    v = float(v)
    if abs(v) <= 1.5:
        v *= 1000.0
    return v


def parse_bbox_2d(raw, w: int, h: int):
    if not isinstance(raw, (list, tuple)) or len(raw) < 4:
        return None
    try:
        vals = [_to_grid(v) for v in raw[:4]]
    except (TypeError, ValueError):
        return None
    gx1, gy1, gx2, gy2 = vals
    if gx2 < gx1:
        gx1, gx2 = gx2, gx1
    if gy2 < gy1:
        gy1, gy2 = gy2, gy1
    if gx2 - gx1 < 2 or gy2 - gy1 < 2:
        return None
    x1 = min(max(gx1 / 1000.0 * w, 0.0), w - 1.0)
    y1 = min(max(gy1 / 1000.0 * h, 0.0), h - 1.0)
    x2 = min(max(gx2 / 1000.0 * w, 0.0), w - 1.0)
    y2 = min(max(gy2 / 1000.0 * h, 0.0), h - 1.0)
    if x2 - x1 < 2 or y2 - y1 < 2:
        return None
    return [x1, y1, x2, y2], [gx1, gy1, gx2, gy2]


def parse_point_2d(raw, w: int, h: int):
    if not isinstance(raw, (list, tuple)) or len(raw) < 2:
        return None
    try:
        gx, gy = _to_grid(raw[0]), _to_grid(raw[1])
    except (TypeError, ValueError):
        return None
    x = min(max(gx / 1000.0 * w, 0.0), w - 1.0)
    y = min(max(gy / 1000.0 * h, 0.0), h - 1.0)
    return [x, y], [gx, gy]


def box_center(xyxy) -> list:
    return [(float(xyxy[0]) + float(xyxy[2])) / 2.0, (float(xyxy[1]) + float(xyxy[3])) / 2.0]


def _iou_xyxy(a, b) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    if inter <= 0:
        return 0.0
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    return inter / (area_a + area_b - inter + 1e-6)


def _box_area_rec(rec) -> float:
    return _box_area(rec.get("box") or [0, 0, 0, 0])


def _inside_frac(inner, outer) -> float:
    """inner 有多少面积落在 outer 里。"""
    ia = _box_area(inner)
    if ia <= 1:
        return 0.0
    ax1, ay1, ax2, ay2 = inner
    bx1, by1, bx2, by2 = outer
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    return inter / ia


def _nms_boxes(rows, iou_thr=0.5) -> list:
    ranked = sorted(
        rows or [],
        key=lambda r: (0 if r.get("confidence") == "high" else 1, _box_area_rec(r)),
    )
    kept = []
    for rec in ranked:
        drop = False
        replace = []
        for i, other in enumerate(kept):
            if other["label"] != rec["label"]:
                continue
            iou = _iou_xyxy(other["box"], rec["box"])
            nested = (
                _inside_frac(other["box"], rec["box"]) >= 0.7
                or _inside_frac(rec["box"], other["box"]) >= 0.7
            )
            if not nested and iou < iou_thr:
                continue
            # 物体套叠（近景大框罩住另一个实例）两边都留；仅高 IoU 才当重复。
            if nested and iou < iou_thr:
                continue
            if _box_area_rec(rec) + 1 < _box_area_rec(other):
                replace.append(i)
            else:
                drop = True
                break
        if drop:
            continue
        for i in reversed(replace):
            kept.pop(i)
        kept.append(rec)
    return kept


def unmatched_boxes(boxed, instances) -> list:
    kept = [i.get("box") for i in instances if i.get("box")]
    out = []
    for rec in boxed or []:
        if any(_iou_xyxy(rec["box"], b) >= 0.3 for b in kept):
            continue
        out.append(rec)
    return out


def _confidence_rule() -> str:
    return "看不清或吃不准标 low，其余 high。"


def _class_hints(classes) -> str:
    parts = [current_priors().hint(c) for c in (classes or []) if current_priors().hint(c)]
    return ("\n" + "\n".join(parts)) if parts else ""


def box_prompt(classes) -> str:
    from groundingpi_client import locate_prompt
    extra = _class_hints(classes).strip()
    return locate_prompt(classes) + (("\n" + extra) if extra else "")


def _rows_to_boxes(rows, classes, w: int, h: int) -> list:
    out = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        label = canonical_label(row.get("label"), classes)
        parsed = parse_bbox_2d(
            row.get("bbox_2d") or row.get("bbox") or row.get("box"), w, h,
        )
        if not label or not parsed:
            continue
        xyxy, grid = parsed
        out.append({
            "label": label,
            "box": xyxy,
            "bbox_2d": grid,
            "point": box_center(xyxy),
            "confidence": parse_confidence(row),
        })
    return out


def gpi_boxes(client: GroundingPIClient, image_abs: str, classes) -> list:
    rgb = _read_rgb(image_abs)
    h, w = rgb.shape[:2]
    raw = client.chat_image(image_abs, box_prompt(classes), max_tokens=8192)
    rows = []
    for rec in parse_gpi_boxes(raw, w, h):
        label = canonical_label(rec.get("label"), classes)
        box = rec.get("box") or []
        if not label or len(box) < 4:
            continue
        rows.append({
            "label": label,
            "box": list(box),
            "bbox_2d": rec.get("bbox_2d") or [],
            "point": box_center(box),
            "confidence": "high",
        })
    if not rows:
        rows = _rows_to_boxes(extract_json_list(raw), classes, w, h)
    return _nms_boxes(rows, iou_thr=BOX_NMS_IOU)


def gate_prompt(label: str) -> str:
    return (
        f"半透明彩色区域是对当前这一个「{label}」的分割结果。"
        "只评价这一块掩膜：是否对准当前这一目标、尽量不吃进邻物或背景。\n"
        "图中其他没涂色的目标一律忽略，不要因为他们没被覆盖就判失败，也不要把框扩大去包邻物。\n"
        "只返回一个 JSON 对象，不要 markdown：\n"
        '{"ok":true,"reason":"...","action":"keep","bbox_2d":[xmin,ymin,xmax,ymax],'
        '"point_2d":[x,y],"point_label":1}\n'
        "ok=true 表示当前这一目标可以接受，action 填 keep。"
        "ok=false 时 action 为 rebox（新框必须仍是当前这一目标，只能微调，禁止并进邻物）或 point"
        "（须给 point_2d 与 point_label：1=应补进掩膜的前景点，0=应抠掉的邻物/背景点）。"
    )


def qwen_gate(client, overlay_abs: str, label: str) -> dict:
    raw = ""
    if hasattr(client, "describe_image"):
        raw = client.describe_image(
            overlay_abs, gate_prompt(label), system=SYSTEM_GATE,
            max_tokens=256, temperature=0,
        )
    elif hasattr(client, "chat_image"):
        raw = client.chat_image(overlay_abs, gate_prompt(label), max_tokens=256)
    data = extract_json_dict(raw)
    if not data:
        return {"ok": True, "action": "keep", "reason": "parse_fail"}
    ok = data.get("ok")
    if isinstance(ok, str):
        ok = ok.strip().lower() in ("1", "true", "yes", "y", "ok")
    else:
        ok = bool(ok)
    action = str(data.get("action") or ("keep" if ok else "rebox")).strip().lower()
    if action not in ("keep", "rebox", "point"):
        action = "keep" if ok else "rebox"
    return {
        "ok": ok,
        "action": action,
        "reason": str(data.get("reason") or ""),
        "bbox_2d": data.get("bbox_2d") or data.get("bbox") or data.get("box"),
        "point_2d": data.get("point_2d") or data.get("point"),
        "point_label": data.get("point_label", 1),
    }


def _box_area(xyxy) -> float:
    return max(0.0, float(xyxy[2]) - float(xyxy[0])) * max(0.0, float(xyxy[3]) - float(xyxy[1]))


def accept_rebox(old_xyxy, new_xyxy) -> bool:
    if not old_xyxy or not new_xyxy:
        return False
    if _iou_xyxy(old_xyxy, new_xyxy) < REBOX_MIN_IOU:
        return False
    old_a = _box_area(old_xyxy)
    if old_a <= 1:
        return True
    return _box_area(new_xyxy) <= old_a * REBOX_MAX_AREA_RATIO


def write_qwen_view(bgr, max_side=QWEN_MAX_SIDE) -> str:
    """缩小后写临时 jpeg，避免航拍大图把 vLLM 打成 500。0–1000 网格仍对应整图。"""
    if bgr is None or bgr.size == 0:
        raise ValueError("空图")
    h, w = bgr.shape[:2]
    if max(h, w) > max_side:
        scale = max_side / float(max(h, w))
        bgr = cv2.resize(bgr, (int(round(w * scale)), int(round(h * scale))), interpolation=cv2.INTER_AREA)
    fd, path = tempfile.mkstemp(suffix=".jpg")
    os.close(fd)
    ok, buf = cv2.imencode(".jpg", bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
    if not ok:
        raise RuntimeError("无法写 Qwen 缩图")
    buf.tofile(path)
    return path


def _save_temp_overlay(bgr: np.ndarray) -> str:
    return write_qwen_view(bgr)


def _instance_from_mask(label, xyxy, mask, task: str, extra_points, gate_ok, n_tries, confidence="low"):
    poly = mask_to_polygon(mask)
    if not poly:
        return None
    item = {
        "label": label,
        "point": box_center(xyxy),
        "box": list(xyxy),
        "polygon": poly,
        "bbox": polygon_to_bbox_pts(poly),
        "gate_ok": bool(gate_ok),
        "n_tries": int(n_tries),
        "extra_points": extra_points or [],
        "confidence": parse_confidence({"confidence": confidence}),
    }
    if task == "detect":
        item["shape_type"] = "rectangle"
        bb = item["bbox"]
        item["points"] = [bb[0], bb[2]]
    else:
        item["shape_type"] = "polygon"
        item["points"] = poly
    return item


def sam_gated_instances(qwen, sam, rgb, boxed, task: str, gate=True) -> list:
    if not boxed:
        return []
    mode = gate_mode(gate)
    h, w = rgb.shape[:2]
    with _SAM_LOCK:
        encoded = sam.encode(rgb)
    out = []
    for rec in boxed:
        xyxy = list(rec["box"])
        extra = []
        last_item = None
        gate_ok = False
        n_tries = 0
        conf = parse_confidence(rec)
        do_gate = instance_needs_gate(rec, mode)
        for attempt in range(GATE_ROUNDS + 1):
            n_tries = attempt + 1
            with _SAM_LOCK:
                pinned = [(box_center(xyxy), 1)] + list(extra)
                mask = sam.decode_prompt(encoded, box=xyxy, extra_points=pinned)
            item = _instance_from_mask(
                rec["label"], xyxy, mask, task, extra, False, n_tries, conf,
            )
            if item is None:
                break
            last_item = item
            if not do_gate:
                gate_ok = True
                last_item["gate_ok"] = True
                last_item["gate_reason"] = "skip_high" if mode == "low" and conf == "high" else "no_gate"
                last_item["gated"] = False
                break
            overlay = draw_overlay(rgb, [item])
            tmp = _save_temp_overlay(overlay)
            try:
                verdict = qwen_gate(qwen, tmp, rec["label"])
            finally:
                try:
                    os.remove(tmp)
                except OSError:
                    pass
            last_item["gated"] = True
            if verdict.get("ok"):
                gate_ok = True
                last_item["gate_ok"] = True
                last_item["gate_reason"] = verdict.get("reason") or ""
                break
            last_item["gate_reason"] = verdict.get("reason") or ""
            if attempt >= GATE_ROUNDS:
                break
            action = verdict.get("action") or "rebox"
            if action == "rebox":
                parsed = parse_bbox_2d(verdict.get("bbox_2d"), w, h)
                if parsed and accept_rebox(xyxy, parsed[0]):
                    xyxy, _ = parsed
                    extra = []
                    continue
                action = "point"
            if action == "point":
                parsed = parse_point_2d(verdict.get("point_2d"), w, h)
                if not parsed:
                    break
                xy, _ = parsed
                try:
                    lab = int(verdict.get("point_label", 1))
                except (TypeError, ValueError):
                    lab = 1
                extra = extra + [(xy, 1 if lab else 0)]
            else:
                break
        if last_item is not None:
            last_item["gate_ok"] = gate_ok
            last_item["n_tries"] = n_tries
            last_item["point"] = box_center(xyxy)
            last_item["box"] = list(xyxy)
            last_item["confidence"] = conf
            last_item["gated"] = bool(last_item.get("gated"))
            out.append(last_item)
    return out


def write_classes_yaml(dataset_root: str, classes) -> str:
    path = os.path.join(dataset_root, "classes.yaml")
    lines = [f"nc: {len(classes)}", "names:"]
    for i, name in enumerate(classes):
        lines.append(f"  {i}: {name}")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return path


def write_labelme(json_path: str, image_abs: str, w: int, h: int, instances: list):
    json_dir = os.path.dirname(os.path.abspath(json_path))
    rel = os.path.relpath(os.path.abspath(image_abs), json_dir).replace("\\", "/")
    shapes = []
    for inst in instances:
        en = json_label(inst["label"])
        if not en or _has_cjk(en):
            raise RuntimeError(f"jsons 不能写中文 label：{inst.get('label')!r}")
        shapes.append({
            "label": en,
            "points": [[float(x), float(y)] for x, y in inst["points"]],
            "group_id": None,
            "shape_type": inst["shape_type"],
            "flags": {},
        })
    data = {
        "version": "0.1.4",
        "flags": {},
        "shapes": shapes,
        "imagePath": rel,
        "imageData": None,
        "imageHeight": int(h),
        "imageWidth": int(w),
    }
    write_json(json_path, data)


def write_yolo_txt(txt_path: str, w: int, h: int, instances: list, classes, task: str):
    name2id = {n: i for i, n in enumerate(classes)}
    lines = []
    for inst in instances:
        cid = name2id.get(inst["label"])
        if cid is None:
            continue
        pts = inst["points"]
        if task == "detect":
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            xmin, xmax = min(xs), max(xs)
            ymin, ymax = min(ys), max(ys)
            if xmax <= xmin or ymax <= ymin:
                continue
            row = [
                cid,
                ((xmin + xmax) / 2) / w,
                ((ymin + ymax) / 2) / h,
                (xmax - xmin) / w,
                (ymax - ymin) / h,
            ]
        else:
            if len(pts) < 3:
                continue
            row = [cid]
            for x, y in pts:
                row.extend([x / w, y / h])
        lines.append(" ".join(f"{v:.6g}" if not isinstance(v, int) else str(v) for v in row))
    ensure_dir(os.path.dirname(txt_path) or ".")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + ("\n" if lines else ""))


_CJK_FONT = None


def _cjk_font_path() -> str:
    global _CJK_FONT
    if _CJK_FONT is not None:
        return _CJK_FONT
    windir = os.environ.get("WINDIR") or os.environ.get("SystemRoot") or ""
    cands = [
        os.path.join(windir, "Fonts", "msyh.ttc"),
        os.path.join(windir, "Fonts", "msyhbd.ttc"),
        os.path.join(windir, "Fonts", "simhei.ttf"),
        os.path.join(windir, "Fonts", "simsun.ttc"),
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    ]
    _CJK_FONT = next((p for p in cands if p and os.path.isfile(p)), "")
    return _CJK_FONT


def _ascii_overlay_label(label: str) -> str:
    en = json_label(label)
    if en:
        return en
    blob = current_priors().alias_blob(label)
    for tok in blob.split():
        if tok.isascii() and any(c.isalpha() for c in tok):
            return tok
    stripped = "".join(c for c in str(label or "") if c.isascii() and (c.isalnum() or c in "-_"))
    return stripped or "obj"


def overlay_caption(inst) -> str:
    label = str((inst or {}).get("label") or "")
    if not _cjk_font_path():
        label = _ascii_overlay_label(label)
    if (inst or {}).get("confidence") == "low" or (inst or {}).get("gated"):
        return f"{label}*"
    return label


def _inst_xyxy(inst):
    if inst.get("bbox") and len(inst["bbox"]) >= 3:
        return [
            float(inst["bbox"][0][0]), float(inst["bbox"][0][1]),
            float(inst["bbox"][2][0]), float(inst["bbox"][2][1]),
        ]
    box = inst.get("box") or []
    if len(box) >= 4:
        return [float(v) for v in box[:4]]
    pts = inst.get("points") or []
    if len(pts) >= 2:
        xs = [float(p[0]) for p in pts]
        ys = [float(p[1]) for p in pts]
        return [min(xs), min(ys), max(xs), max(ys)]
    return None


CLASS_PALETTE = [
    (0, 200, 80), (0, 180, 255), (40, 40, 220),
    (180, 80, 220), (220, 140, 20), (80, 200, 200),
]


def _class_color(label: str) -> tuple:
    name = str(label or "").strip().lower() or "obj"
    acc = 0
    for ch in name:
        acc = (acc * 33 + ord(ch)) & 0xFFFFFFFF
    return CLASS_PALETTE[acc % len(CLASS_PALETTE)]


def _line_width(h, w) -> int:
    return max(1, round((h + w) / 2 * 0.0006))


def _font_size(lw: int) -> int:
    return max(11, min(16, lw * 6))


def _draw_dashed_rect(img, pt1, pt2, color, thickness=1, dash=8, gap=6):
    x1, y1 = int(pt1[0]), int(pt1[1])
    x2, y2 = int(pt2[0]), int(pt2[1])
    if x2 < x1:
        x1, x2 = x2, x1
    if y2 < y1:
        y1, y2 = y2, y1
    segs = [
        ((x1, y1), (x2, y1)),
        ((x2, y1), (x2, y2)),
        ((x2, y2), (x1, y2)),
        ((x1, y2), (x1, y1)),
    ]
    for (ax, ay), (bx, by) in segs:
        dist = ((bx - ax) ** 2 + (by - ay) ** 2) ** 0.5
        if dist < 1:
            continue
        step = float(dash + gap)
        n = max(1, int(dist / step) + 1)
        for i in range(n):
            t0 = min(1.0, (i * step) / dist)
            t1 = min(1.0, (i * step + dash) / dist)
            if t1 <= t0:
                continue
            p0 = (int(round(ax + (bx - ax) * t0)), int(round(ay + (by - ay) * t0)))
            p1 = (int(round(ax + (bx - ax) * t1)), int(round(ay + (by - ay) * t1)))
            cv2.line(img, p0, p1, color, thickness, cv2.LINE_AA)


QWEN_BOX_COLOR = (0, 220, 255)


def _draw_qwen_box(vis, box, thickness=1):
    if not box or len(box) < 4:
        return
    x0, y0, x1, y1 = [int(v) for v in box[:4]]
    _draw_dashed_rect(vis, (x0, y0), (x1, y1), QWEN_BOX_COLOR, thickness=thickness)


def _text_wh(text: str, font_size: int):
    font_path = _cjk_font_path()
    if font_path:
        from PIL import ImageFont
        font = ImageFont.truetype(font_path, font_size)
        if hasattr(font, "getbbox"):
            x0, y0, x1, y1 = font.getbbox(text)
            tw, th = int(x1 - x0), int(y1 - y0)
        else:
            tw, th = font.getsize(text)
    else:
        (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, font_size / 22.0, 1)
    tw = max(int(tw), int(round(font_size * max(1, len(text)) * 0.62)))
    th = max(int(th), int(font_size))
    return tw, th


def _put_label_bar(bgr, xyxy, text, color, font_size: int) -> np.ndarray:
    """Ultralytics / SAM plot：框顶色条 + 白字。框太矮则只画框不贴字。"""
    if not text:
        return bgr
    x0, y0, x1, y1 = [int(v) for v in xyxy[:4]]
    if x1 < x0:
        x0, x1 = x1, x0
    if y1 < y0:
        y0, y1 = y1, y0
    tw, th = _text_wh(text, font_size)
    pad_x, pad_y = 3, 2
    bar_h = th + pad_y * 2
    if (y1 - y0) < bar_h * 1.2:
        return bgr
    outside = y0 - bar_h >= 0
    by0 = y0 - bar_h if outside else y0
    by1 = y0 if outside else y0 + bar_h
    bx1 = min(bgr.shape[1], x0 + tw + pad_x * 2)
    cv2.rectangle(bgr, (x0, by0), (bx1, by1), color, -1, cv2.LINE_AA)
    tx, ty = x0 + pad_x, by0 + pad_y
    font_path = _cjk_font_path()
    if not font_path:
        cv2.putText(
            bgr, text, (tx, by1 - pad_y),
            cv2.FONT_HERSHEY_SIMPLEX, font_size / 22.0, (255, 255, 255), 1, cv2.LINE_AA,
        )
        return bgr
    from PIL import Image, ImageDraw, ImageFont
    pil = Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(pil)
    font = ImageFont.truetype(font_path, font_size)
    draw.text((tx, ty), text, font=font, fill=(255, 255, 255))
    return cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)


def draw_overlay(rgb, instances, pointed=None) -> np.ndarray:
    vis = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    h, w = vis.shape[:2]
    lw = _line_width(h, w)
    font_size = _font_size(lw)
    for inst in instances or []:
        color = _class_color(inst.get("label") or "")
        xyxy = _inst_xyxy(inst)
        if inst.get("shape_type") == "polygon" and len(inst.get("points") or []) >= 3:
            pts = np.array(inst["points"], dtype=np.int32).reshape(-1, 1, 2)
            overlay = vis.copy()
            cv2.fillPoly(overlay, [pts], color)
            vis = cv2.addWeighted(overlay, 0.28, vis, 0.72, 0)
            cv2.polylines(vis, [pts], True, color, lw, cv2.LINE_AA)
        elif xyxy is not None:
            x0, y0, x1, y1 = [int(v) for v in xyxy]
            cv2.rectangle(vis, (x0, y0), (x1, y1), color, lw, cv2.LINE_AA)
        if xyxy is not None:
            vis = _put_label_bar(vis, xyxy, overlay_caption(inst), color, font_size)
    for rec in pointed or []:
        if rec.get("box") and len(rec["box"]) >= 4:
            _draw_qwen_box(vis, rec["box"], thickness=max(1, lw))
        box = rec.get("box") or [0, 0, 0, 0]
        px, py = rec.get("point") or box_center(box)
        cv2.drawMarker(vis, (int(px), int(py)), (0, 0, 255), cv2.MARKER_TILTED_CROSS, 12, 2)
        if len(box) >= 4:
            vis = _put_label_bar(vis, box, overlay_caption(rec) + "?", (0, 0, 255), font_size)
    return vis


def save_overlay(path: str, bgr: np.ndarray):
    ensure_dir(os.path.dirname(path) or ".")
    ok, buf = cv2.imencode(Path(path).suffix or ".jpg", bgr)
    if not ok:
        raise RuntimeError(f"无法写叠图: {path}")
    buf.tofile(path)


def json_exists_ok(path: str) -> bool:
    data = load_json(path, default=None)
    if not data:
        return False
    shapes = data.get("shapes")
    return isinstance(shapes, list)


def boxed_from_labelme(json_path: str, classes) -> list:
    data = load_json(json_path, default=None)
    if not data:
        return []
    out = []
    for sh in data.get("shapes") or []:
        if not isinstance(sh, dict):
            continue
        label = canonical_label(sh.get("label"), classes)
        pts = sh.get("points") or []
        if not label or len(pts) < 2:
            continue
        try:
            xs = [float(p[0]) for p in pts]
            ys = [float(p[1]) for p in pts]
        except (TypeError, ValueError, IndexError):
            continue
        xyxy = [min(xs), min(ys), max(xs), max(ys)]
        if xyxy[2] - xyxy[0] < 2 or xyxy[3] - xyxy[1] < 2:
            continue
        out.append({
            "label": label,
            "box": xyxy,
            "point": box_center(xyxy),
            "confidence": parse_confidence(sh),
        })
    return out


def instances_from_boxes(boxed) -> list:
    out = []
    for rec in boxed or []:
        xyxy = rec["box"]
        x1, y1, x2, y2 = [float(v) for v in xyxy[:4]]
        pts = [[x1, y1], [x2, y2]]
        out.append({
            "label": rec["label"],
            "point": rec.get("point") or box_center(xyxy),
            "box": [x1, y1, x2, y2],
            "polygon": pts,
            "bbox": [[x1, y1], [x2, y1], [x2, y2], [x1, y2]],
            "shape_type": "rectangle",
            "points": pts,
            "gate_ok": True,
            "n_tries": 0,
            "confidence": parse_confidence(rec),
            "gated": False,
            "gate_reason": "groundingpi_box",
        })
    return out


def class_folder_slug(classes) -> str:
    parts = []
    for name in classes or []:
        en = json_label(name) or default_en_label(name)
        slug = re.sub(r"[^a-z0-9]+", "", (en or "").lower())
        if slug:
            parts.append(slug)
    return "-".join(parts)


def default_jsons_dirname(task: str, classes=None) -> str:
    return JSON_DIRNAME.get((task or "").strip().lower(), "jsons-seg-pre")


def _bare_jsons_kind(name: str) -> str:
    raw = (name or "").strip().lower()
    if raw == "jsons-det-pre":
        return "detect"
    if raw in {"jsons-seg-pre", "jsons-seg", "jsons-segm", "jsons-segment"}:
        return "segment"
    return ""


def resolve_json_dir(dataset_root: str, jsons_arg: str, task: str = "", classes=None, must_exist=False) -> str:
    raw = (jsons_arg or "").strip()
    kind = _bare_jsons_kind(raw) or (task or "").strip().lower()
    default_name = JSON_DIRNAME.get(kind, "jsons-seg-pre")
    if os.path.isabs(raw):
        path = os.path.realpath(raw)
    elif not raw or _bare_jsons_kind(raw):
        path = os.path.realpath(os.path.join(dataset_root, default_name))
    else:
        under_root = os.path.join(dataset_root, raw)
        under_result = os.path.join(pkg_result(dataset_root), raw)
        if must_exist:
            if os.path.isdir(under_root):
                path = os.path.realpath(under_root)
            elif os.path.isdir(under_result):
                path = os.path.realpath(under_result)
            else:
                path = os.path.realpath(under_root)
        else:
            path = os.path.realpath(under_root)
    if must_exist and not os.path.isdir(path):
        raise SystemExit(f"找不到 json 目录: {path}")
    return path


def _elapsed(t0) -> float:
    return round(time.perf_counter() - t0, 3)


def _format_timing(timing: dict) -> str:
    t = timing or {}
    parts = [f"total={t.get('total', 0):.1f}s"]
    for key in ("gpi", "sam"):
        sec = float(t.get(key) or 0)
        if sec > 0.001:
            parts.append(f"{key}={sec:.1f}s")
    return " ".join(parts)


def annotate_file(gpi, sam, image_abs: str, classes, task: str, direct_box=False, boxed=None, gate="off"):
    t_all = time.perf_counter()
    timing = {"gpi": 0.0, "sam": 0.0}
    rgb = _read_rgb(image_abs)
    h, w = rgb.shape[:2]
    use_direct = bool(direct_box) or (task == "detect") or sam is None
    mode = "off" if use_direct else gate_mode(gate)
    if boxed is None:
        t0 = time.perf_counter()
        boxed = gpi_boxes(gpi, image_abs, classes)
        timing["gpi"] = _elapsed(t0)
    instances = []
    sam_error = ""
    if boxed:
        t0 = time.perf_counter()
        try:
            if use_direct:
                instances = instances_from_boxes(boxed)
            else:
                instances = sam_gated_instances(gpi, sam, rgb, boxed, task, gate=mode)
        except Exception as e:
            sam_error = str(e)
        timing["sam"] = _elapsed(t0)
    n_gate_ok = sum(1 for i in instances if i.get("gate_ok"))
    n_retried = sum(1 for i in instances if int(i.get("n_tries") or 1) > 1)
    n_gated = sum(1 for i in instances if i.get("gated"))
    n_skip_gate = sum(1 for i in instances if not i.get("gated"))
    n_gate_pass = sum(1 for i in instances if i.get("gated") and i.get("gate_ok"))
    n_low = sum(1 for r in boxed if parse_confidence(r) == "low")
    n_high = sum(1 for r in boxed if parse_confidence(r) == "high")
    timing["total"] = _elapsed(t_all)
    return {
        "image_abs": image_abs,
        "width": w,
        "height": h,
        "boxed": boxed,
        "pointed": boxed,
        "instances": instances,
        "n_boxes": len(boxed),
        "n_points": len(boxed),
        "n_kept": len(instances),
        "n_gate_ok": n_gate_ok,
        "n_retried": n_retried,
        "n_gated": n_gated,
        "n_skip_gate": n_skip_gate,
        "n_gate_pass": n_gate_pass,
        "n_low": n_low,
        "n_high": n_high,
        "gate": mode,
        "direct_box": bool(direct_box),
        "timing": timing,
        "error": sam_error or None,
    }


def load_or_write_config(dataset_root, task, classes, extra=None):
    old = _pkg_json(dataset_root, "config.json")
    data = dict(old) if isinstance(old, dict) else {}
    data.update({
        "task": task,
        "classes": classes,
        "dataset_root": dataset_root,
    })
    if extra:
        data.update(extra)
    data.pop("class_priors", None)
    data.pop("n_classes", None)
    write_json(config_path(dataset_root), data)
    return data


def load_run_config(dataset_root, task, classes):
    cfg = _pkg_json(dataset_root, "config.json")
    classes = parse_classes(classes) or parse_classes(cfg.get("classes") or [])
    task = (task or cfg.get("task") or "").strip().lower()
    if task not in TASKS:
        raise SystemExit("请指定 --task detect 或 segment")
    if len(classes) < 1:
        raise SystemExit("请提供类别，例如 --classes car,person")
    return task, classes


def cmd_sample(args):
    dataset_root = os.path.realpath(args.dataset)
    classes = parse_classes(args.classes)
    task = (args.task or "").strip().lower()
    if task not in TASKS:
        raise SystemExit("请指定 --task detect 或 segment")
    if len(classes) < 1:
        raise SystemExit("请提供至少一个类别")
    img_dir = resolve_images_dir(dataset_root, args.images)
    files = list_image_files(img_dir)
    if not files:
        raise SystemExit(f"未找到图像: {img_dir}")
    vis_name = normalize_vis_name(str(getattr(args, "vis_dir", None) or "vis"))
    n = min(max(1, int(args.n or 12)), len(files))
    rng = random.Random(int(args.seed))
    picked = rng.sample(files, n)

    vis = ensure_dir(sample_vis_dir(dataset_root, vis_name))
    vis_by_class = {
        name: ensure_dir(sample_vis_class_dir(dataset_root, name, vis_name))
        for name in classes
    }
    jsons_out = ensure_dir(sample_jsons_dir(dataset_root))
    prepare_class_knowledge(
        dataset_root, task, classes, write=True,
        hint_overrides=parse_hint_args(getattr(args, "hint", None)),
        en_overrides=parse_hint_args(getattr(args, "en_label", None)),
    )
    hints = [f"{name}={(current_priors().rec(name).get('hint') or '').strip() or '（空）'}" for name in classes]
    print("当前 hint：" + "；".join(hints))
    load_or_write_config(dataset_root, task, classes, {
        "sample_n": n,
        "seed": int(args.seed),
        "images_dirname": args.images,
        "img_dir": img_dir,
        "gate": args.gate,
    })

    gpi, model_name = _make_gpi(args.base_url, args.model, args.timeout, getattr(args, "thinking", "off"))
    sam = None if task == "detect" else make_client()
    sam_url = "-" if sam is None else get_default_sam()["url"]
    print(
        f"sample 待标注: {n} / 共 {len(files)}（task={task}, classes={classes}, "
        f"groundingpi={model_name}, sam={sam_url}, gate={args.gate}, "
        f"thinking={getattr(args, 'thinking', 'off')}）"
    )

    def _one(path):
        stem = Path(path).stem
        try:
            rec = annotate_file(gpi, sam, path, classes, task, gate=args.gate)
        except Exception as e:
            print(f"⚠ {stem}: {e}")
            rec = {
                "boxed": [], "pointed": [], "instances": [],
                "n_boxes": 0, "n_points": 0, "n_kept": 0,
                "n_gate_ok": 0, "n_retried": 0, "n_gated": 0, "n_skip_gate": 0,
                "n_gate_pass": 0, "n_low": 0, "n_high": 0, "error": str(e),
            }
        rgb = _read_rgb(path)
        h, w = rgb.shape[:2]
        overlay_paths = {}
        boxed = rec.get("boxed") or rec.get("pointed") or []
        instances = rec.get("instances") or []
        for name in classes:
            insts = [i for i in instances if rec_of_class(i, name, classes)]
            um = unmatched_boxes(
                [b for b in boxed if rec_of_class(b, name, classes)],
                insts,
            )
            overlay = draw_overlay(rgb, insts, um)
            out_vis = os.path.join(vis_by_class[name], f"{stem}.jpg")
            save_overlay(out_vis, overlay)
            overlay_paths[name] = out_vis
        out_json = os.path.join(jsons_out, f"{stem}.json")
        write_labelme(out_json, path, w, h, rec.get("instances") or [])
        meta = {
            "stem": stem,
            "image": os.path.relpath(path, dataset_root),
            "json": out_json,
            "n_boxes": rec.get("n_boxes", rec.get("n_points", 0)),
            "n_kept": rec.get("n_kept", 0),
            "n_gate_ok": rec.get("n_gate_ok", 0),
            "n_retried": rec.get("n_retried", 0),
            "n_gated": rec.get("n_gated", 0),
            "n_skip_gate": rec.get("n_skip_gate", 0),
            "n_gate_pass": rec.get("n_gate_pass", 0),
            "n_low": rec.get("n_low", 0),
            "n_high": rec.get("n_high", 0),
            "time_s": (rec.get("timing") or {}).get("total"),
            "timing": rec.get("timing") or {},
            "overlay": overlay_paths.get(classes[0], ""),
            "overlays": overlay_paths,
            "error": rec.get("error"),
            "instances": [
                {
                    "label": i["label"],
                    "point": i.get("point"),
                    "shape_type": i["shape_type"],
                    "gate_ok": i.get("gate_ok"),
                    "n_tries": i.get("n_tries", 1),
                    "confidence": i.get("confidence") or "",
                    "gated": bool(i.get("gated")),
                }
                for i in (rec.get("instances") or [])
            ],
        }
        return meta

    rows = []
    with ThreadPoolExecutor(max_workers=max(1, int(args.workers))) as pool:
        futs = [pool.submit(_one, p) for p in picked]
        for fut in tqdm(as_completed(futs), total=len(futs), desc="sample"):
            rows.append(fut.result())
    rows.sort(key=lambda r: r.get("stem") or "")
    md = os.path.join(pkg_cache(dataset_root), "sample.md")
    lines = [
        "# Sample 框提示+SAM+低置信门控",
        "",
        f"- **task**: {task}",
        f"- **classes**: {', '.join(classes)}",
        f"- **n**: {len(rows)}",
        f"- **gate**: {args.gate}（low=只审低置信；叠图 `*` = 低置信或走过门控）",
        f"- **原图**：`{img_dir}`",
        f"- **LabelMe**：`{jsons_out}`",
        f"- **叠图**：`{vis}/<类名>/`",
        f"- **类别表**：`{classes_json_path(dataset_root)}`",
        "",
        "叠图仅供浏览：彩框/彩膜 = 终态；黄虚线 = GroundingPI 框；红叉 = 未出掩膜。按类别分目录。",
        "",
        "| stem | 框数 | 高/低置信 | 跳过门控 | 门控过 | 门控通过 | 重试 | 叠图 | LabelMe |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for rec in rows:
        ov = rec.get("overlays") or {}
        ov_cell = "；".join(f"`{ov[n]}`" for n in classes if ov.get(n)) or f"`{rec.get('overlay','')}`"
        lines.append(
            f"| {rec.get('stem','')} | {rec.get('n_boxes',0)} | "
            f"{rec.get('n_high',0)}/{rec.get('n_low',0)} | "
            f"{rec.get('n_skip_gate',0)} | {rec.get('n_gated',0)} | "
            f"{rec.get('n_gate_pass',0)} | {rec.get('n_retried',0)} | {ov_cell} | "
            f"`{rec.get('json','')}` |"
            + (f"  \n  error: {rec.get('error')}" if rec.get("error") else "")
        )
    with open(md, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"sample 完成 → 叠图 {vis}/<类名>/")
    for name in classes:
        print(f"  {name}: {vis_by_class[name]}")
    print("看 vis 后回复「直接全量」再 run。")


def cmd_run(args):
    dataset_root = os.path.realpath(args.dataset)
    task, classes = load_run_config(dataset_root, args.task, args.classes)
    img_dir = resolve_images_dir(dataset_root, args.images)
    files = list_image_files(img_dir)
    if args.limit:
        files = files[: int(args.limit)]
    if not files:
        raise SystemExit(f"未找到图像: {img_dir}")

    prepare_class_knowledge(
        dataset_root, task, classes, write=True,
        hint_overrides=parse_hint_args(getattr(args, "hint", None)),
        en_overrides=parse_hint_args(getattr(args, "en_label", None)),
    )
    json_dir = ensure_dir(resolve_json_dir(
        dataset_root, getattr(args, "jsons", "") or "", task, classes=classes,
    ))
    jsons_rel = os.path.relpath(json_dir, dataset_root)
    direct_box = bool(getattr(args, "direct_box", False))
    from_jsons = (getattr(args, "from_jsons", "") or "").strip()
    from_dir = resolve_json_dir(
        dataset_root, from_jsons, task, classes=classes, must_exist=True,
    ) if from_jsons else ""
    if from_dir and not os.path.isdir(from_dir):
        raise SystemExit(f"找不到 --from-jsons 目录: {from_dir}")
    load_or_write_config(dataset_root, task, classes, {
        "images_dirname": args.images,
        "img_dir": img_dir,
        "jsons_dirname": os.path.basename(json_dir),
        "last_jsons": jsons_rel,
        "last_direct_box": direct_box,
        "last_from_jsons": from_jsons,
        "last_gate": "off" if from_dir else getattr(args, "gate", "off"),
    })

    jobs = []
    n_skip = 0
    for path in files:
        stem = Path(path).stem
        jp = os.path.join(json_dir, f"{stem}.json")
        if not args.force and json_exists_ok(jp):
            n_skip += 1
            continue
        jobs.append(path)

    if from_dir:
        gpi, model_name = None, "from-jsons"
    else:
        gpi, model_name = _make_gpi(args.base_url, args.model, args.timeout, getattr(args, "thinking", "off"))
    sam = None if (direct_box or task == "detect") else make_client()
    print(
        f"run 待标注: {len(jobs)}（跳过已有 {n_skip}，本批 {len(files)}，"
        f"task={task}, jsons={jsons_rel}, direct_box={direct_box}, "
        f"from_jsons={from_jsons or '-'}, gate={'off' if from_dir else getattr(args, 'gate', 'off')}, "
        f"thinking={getattr(args, 'thinking', 'off')}, model={model_name}）"
    )

    n_fail = 0
    n_empty = 0
    n_inst = 0
    n_gate_ok = 0
    n_retried = 0
    n_gated = 0
    n_skip_gate = 0
    n_gate_pass = 0
    t_sum = 0.0

    def _one(path):
        seed = None
        if from_dir:
            seed = boxed_from_labelme(
                os.path.join(from_dir, f"{Path(path).stem}.json"), classes,
            )
        rec = annotate_file(
            gpi, sam, path, classes, task,
            direct_box=direct_box, boxed=seed,
            gate="off" if from_dir else getattr(args, "gate", "off"),
        )
        if rec.get("error") and not rec.get("instances"):
            raise RuntimeError(rec["error"])
        stem = Path(path).stem
        write_labelme(
            os.path.join(json_dir, f"{stem}.json"),
            path, rec["width"], rec["height"], rec["instances"],
        )
        rec["stem"] = stem
        return rec

    if jobs:
        with ThreadPoolExecutor(max_workers=max(1, int(args.workers))) as pool:
            futs = [pool.submit(_one, p) for p in jobs]
            for fut in tqdm(as_completed(futs), total=len(futs), desc="detect_segment"):
                try:
                    rec = fut.result()
                except Exception as e:
                    n_fail += 1
                    print(f"⚠ {e}")
                    continue
                n_inst += rec["n_kept"]
                n_gate_ok += rec.get("n_gate_ok", 0)
                n_retried += rec.get("n_retried", 0)
                n_gated += rec.get("n_gated", 0)
                n_skip_gate += rec.get("n_skip_gate", 0)
                n_gate_pass += rec.get("n_gate_pass", 0)
                t_sum += float((rec.get("timing") or {}).get("total") or 0)
                if rec["n_kept"] == 0:
                    n_empty += 1

    print(f"全量完成 → {json_dir}  （未覆盖其它 json 目录，未写 labels/）")
    print("计数:", json.dumps({
        "ran": len(jobs), "skipped": n_skip, "failed": n_fail,
        "empty": n_empty, "instances": n_inst,
        "gate_ok": n_gate_ok, "retried": n_retried,
        "gated": n_gated, "skip_gate": n_skip_gate, "gate_pass": n_gate_pass,
        "time_s": round(t_sum, 1),
        "time_per_image_s": round(t_sum / max(1, len(jobs) - n_fail), 1) if jobs else 0,
    }, ensure_ascii=False))


def cmd_image(args):
    classes = parse_classes(args.classes)
    task = (args.task or "detect").strip().lower()
    if task not in TASKS:
        raise SystemExit("请指定 --task detect 或 segment")
    if len(classes) < 1:
        raise SystemExit("请提供至少一个类别")
    if not os.path.isfile(args.image):
        raise SystemExit(f"图像不存在: {args.image}")
    ds = (getattr(args, "dataset", None) or "").strip()
    prepare_class_knowledge(
        os.path.realpath(ds) if ds else "", task, classes, write=bool(ds),
        hint_overrides=parse_hint_args(getattr(args, "hint", None)),
        en_overrides=parse_hint_args(getattr(args, "en_label", None)),
    )
    gpi, model_name = _make_gpi(args.base_url, args.model, args.timeout, getattr(args, "thinking", "off"))
    sam = None if task == "detect" else make_client()
    rec = annotate_file(
        gpi, sam, os.path.abspath(args.image), classes, task,
        gate=args.gate,
    )
    out = {
        "image": rec["image_abs"],
        "task": task,
        "model": model_name,
        "gate": rec.get("gate", args.gate),
        "thinking": "on" if thinking_on(getattr(args, "thinking", "off")) else "off",
        "n_boxes": rec["n_boxes"],
        "n_kept": rec["n_kept"],
        "n_high": rec.get("n_high", 0),
        "n_low": rec.get("n_low", 0),
        "n_gated": rec.get("n_gated", 0),
        "n_skip_gate": rec.get("n_skip_gate", 0),
        "n_gate_pass": rec.get("n_gate_pass", 0),
        "n_gate_ok": rec.get("n_gate_ok", 0),
        "n_retried": rec.get("n_retried", 0),
        "timing": rec.get("timing") or {},
        "boxed": rec["boxed"],
        "instances": [
            {
                "label": i["label"],
                "point": i.get("point"),
                "box": i.get("box"),
                "shape_type": i["shape_type"],
                "bbox": i["bbox"],
                "n_pts": len(i["points"]),
                "confidence": i.get("confidence") or "",
                "gated": bool(i.get("gated")),
                "gate_ok": i.get("gate_ok"),
                "n_tries": i.get("n_tries", 1),
                "gate_reason": i.get("gate_reason") or "",
            }
            for i in rec["instances"]
        ],
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"time: {_format_timing(rec.get('timing') or {})}  model={model_name}")
    if rec.get("error"):
        print(f"⚠ SAM: {rec['error']}")
    overlay_path = (args.overlay or "").strip()
    if overlay_path:
        rgb = _read_rgb(rec["image_abs"])
        vis = draw_overlay(
            rgb, rec["instances"],
            unmatched_boxes(rec.get("boxed") or rec.get("pointed") or [], rec["instances"]),
        )
        save_overlay(overlay_path, vis)
        print(f"overlay: {overlay_path}")


def _add_shared(p, require_dataset=True, require_classes=False):
    if require_dataset:
        p.add_argument("--dataset", required=True, help="数据集根目录（含 images/）")
    else:
        p.add_argument("--dataset", default="", help="可选；有则写入 draft 类别知识")
    p.add_argument("--images", default="images", help="图像子目录名，默认 images")
    p.add_argument("--task", default="", help="detect | segment")
    p.add_argument("--classes", default="", required=require_classes, help="类别，逗号分隔")
    p.add_argument("--base_url", default="", help="空则读 vllm_server.json 的 GroundingPI")
    p.add_argument("--model", default="")
    p.add_argument("--timeout", type=int, default=600)
    p.add_argument("--workers", type=int, default=2)
    p.add_argument("--force", action="store_true")
    p.add_argument("--jsons", default="", help="LabelMe 输出目录；空则 <dataset>/jsons-det-pre 或 jsons-seg-pre")
    p.add_argument("--direct-box", action="store_true", help="只写 GroundingPI 框，不调 SAM（detect 默认如此）")
    p.add_argument(
        "--gate", choices=list(GATE_MODES), default="off",
        help="off=不审 SAM（默认）；low/all=旧流程 SAM 叠图复审。新的误检过滤走 0-SmartImage/label_grade",
    )
    p.add_argument(
        "--thinking", choices=("on", "off"), default="off",
        help="off=关闭模型思考直接出 JSON（默认）；on=允许推理（更慢）",
    )
    p.add_argument(
        "--hint", action="append", default=[],
        help="类别提示，可重复：类名=提示。sample 前由 Skill 向用户确认后再传入",
    )
    p.add_argument(
        "--en-label", action="append", default=[],
        help="写入 jsons 的英文标签，可重复：中文名=EnglishName。jsons 禁止中文 label",
    )


def parse_args():
    p = argparse.ArgumentParser(description="GroundingPI 给框；segment 再走 SAM → jsons-det-pre | jsons-seg-pre")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("sample", help="抽样本叠图，给人看 vis")
    _add_shared(s, require_classes=True)
    s.add_argument("--n", type=int, default=12)
    s.add_argument("--seed", type=int, default=0)
    s.add_argument("--vis-dir", default="vis", help="叠图根目录，位于 cache/sample/ 下，默认 vis；其下按类别分子目录")

    r = sub.add_parser("run", help="全量写入 jsons-det-pre 或 jsons-seg-pre")
    _add_shared(r)
    r.add_argument("--limit", type=int, default=None)
    r.add_argument("--from-jsons", default="", help="从已有 LabelMe 目录读框，只跑 SAM，不调 GroundingPI")

    i = sub.add_parser("image", help="单张图给框+SAM+门控，打印 JSON 并写叠图")
    i.add_argument("--image", required=True)
    i.add_argument("--overlay", default="")
    _add_shared(i, require_dataset=False, require_classes=True)
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    if args.cmd == "sample":
        cmd_sample(args)
    elif args.cmd == "run":
        cmd_run(args)
    elif args.cmd == "image":
        cmd_image(args)
    else:
        raise SystemExit("未知子命令")
