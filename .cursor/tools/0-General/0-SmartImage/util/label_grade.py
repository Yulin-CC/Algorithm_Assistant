"""
# @Author: Yullin
# @Date: 2026-11-11
# @Description: 逐个框或掩膜定档 grade=fit|adjust|wrong。--masks 时核对两期变化掩膜。不改写标注。
# @Command: python util/label_grade.py --dataset /path --jsons jsons-det-pre-car
# @Command: python util/label_grade.py --dataset /path --masks label --prompt-file task.txt
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

_PKG_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
_REPO = os.path.normpath(os.path.join(_PKG_ROOT, "..", "..", ".."))
_MODEL_UTIL = os.path.join(_REPO, "server", "util")
if _MODEL_UTIL not in sys.path:
    sys.path.insert(0, _MODEL_UTIL)

from tqdm import tqdm

tqdm.monitor_interval = 0

import cv2

from common import ensure_dir, load_json, resolve_images_dir, write_json
from describe import _make_client
from vllm_client import extract_json_object

from overlay import (
    PALETTE,
    TASK_SLUG,
    cd_layout,
    crop_name_for,
    draw_shapes,
    instance_crop_view,
    model_dir,
    model_name_for,
    needs_true_color,
    pkg_draft_progress,
    qa_jsons_dir,
    render_shape,
    resolve_image,
    resolve_jsons_dir,
    save_change_item_view,
    save_change_overview,
    save_jpg,
    shape_kind,
    summary_path,
    use_slug,
    view_kind,
    vis_dir,
    write_qwen_view,
)

SYSTEM_QA = "只输出一个 JSON 对象，不要 markdown。"

_GRADE_ASK = (
    "严格按顺序。"
    "第一步只判断区域内有没有该类别。"
    "没有，或主体是别的东西（车道线、自行车标志、行人标志）："
    "present=false，grade=wrong，issue 为空。这一步已经否掉，就不要再写框的质量。"
    "能看到该类别的一部分也算有，包括组合箭头只露出一支：present=true，不得给 wrong。"
    "第二步只在 present=true 之后看区域。"
    "目标有一块明显在区域外，包括组合箭头的另一支：grade=adjust，issue=incomplete。"
    "区域漏掉目标一块，又多罩了旁边一块：grade=adjust，issue=shifted。"
    "区域里主要是大块空路面，目标只占一小部分：grade=adjust，issue=oversize。"
    "没有这些问题：grade=fit，issue 为空。"
    "多种问题同时出现时，先取不完整，再取错位，再取过大。"
    "reason 只写这张图里看到的事实。"
)

_GRADE_JSON_FMT = (
    "只返回一个 JSON："
    '{{"present":true,"grade":"adjust","issue":"oversize","reason":"..."}}'
    ' 或 {{"present":true,"grade":"adjust","issue":"incomplete","reason":"..."}}'
    ' 或 {{"present":true,"grade":"adjust","issue":"shifted","reason":"..."}}'
    ' 或 {{"present":true,"grade":"fit","issue":"","reason":"..."}}'
    ' 或 {{"present":false,"grade":"wrong","issue":"","reason":"..."}}。'
)

_GRADE_JSON = (
    "只返回一个 JSON："
    '{"present":true,"grade":"adjust","issue":"oversize","reason":"..."}'
    ' 或 {"present":true,"grade":"adjust","issue":"incomplete","reason":"..."}'
    ' 或 {"present":true,"grade":"adjust","issue":"shifted","reason":"..."}'
    ' 或 {"present":true,"grade":"fit","issue":"","reason":"..."}'
    ' 或 {"present":false,"grade":"wrong","issue":"","reason":"..."}。'
)

_GRADE_FOLD = (
    "逐个看完再折成一条："
    "有一个完全没有对应目标则 grade=wrong；"
    "否则有一个不完整、错位或过大则 grade=adjust，issue 取不完整，其次错位，其次过大；"
    "否则 grade=fit，issue 为空。"
)

PROMPT_ONE = (
    "淡色区域就是要检查的框。类别是「{label}」。"
    + _GRADE_ASK
    + _GRADE_JSON_FMT
)

PROMPT_ALL = (
    "每个淡色区域是一个要检查的框。类别写在框上。"
    + _GRADE_ASK
    + _GRADE_FOLD
    + _GRADE_JSON
)

PROMPT_MASK = (
    "彩色轮廓是要检查的掩膜，淡色只标出范围。类别是「{label}」。"
    + _GRADE_ASK
    + _GRADE_JSON_FMT
)

PROMPT_MASK_ALL = (
    "每个彩色轮廓是一个要检查的掩膜。类别写在轮廓上。"
    + _GRADE_ASK
    + _GRADE_FOLD
    + _GRADE_JSON
)

PROMPT_MIXED_ALL = (
    "淡色矩形和彩色轮廓各是一个要检查的区域。类别写在区域上。"
    + _GRADE_ASK
    + _GRADE_FOLD
    + _GRADE_JSON
)





def prompt_for(shapes, label=None) -> str:
    kind = view_kind(shapes)
    if label is None:
        outline = any(needs_true_color(s.get("label")) for s in shapes or [])
    else:
        outline = needs_true_color(label)
    if kind == "rectangle":
        if label is None:
            head = (
                "彩色细线框出每个要检查的区域，线内是原图。线的颜色不是目标的颜色。类别写在框上。"
                if outline else
                "每个淡色区域是一个要检查的框。类别写在框上。"
            )
            return head + _GRADE_ASK + _GRADE_FOLD + _GRADE_JSON
        head = (
            "彩色细线框出要检查的区域，线内是原图。线的颜色不是目标的颜色。"
            if outline else
            "淡色区域就是要检查的框。"
        )
        return head + "类别是「{label}」。".format(label=label) + _GRADE_ASK + _GRADE_JSON_FMT
    if label is None:
        head = (
            "彩色细线是要检查的掩膜，线内是原图。线的颜色不是目标的颜色。"
            if outline else
            "每个彩色轮廓是一个要检查的掩膜，淡色只标出范围。"
        )
        if kind != "polygon":
            head = (
                "彩色细线标出要检查的区域，线内是原图。线的颜色不是目标的颜色。"
                if outline else
                "淡色矩形和彩色轮廓各是一个要检查的区域。"
            )
        return head + "类别写在区域上。" + _GRADE_ASK + _GRADE_FOLD + _GRADE_JSON
    head = (
        "彩色细线是要检查的掩膜，线内是原图。线的颜色不是目标的颜色。"
        if outline else
        "彩色轮廓是要检查的掩膜，淡色只标出范围。"
    )
    return head + "类别是「{label}」。".format(label=label) + _GRADE_ASK + _GRADE_JSON_FMT




GRADES = {"fit", "adjust", "wrong"}
ISSUES = {"oversize", "incomplete", "shifted"}


def failed_grade(reason: str, source: str = "failed") -> dict:
    return {
        "ok": False,
        "verdict": "wrong",
        "grade": "wrong",
        "issue": "",
        "present": False,
        "reason": reason,
        "source": source,
    }


def _affirmed(text: str, word: str) -> bool:
    start = 0
    while True:
        idx = text.find(word, start)
        if idx < 0:
            return False
        prefix = text[max(0, idx - 6):idx]
        if not any(mark in prefix for mark in ("没有", "未", "不", "无")):
            return True
        start = idx + len(word)


def issue_from_reason(reason: str) -> str:
    text = str(reason or "")
    if any(_affirmed(text, word) for word in ("框外", "区域外", "不完整", "未完全", "没有完全", "另一支", "漏掉")):
        return "incomplete"
    if any(_affirmed(text, word) for word in ("过大", "太大", "空地", "空白", "空路面", "多个")):
        return "oversize"
    if _affirmed(text, "错位"):
        return "shifted"
    return ""


def parse_present(data: dict):
    if "present" not in data:
        return None
    flag = data.get("present")
    if isinstance(flag, str):
        return flag.strip().lower() in {"1", "true", "yes", "y"}
    return bool(flag)


def apply_grade(grade: str, issue: str, reason: str, source: str, present=None) -> dict:
    if grade not in GRADES:
        grade = "wrong"
    issue = str(issue or "").strip().lower()
    if present is True and grade == "wrong":
        grade = "adjust"
        if issue not in ISSUES:
            issue = issue_from_reason(reason)
    if grade != "adjust" or issue not in ISSUES:
        issue = ""
    if present is None:
        present = grade != "wrong"
    ok = grade != "wrong"
    return {
        "ok": ok,
        "verdict": "ok" if ok else "wrong",
        "grade": grade,
        "issue": issue,
        "present": bool(present),
        "reason": reason,
        "source": source,
    }


def _legacy_ok(data: dict) -> bool:
    flag = data.get("ok")
    if isinstance(flag, str):
        flag = flag.strip().lower() in {"1", "true", "yes", "y", "ok"}
    elif flag is None:
        flag = None
    else:
        flag = bool(flag)
    verdict = str(data.get("verdict") or "").strip().lower()
    if verdict in {"wrong", "bad", "fail", "false", "no"}:
        return False
    if verdict in {"ok", "keep", "good", "true", "yes"}:
        return True
    if flag is None:
        return False
    return flag


def grade_from_raw(data: dict) -> str:
    grade = str(data.get("grade") or "").strip().lower()
    if grade in GRADES:
        return grade
    fit = str(data.get("fit") or "").strip().lower()
    if fit == "miss":
        return "wrong"
    if fit in GRADES:
        return fit
    if "ok" not in data and not str(data.get("verdict") or "").strip():
        return "wrong"
    return "fit" if _legacy_ok(data) else "wrong"


def parse_verdict(raw) -> dict:
    try:
        data = extract_json_object(raw)
    except Exception as e:
        return failed_grade(f"parse_fail:{e}")
    if not isinstance(data, dict):
        return failed_grade("parse_fail:not_object")
    issue = str(data.get("issue") or "").strip().lower()
    return apply_grade(
        grade_from_raw(data),
        issue,
        str(data.get("reason") or ""),
        "vllm",
        present=parse_present(data),
    )


def normalize_grade(verdict: dict) -> dict:
    """框和掩膜同一套档位。旧结果里的 fit=miss 读成 wrong，不凭空补 adjust。"""
    return apply_grade(
        grade_from_raw(verdict),
        str(verdict.get("issue") or ""),
        str(verdict.get("reason") or ""),
        str(verdict.get("source") or "vllm"),
        present=parse_present(verdict),
    )


def item_grade(item: dict) -> str:
    if not isinstance(item, dict):
        return ""
    grade = str(item.get("grade") or "").strip().lower()
    if grade in GRADES:
        return grade
    fit = str(item.get("fit") or "").strip().lower()
    if fit == "miss" or fit == "wrong":
        return "wrong"
    if fit == "adjust":
        return "adjust"
    if fit == "fit":
        return "fit"
    if item.get("verdict") == "wrong" or item.get("ok") is False:
        return "wrong"
    if item.get("verdict") == "ok" or item.get("ok") is True:
        return "fit"
    return ""


def count_grades(items) -> dict:
    n_fit = sum(1 for it in items if item_grade(it) == "fit")
    n_adjust = sum(1 for it in items if item_grade(it) == "adjust")
    n_wrong = sum(1 for it in items if item_grade(it) == "wrong")
    return {
        "fit": n_fit,
        "adjust": n_adjust,
        "wrong": n_wrong,
        "ok": n_fit + n_adjust,
    }


def ask_overlay(client, bgr, prompt: str, model_path: str = "") -> dict:
    if model_path and os.path.isfile(model_path) and bgr is None:
        view = model_path
    else:
        view = write_qwen_view(bgr, path=model_path)
    try:
        raw = client.describe_image(
            view, prompt, system=SYSTEM_QA, max_tokens=256, temperature=0,
        )
    finally:
        if not model_path:
            try:
                os.remove(view)
            except OSError:
                pass
    return parse_verdict(raw)


def verdict_color(item: dict):
    grade = item_grade(item)
    if grade == "adjust":
        return (0, 220, 255)
    if grade == "wrong":
        return (40, 40, 255)
    return (40, 255, 40)




def paint_det_overview(bgr, shapes, items):
    overview = bgr.copy()
    if items and items[0].get("index") is None:
        color = verdict_color(items[0])
        for shape in shapes:
            render_shape(overview, shape, color, for_vis=True)
        return overview
    for item in items:
        idx = item.get("index")
        if not isinstance(idx, int) or idx < 0 or idx >= len(shapes):
            continue
        render_shape(overview, shapes[idx], verdict_color(item), for_vis=True)
    return overview


def dump_progress(dataset_root: str, payload: dict, slug=None, part=None) -> None:
    write_json(pkg_draft_progress(dataset_root, slug, part), payload)


def collect_jobs(dataset_root, jsons_dir, images_dir, mode: str, limit=None, force=False, slug=None, part=None):
    files = sorted(Path(jsons_dir).glob("*.json"))
    if limit:
        files = files[: int(limit)]
    jobs = []
    skipped = 0
    slug = use_slug(slug)
    for jp in files:
        out_p = os.path.join(qa_jsons_dir(dataset_root, slug, part), f"{jp.stem}.json")
        existing = load_json(out_p) if os.path.isfile(out_p) else None
        if not force and existing and existing.get("source") not in {"failed", "placeholder"}:
            skipped += 1
            continue
        data = load_json(str(jp), default={}) or {}
        shapes = data.get("shapes") if isinstance(data.get("shapes"), list) else []
        try:
            image_abs = resolve_image(dataset_root, str(jp), data, images_dir)
        except FileNotFoundError as e:
            jobs.append({
                "stem": jp.stem,
                "json_path": str(jp),
                "out_p": out_p,
                "error": str(e),
                "shapes": [],
                "image_abs": "",
                "mode": mode,
                "slug": slug,
                "part": part,
            })
            continue
        jobs.append({
            "stem": jp.stem,
            "json_path": str(jp),
            "out_p": out_p,
            "error": None,
            "shapes": shapes,
            "image_abs": image_abs,
            "mode": mode,
            "slug": slug,
            "part": part,
        })
    return jobs, skipped, len(files)


def run_job(client, dataset_root: str, job: dict) -> dict:
    stem = job["stem"]
    if job.get("error"):
        rec = {
            "stem": stem,
            "source": "failed",
            "error": job["error"],
            "n": 0,
            "fit": 0,
            "ok": 0,
            "wrong": 0,
            "adjust": 0,
            "items": [],
        }
        write_json(job["out_p"], rec)
        return rec

    bgr = cv2.imread(job["image_abs"])
    if bgr is None:
        rec = {
            "stem": stem,
            "source": "failed",
            "error": f"无法读图 {job['image_abs']}",
            "n": 0,
            "fit": 0,
            "ok": 0,
            "wrong": 0,
            "adjust": 0,
            "items": [],
        }
        write_json(job["out_p"], rec)
        return rec

    m_dir = model_dir(dataset_root, job.get("slug"), job.get("part"))
    v_dir = vis_dir(dataset_root, job.get("slug"), job.get("part"))
    ensure_dir(m_dir)
    ensure_dir(v_dir)
    shapes = job["shapes"]
    items = []
    if not shapes:
        rec = {
            "stem": stem,
            "image": job["image_abs"],
            "source": "empty",
            "error": None,
            "n": 0,
            "fit": 0,
            "ok": 0,
            "wrong": 0,
            "adjust": 0,
            "items": [],
        }
        write_json(job["out_p"], rec)
        return rec

    if job["mode"] == "image":
        kind = view_kind(shapes)
        drawn = draw_shapes(bgr, shapes, highlight=None)
        m_path = os.path.join(m_dir, model_name_for(stem, None))
        verdict = normalize_grade(
            ask_overlay(client, drawn, prompt_for(shapes), model_path=m_path),
        )
        items.append({
            "index": None,
            "label": ",".join(sorted({str(s.get("label") or "") for s in shapes})),
            "shape_type": kind,
            "model": m_path,
            **verdict,
        })
    else:
        for i, shape in enumerate(shapes):
            color = PALETTE[i % len(PALETTE)]
            label = str(shape.get("label") or "object")
            kind = shape_kind(shape)
            m_path = os.path.join(m_dir, model_name_for(stem, i))
            try:
                drawn = instance_crop_view(
                    bgr, shape, color, fill=not needs_true_color(label),
                )
                verdict = normalize_grade(
                    ask_overlay(client, drawn, prompt_for([shape], label=label), model_path=m_path),
                )
            except Exception as e:
                verdict = failed_grade(str(e))
                m_path = ""
            items.append({
                "index": i,
                "label": label,
                "shape_type": kind,
                "model": m_path,
                **verdict,
            })

    overview = paint_det_overview(bgr, shapes, items)
    v_path = os.path.join(v_dir, f"{stem}.jpg")
    save_jpg(v_path, overview)
    counts = count_grades(items)
    rec = {
        "stem": stem,
        "image": job["image_abs"],
        "json": job["json_path"],
        "source": "vllm",
        "error": None,
        "n": len(items),
        **counts,
        "vis": v_path,
        "items": items,
    }
    write_json(job["out_p"], rec)
    return rec


def run_dataset(dataset_root, jsons="jsons-det-pre-car", mode="instance", limit=None,
                force=False, workers=2, timeout=600, base_url="", model="", slug=None, part=None):
    slug = use_slug(slug)
    part = str(part or "").strip() or None
    images_dir = resolve_images_dir(dataset_root, "images")
    jsons_dir = resolve_jsons_dir(dataset_root, jsons)
    if not os.path.isdir(jsons_dir):
        raise SystemExit(f"找不到标注目录: {jsons_dir}")
    ensure_dir(qa_jsons_dir(dataset_root, slug, part))
    ensure_dir(model_dir(dataset_root, slug, part))
    ensure_dir(vis_dir(dataset_root, slug, part))

    jobs, skipped, n_json = collect_jobs(
        dataset_root, jsons_dir, images_dir, mode, limit=limit, force=force, slug=slug, part=part,
    )
    client, model_name = _make_client(base_url, model, timeout)
    dump_progress(dataset_root, {
        "status": "start",
        "dataset": dataset_root,
        "jsons": jsons_dir,
        "jobs": len(jobs),
        "skip": skipped,
        "json_n": n_json,
        "mode": mode,
        "model": model_name,
        "done": 0,
        "fit": 0,
        "ok": 0,
        "wrong": 0,
        "adjust": 0,
        "n": 0,
        "slug": slug,
        "part": part or "",
    }, slug, part)
    print(
        f"{slug} jobs={len(jobs)} skip={skipped} jsons={n_json} "
        f"mode={mode} model={model_name} → {qa_jsons_dir(dataset_root, slug, part)}"
    )
    stats = {"fit": 0, "ok": 0, "wrong": 0, "adjust": 0, "n": 0, "images": 0, "fail": 0, "empty": 0}
    if not jobs:
        table = ensure_views(dataset_root, slug, part)
        summary = {**stats, "skip": skipped, "jsons": jsons_dir, "model": model_name, "part": part or ""}
        write_json(summary_path(dataset_root, slug, part), summary)
        dump_progress(dataset_root, {"status": "done", **summary}, slug, part)
        print("无需质检（均已完成）")
        if table:
            print(f"表格 {table}")
        return summary

    def acc(rec):
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

    with ThreadPoolExecutor(max_workers=max(1, int(workers))) as pool:
        futs = [pool.submit(run_job, client, dataset_root, job) for job in jobs]
        done = 0
        for fut in tqdm(as_completed(futs), total=len(futs), desc=slug):
            rec = fut.result()
            acc(rec)
            done += 1
            dump_progress(dataset_root, {
                "status": "running",
                "done": done,
                "jobs": len(jobs),
                "slug": slug,
                "part": part or "",
                **stats,
            }, slug, part)

    summary = {
        **stats,
        "skip": skipped,
        "jsons": jsons_dir,
        "qa_jsons": qa_jsons_dir(dataset_root, slug, part),
        "model_dir": model_dir(dataset_root, slug, part),
        "vis_dir": vis_dir(dataset_root, slug, part),
        "model": model_name,
        "mode": mode,
        "slug": slug,
        "part": part or "",
    }
    table = ensure_views(dataset_root, slug, part)
    write_json(summary_path(dataset_root, slug, part), summary)
    dump_progress(dataset_root, {"status": "done", **summary}, slug, part)
    print(
        f"label-grade 完成 n={stats['n']} fit={stats['fit']} adjust={stats['adjust']} "
        f"wrong={stats['wrong']} ok={stats['ok']} images={stats['images']} "
        f"fail={stats['fail']} empty={stats['empty']}"
    )
    if table:
        print(f"表格 {table}")
    return summary




def _bind_view_paths(rec, m_dir, v_dir):
    stem = str(rec.get("stem") or "")
    need_paint = False
    dirty = False
    vis = os.path.join(v_dir, f"{stem}.jpg")
    if os.path.isfile(vis):
        if rec.get("vis") != vis:
            rec["vis"] = vis
            dirty = True
    else:
        need_paint = True
    for item in rec.get("items") or []:
        if item.pop("overlay", None):
            dirty = True
        if item.get("view_skip"):
            continue
        name = model_name_for(stem, item.get("index"))
        path = os.path.join(m_dir, name)
        if os.path.isfile(path):
            if item.get("model") != path:
                item["model"] = path
                dirty = True
        elif not (item.get("model") and os.path.isfile(str(item.get("model")))):
            need_paint = True
    return need_paint, dirty


def paint_saved_det(rec, m_dir, v_dir) -> bool:
    from cd_pair import read_bgr

    image = str(rec.get("image") or "")
    src = str(rec.get("json") or "")
    if not image or not src or not os.path.isfile(image) or not os.path.isfile(src):
        return False
    bgr = read_bgr(image)
    data = load_json(src, default={}) or {}
    shapes = data.get("shapes") if isinstance(data.get("shapes"), list) else []
    items = rec.get("items") or []
    stem = str(rec.get("stem") or "")
    if items and items[0].get("index") is None:
        m_path = os.path.join(m_dir, model_name_for(stem, None))
        write_qwen_view(draw_shapes(bgr, shapes), path=m_path)
        items[0]["model"] = m_path
    else:
        for item in items:
            idx = item.get("index")
            if not isinstance(idx, int) or idx < 0 or idx >= len(shapes):
                continue
            label = shapes[idx].get("label")
            drawn = instance_crop_view(
                bgr, shapes[idx], PALETTE[idx % len(PALETTE)],
                fill=not needs_true_color(label),
            )
            m_path = os.path.join(m_dir, model_name_for(stem, idx))
            write_qwen_view(drawn, path=m_path)
            item["model"] = m_path
    rec["vis"] = os.path.join(v_dir, f"{stem}.jpg")
    save_jpg(rec["vis"], paint_det_overview(bgr, shapes, items))
    return True


def paint_saved_change(rec, m_dir, v_dir) -> bool:
    from cd_pair import locate_pair_file, mask_components, pair_mask_view, read_bgr, read_mask

    dataset_root = str(Path(m_dir).parents[2]) if m_dir else ""
    before_p = locate_pair_file(rec.get("before") or "", dataset_root)
    after_p = locate_pair_file(rec.get("image") or "", dataset_root)
    mask_p = str(rec.get("mask") or "")
    if not before_p or not after_p or not mask_p:
        return False
    before = read_bgr(before_p)
    after = read_bgr(after_p)
    comps = mask_components(read_mask(mask_p))
    items = rec.get("items") or []
    stem = str(rec.get("stem") or "")
    paired = list(zip(comps, items))
    for comp, item in paired:
        idx = item.get("index")
        drawn = pair_mask_view(before, after, comp, PALETTE[int(idx or 0) % len(PALETTE)])
        m_path = os.path.join(m_dir, model_name_for(stem, idx))
        write_qwen_view(drawn, path=m_path)
        item["model"] = m_path
        item["vis"] = save_change_item_view(before, after, comp, item, stem, v_dir)
    for item in items[len(paired):]:
        item["view_skip"] = True
    rec["vis"] = save_change_overview(before, after, comps, items, stem, v_dir)
    return True


ISSUE_ZH = {"oversize": "过大", "incomplete": "不完整", "shifted": "错位"}
GRADE_RANK = {"wrong": 0, "adjust": 1, "fit": 2}


def to_check_dir(dataset_root: str, dest="") -> str:
    return dest or os.path.join(dataset_root, "draft", "to_check")


def label_dirname(label) -> str:
    text = str(label or "").strip() or "unknown"
    for ch in '\\/:*?"<>|':
        text = text.replace(ch, "_")
    text = text.rstrip(". ")
    return text or "unknown"


def export_to_check(dataset_root, slug, part=None, jsons_dir="", dest="") -> dict:
    """待查图：检测抄裁图；变化检测抄 crop。CD 另抄 fit。变化检测 dest 在版本目录，不写 draft。"""
    slug = use_slug(slug)
    if slug != TASK_SLUG:
        return {}
    folder = jsons_dir or qa_jsons_dir(dataset_root, slug, part)
    grades = ("wrong", "adjust", "fit")
    by_label = {}
    copy_fit = False
    if os.path.isdir(folder):
        for path in sorted(Path(folder).glob("*.json")):
            rec = load_json(str(path))
            if not isinstance(rec, dict) or rec.get("source") in {"failed", "placeholder"}:
                continue
            pair = bool(rec.get("pair"))
            if pair:
                copy_fit = True
            stem = str(rec.get("stem") or path.stem)
            for item in rec.get("items") or []:
                if item.get("source") == "failed" or item.get("view_skip"):
                    continue
                label = label_dirname(item.get("label"))
                bucket = by_label.setdefault(label, {g: [] for g in grades})
                grade = item_grade(item)
                if grade not in grades:
                    continue
                if grade == "fit" and not pair:
                    continue
                if pair:
                    src = str(item.get("model") or item.get("vis") or "")
                    name = os.path.basename(src) if src else crop_name_for(stem, item.get("index") or 0)
                else:
                    src = str(item.get("model") or "")
                    name = os.path.basename(src) if src else ""
                if src and os.path.isfile(src) and name:
                    bucket[grade].append((src, name))
    root = to_check_dir(dataset_root, dest)
    n_wrong = n_adjust = n_fit = 0
    for label, bucket in by_label.items():
        for grade in grades:
            dst_dir = os.path.join(root, label, grade)
            if os.path.isdir(dst_dir):
                for old in Path(dst_dir).iterdir():
                    if old.is_file():
                        old.unlink()
            srcs = bucket[grade]
            if grade == "fit" and not copy_fit:
                srcs = []
            if not srcs:
                if os.path.isdir(dst_dir) and not any(Path(dst_dir).iterdir()):
                    os.rmdir(dst_dir)
                continue
            ensure_dir(dst_dir)
            for src, name in srcs:
                shutil.copy2(src, os.path.join(dst_dir, name))
            if grade == "wrong":
                n_wrong += len(srcs)
            elif grade == "adjust":
                n_adjust += len(srcs)
            else:
                n_fit += len(srcs)
        label_dir = os.path.join(root, label)
        if os.path.isdir(label_dir) and not any(Path(label_dir).iterdir()):
            os.rmdir(label_dir)
    return {"dir": root, "wrong": n_wrong, "adjust": n_adjust, "fit": n_fit}


def md_cell(text) -> str:
    return " ".join(str(text or "").split()).replace("|", "\\|")


def md_file_link(path: str) -> str:
    raw = str(path or "").strip()
    if not raw:
        return ""
    name = os.path.basename(raw)
    href = Path(raw).as_posix()
    return f"[{name}]({href})"


def write_vis_summary(dataset_root, slug, part=None) -> str:
    folder = qa_jsons_dir(dataset_root, slug, part)
    v_dir = vis_dir(dataset_root, slug, part)
    m_dir = model_dir(dataset_root, slug, part)
    ensure_dir(v_dir)
    rows = []
    if os.path.isdir(folder):
        for path in sorted(Path(folder).glob("*.json")):
            rec = load_json(str(path))
            if isinstance(rec, dict):
                rows.append(rec)
    title = use_slug(slug) if not part else f"{use_slug(slug)}/{part}"
    detail = []
    n_fit = n_adjust = n_wrong = 0
    for rec in rows:
        stem = str(rec.get("stem") or "")
        vis = str(rec.get("vis") or os.path.join(v_dir, f"{stem}.jpg"))
        items = rec.get("items") or []
        if not items:
            detail.append((9, stem, None, stem, "", "", "", rec.get("error") or rec.get("source") or "", "", vis))
            continue
        for item in items:
            grade = item_grade(item)
            if grade == "fit":
                n_fit += 1
            elif grade == "adjust":
                n_adjust += 1
            elif grade == "wrong":
                n_wrong += 1
            issue = ISSUE_ZH.get(str(item.get("issue") or ""), "")
            detail.append((
                GRADE_RANK.get(grade, 9),
                stem,
                item.get("index"),
                stem,
                item.get("label") or "",
                grade,
                issue,
                item.get("reason") or "",
                item.get("model") or "",
                vis,
            ))
    detail.sort(key=lambda row: (row[0], row[1], row[2] is None, row[2] if isinstance(row[2], int) else -1))
    lines = [
        f"# {title}",
        "",
        f"- 整图：`{v_dir}`（绿贴合，橙要改，红误检）",
        f"- 裁图：`{m_dir}`",
        f"- 判定：`{folder}`",
        f"- 合计：fit {n_fit}，adjust {n_adjust}，wrong {n_wrong}",
    ]
    if use_slug(slug) == TASK_SLUG:
        lines.append(
            f"- 待查：`{to_check_dir(dataset_root)}`"
            "（`<类别>/wrong` 误检，`<类别>/adjust` 要改；变化检测另有 `<类别>/fit`）"
        )
    lines.extend([
        "",
        "误检和要改排在前面。",
        "",
        "| 图 | 序号 | 类别 | 档位 | 问题 | 理由 | 裁图 | 整图 |",
        "| --- | ---: | --- | --- | --- | --- | --- | --- |",
    ])
    for row in detail:
        idx = "" if row[2] is None else str(row[2])
        lines.append(
            "| {stem} | {idx} | {label} | {grade} | {issue} | {reason} | {crop} | {vis} |".format(
                stem=md_cell(row[3]),
                idx=idx,
                label=md_cell(row[4]),
                grade=md_cell(row[5]),
                issue=md_cell(row[6]),
                reason=md_cell(row[7]) or "—",
                crop=md_file_link(row[8]),
                vis=md_file_link(row[9]),
            )
        )
    lines.append("")
    out = os.path.join(v_dir, "summary.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return out


def ensure_views(dataset_root, slug=None, part=None) -> str:
    """已有判定但缺图时补 model/ 与 vis/，不重问模型。"""
    slug = use_slug(slug)
    part = str(part or "").strip() or None
    folder = qa_jsons_dir(dataset_root, slug, part)
    if not os.path.isdir(folder):
        return ""
    m_dir = model_dir(dataset_root, slug, part)
    v_dir = vis_dir(dataset_root, slug, part)
    ensure_dir(m_dir)
    ensure_dir(v_dir)
    for path in sorted(Path(folder).glob("*.json")):
        rec = load_json(str(path))
        if not isinstance(rec, dict) or rec.get("source") in {"failed", "placeholder"}:
            continue
        need_paint, dirty = _bind_view_paths(rec, m_dir, v_dir)
        if need_paint:
            try:
                ok = paint_saved_change(rec, m_dir, v_dir) if rec.get("pair") else paint_saved_det(rec, m_dir, v_dir)
            except Exception as e:
                print(f"视图跳过 {path.stem}: {e}")
                continue
            dirty = ok or dirty
        if dirty:
            write_json(str(path), rec)
    checked = export_to_check(dataset_root, slug, part)
    table = write_vis_summary(dataset_root, slug, part)
    if checked:
        print(
            f"to_check wrong={checked['wrong']} adjust={checked['adjust']} "
            f"fit={checked.get('fit', 0)} → {checked['dir']}"
        )
    return table


def _list_stem_crops(crop_dir: str, stem: str):
    """按 stem_01.jpg 序号列出已有裁图，返回 (0-based index, path)。"""
    if not crop_dir or not os.path.isdir(crop_dir):
        return []
    pat = re.compile(rf"^{re.escape(stem)}_(\d+)\.(?:jpg|jpeg|png)$", re.I)
    found = []
    for name in os.listdir(crop_dir):
        m = pat.match(name)
        if not m:
            continue
        found.append((int(m.group(1)) - 1, os.path.join(crop_dir, name)))
    found.sort(key=lambda x: x[0])
    return found


def run_change(dataset_root, masks="label", limit=None, force=False, workers=2,
               timeout=600, base_url="", model="", slug=None, min_area=32, part=None,
               prompt="", prompt_file=""):
    """两期 A/B 上核对 png 变化掩膜。不改原图和掩膜。

    小于 min_area 的碎斑不送模型，也不写入档位，不参与整对去留。
    `--masks` 落在 `repro/<版本>/bcd_map` 时：窗以 `crop/vismask_crop/` 为准，
    Qwen 看同名 `crop/analysis_crop/`（不叠 GT）；缺 analysis 跳过、不补写。
    判定写 `analysis/jsons/`，不再写 draft/model、vis、summary.json。
    """
    from cd_pair import (
        resolve_grade_prompt,
        list_pairs,
        mask_components,
        pair_mask_view,
        pair_roots,
        read_bgr,
        read_mask,
    )
    grade_prompt = resolve_grade_prompt(prompt, prompt_file)

    slug = use_slug(slug)
    part = str(part or "").strip() or None
    before_dir, after_dir = pair_roots(dataset_root)
    if not before_dir:
        raise SystemExit(f"变化检测需要对齐的 A/ 与 B/: {dataset_root}")
    mask_dir = resolve_jsons_dir(dataset_root, masks)
    if not os.path.isdir(mask_dir):
        raise SystemExit(f"找不到掩膜目录: {mask_dir}")
    layout = cd_layout(mask_dir, dataset_root)
    jsons_dir = layout["jsons"] if layout else qa_jsons_dir(dataset_root, slug, part)
    crop_dir = layout["crop"] if layout else model_dir(dataset_root, slug, part)
    vismask_crop_dir = layout["vismask_crop"] if layout else ""
    use_repro = bool(layout)
    pairs = {stem: (before, after) for stem, before, after in list_pairs(before_dir, after_dir)}
    files = sorted(
        p for p in Path(mask_dir).iterdir()
        if p.is_file() and p.suffix.lower() in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}
    )
    if limit:
        files = files[: int(limit)]
    ensure_dir(jsons_dir)
    ensure_dir(crop_dir)
    if not use_repro:
        ensure_dir(vis_dir(dataset_root, slug, part))

    pending = []
    skipped = 0
    for path in files:
        out_p = os.path.join(jsons_dir, f"{path.stem}.json")
        existing = load_json(out_p) if os.path.isfile(out_p) else None
        if not force and existing and existing.get("source") not in {"failed", "placeholder"}:
            skipped += 1
            continue
        pending.append((path, out_p))
    if not pending:
        table = "" if use_repro else ensure_views(dataset_root, slug, part)
        print(f"变化掩膜无需质检 skip={skipped}")
        if table:
            print(f"表格 {table}")
        return {"skip": skipped, "n": 0, "fit": 0, "ok": 0, "wrong": 0, "adjust": 0}

    client, model_name = _make_client(base_url, model, timeout)
    print(
        f"change-qa jobs={len(pending)} skip={skipped} masks={len(files)} "
        f"model={model_name} → {jsons_dir}"
    )

    def one(item):
        path, out_p = item
        stem = path.stem
        pair = pairs.get(stem)
        if not pair:
            rec = {
                "stem": stem, "source": "failed", "error": "A/B 没有同名图",
                "n": 0, "fit": 0, "ok": 0, "wrong": 0, "adjust": 0, "items": [], "pair": True,
            }
            write_json(out_p, rec)
            return rec
        try:
            before = read_bgr(pair[0])
            after = read_bgr(pair[1])
            mask = read_mask(str(path))
            if before.shape[:2] != after.shape[:2] or before.shape[:2] != mask.shape[:2]:
                raise ValueError("A/B/掩膜尺寸不一致")
        except Exception as e:
            rec = {
                "stem": stem, "source": "failed", "error": str(e),
                "n": 0, "fit": 0, "ok": 0, "wrong": 0, "adjust": 0, "items": [], "pair": True,
            }
            write_json(out_p, rec)
            return rec
        items = []
        if use_repro:
            # 窗名单跟 vismask_crop；识图用同名 analysis_crop（无 GT）
            comps = mask_components(mask, min_area=1219)
            area_by_i = {i: int(c["area"]) for i, c in enumerate(comps)}
            window_dir = vismask_crop_dir if (
                vismask_crop_dir and os.path.isdir(vismask_crop_dir)
            ) else crop_dir
            for i, vis_path in _list_stem_crops(window_dir, stem):
                name = os.path.basename(vis_path)
                m_path = os.path.join(crop_dir, name)
                if not os.path.isfile(m_path):
                    continue
                try:
                    verdict = normalize_grade(
                        ask_overlay(client, None, grade_prompt, model_path=m_path),
                    )
                except Exception as e:
                    verdict = failed_grade(str(e))
                    m_path = ""
                items.append({
                    "index": i,
                    "label": "change",
                    "shape_type": "mask",
                    "model": m_path,
                    "area": int(area_by_i.get(i, 0)),
                    **verdict,
                })
        else:
            comps = mask_components(mask, min_area=min_area)
            for i, comp in enumerate(comps):
                color = PALETTE[i % len(PALETTE)]
                m_path = os.path.join(crop_dir, model_name_for(stem, i))
                try:
                    drawn = pair_mask_view(before, after, comp, color)
                    verdict = normalize_grade(
                        ask_overlay(client, drawn, grade_prompt, model_path=m_path),
                    )
                except Exception as e:
                    verdict = failed_grade(str(e))
                    m_path = ""
                items.append({
                    "index": i,
                    "label": "change",
                    "shape_type": "mask",
                    "model": m_path,
                    "area": int(comp["area"]),
                    **verdict,
                })
        v_path = ""
        if not use_repro:
            v_dir = vis_dir(dataset_root, slug, part)
            v_path = save_change_overview(before, after, comps, items, stem, v_dir)
            for comp, item in zip(comps, items):
                item["vis"] = save_change_item_view(before, after, comp, item, stem, v_dir)
        counts = count_grades(items)
        rec = {
            "stem": stem,
            "image": pair[1],
            "before": pair[0],
            "mask": str(path),
            "pair": True,
            "source": "empty" if not items else "vllm",
            "error": None,
            "n": len(items),
            **counts,
            "vis": v_path,
            "items": items,
        }
        write_json(out_p, rec)
        return rec

    stats = {"fit": 0, "ok": 0, "wrong": 0, "adjust": 0, "n": 0, "images": 0, "fail": 0, "empty": 0}
    with ThreadPoolExecutor(max_workers=max(1, int(workers))) as pool:
        futs = [pool.submit(one, item) for item in pending]
        for fut in tqdm(as_completed(futs), total=len(futs), desc="change-qa"):
            rec = fut.result()
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
    table = "" if use_repro else ensure_views(dataset_root, slug, part)
    summary = {
        **stats, "skip": skipped, "masks": mask_dir, "model": model_name,
        "crop": crop_dir if use_repro else model_dir(dataset_root, slug, part),
        "jsons": jsons_dir,
        "slug": slug, "part": part or "", "pair": True,
    }
    if not use_repro:
        summary["model_dir"] = model_dir(dataset_root, slug, part)
        summary["vis_dir"] = vis_dir(dataset_root, slug, part)
        write_json(summary_path(dataset_root, slug, part), summary)
    elif slug == TASK_SLUG:
        export_to_check(
            dataset_root, slug, part,
            jsons_dir=jsons_dir, dest=layout["to_check"],
        )
    print(
        f"change-qa 完成 n={stats['n']} fit={stats['fit']} adjust={stats['adjust']} "
        f"wrong={stats['wrong']} ok={stats['ok']} images={stats['images']}"
    )
    if table:
        print(f"表格 {table}")
    return summary


def parse_args():
    p = argparse.ArgumentParser(description="逐框逐掩膜定档：fit|adjust|wrong。--masks 走变化检测")
    p.add_argument("--dataset", required=True)
    p.add_argument("--jsons", default="jsons-det-pre-car")
    p.add_argument("--masks", default="", help="变化掩膜目录（png，与 A/B 同名）。给出后走两期定档")
    p.add_argument("--mode", choices=("instance", "image"), default="instance")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--force", action="store_true")
    p.add_argument("--workers", type=int, default=2)
    p.add_argument("--timeout", type=int, default=600)
    p.add_argument("--base_url", default="")
    p.add_argument("--model", default="")
    p.add_argument("--prompt", default="", help="变化检测定档：本单要判的变化。空则用通用真实变化")
    p.add_argument("--prompt-file", default="", dest="prompt_file")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    if args.masks:
        run_change(
            args.dataset,
            masks=args.masks,
            limit=args.limit,
            force=args.force,
            workers=args.workers,
            timeout=args.timeout,
            base_url=args.base_url,
            model=args.model,
            prompt=args.prompt,
            prompt_file=args.prompt_file,
        )
    else:
        run_dataset(
            args.dataset,
            jsons=args.jsons,
            mode=args.mode,
            limit=args.limit,
            force=args.force,
            workers=args.workers,
            timeout=args.timeout,
            base_url=args.base_url,
            model=args.model,
        )
