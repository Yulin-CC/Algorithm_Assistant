"""
# @Author: Yullin
# @Date: 2026-09-11
# @Description: 能力 1 理解图像：把整图发给 vLLM，返回中文可见内容理解
# @Command: python util/describe.py --image /path/to.jpg
# @Command: python util/describe.py --image a.jpg --image b.jpg
# @Command: python util/describe.py --dataset /path/to/data

能力 2 误检定档见同目录 label_grade.py（框和掩膜都判 fit|adjust|wrong，不改写标注）。漏检定位是 label_miss.py。
能力 3 按理解改掩膜和框：暂不做。
"""

import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

_PKG_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
_REPO = os.path.normpath(os.path.join(_PKG_ROOT, "..", "..", ".."))
_MODEL_UTIL = os.path.join(_REPO, "model", "util")
if _MODEL_UTIL not in sys.path:
    sys.path.insert(0, _MODEL_UTIL)

from tqdm import tqdm

tqdm.monitor_interval = 0

from common import (
    ensure_dir,
    list_image_files,
    load_json,
    resolve_images_dir,
    task_model,
    task_result,
    write_json,
)
from servers_io import get_default_service
from vllm_client import VLLMClient

TASK_SLUG = "describe"

SYSTEM_PROMPT = (
    "你是图像描述助手。只写图中可见内容，不要编造看不清的文字或细节。"
    "不要使用 markdown，不要输出 JSON。"
)

DEFAULT_PROMPT = (
    "请用简洁中文描述这张图片：主体、场景、关键可见细节。"
    "2–6 句话即可。"
)


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


def is_placeholder_desc(desc) -> bool:
    if not desc:
        return True
    src = (desc.get("source") or "").lower()
    if src in {"failed", "placeholder"}:
        return True
    text = str(desc.get("description") or "").strip()
    return not text


def describe_image(client: VLLMClient, image_abs: str, prompt: str = "",
                   system: str = "", max_tokens: int = 768):
    task = (prompt or "").strip() or DEFAULT_PROMPT
    sys_p = (system or "").strip() or SYSTEM_PROMPT
    raw = client.describe_image(
        image_abs, task, system=sys_p, max_tokens=max_tokens,
    )
    text = str(raw or "").strip()
    if not text:
        raise ValueError("模型返回空描述")
    return {
        "description": text,
        "source": "vllm",
        "error": None,
    }


def describe_file(image_path, base_url="", model="", timeout=600, prompt="",
                  system="", max_tokens=768):
    rows = describe_files(
        [image_path], base_url=base_url, model=model, timeout=timeout,
        prompt=prompt, system=system, max_tokens=max_tokens,
    )
    return rows[0]


def describe_files(image_paths, base_url="", model="", timeout=600, prompt="",
                   system="", max_tokens=768):
    paths = []
    for raw in image_paths or []:
        p = os.path.abspath(str(raw))
        if not os.path.isfile(p):
            raise FileNotFoundError(f"图像不存在: {p}")
        paths.append(p)
    if not paths:
        raise ValueError("未提供图像")
    client, model_name = _make_client(base_url, model, timeout)
    out = []
    for p in paths:
        desc = describe_image(
            client, p, prompt=prompt, system=system, max_tokens=max_tokens,
        )
        desc["image"] = p
        desc["model"] = model_name
        out.append(desc)
    return out


def jsons_dir(dataset_root: str) -> str:
    return os.path.join(task_result(dataset_root, TASK_SLUG), "jsons")


def _desc_paths(dataset_root, stem: str):
    new_p = os.path.join(jsons_dir(dataset_root), f"{stem}.json")
    old_p = os.path.join(dataset_root, "draft", "descriptions", f"{stem}.json")
    return new_p, old_p


def _collect_jobs(dataset_root, img_dir, limit=None, force=False):
    files = list_image_files(img_dir)
    if limit:
        files = files[:limit]
    ensure_dir(jsons_dir(dataset_root))
    jobs = []
    for path in files:
        stem = Path(path).stem
        out_p, old_p = _desc_paths(dataset_root, stem)
        existing = load_json(out_p) if os.path.isfile(out_p) else None
        if existing is None and os.path.isfile(old_p):
            existing = load_json(old_p)
            if existing is not None and not is_placeholder_desc(existing) and not force:
                write_json(out_p, existing)
        if not force and existing is not None and not is_placeholder_desc(existing):
            continue
        jobs.append({
            "stem": stem,
            "image_abs": path,
            "image_rel": os.path.relpath(path, dataset_root),
            "out_p": out_p,
        })
    return jobs


def _run_job(client, job, prompt="", system="", max_tokens=768):
    try:
        image_abs = job["image_abs"]
        if job.get("pair"):
            from cd_pair import read_bgr, stitch, write_view
            view = stitch(read_bgr(job["before"]), read_bgr(job["after"]))
            image_abs = write_view(view, job["model_path"])
        desc = describe_image(
            client, image_abs, prompt=prompt, system=system,
            max_tokens=max_tokens,
        )
    except Exception as e:
        desc = {
            "description": "",
            "source": "failed",
            "error": str(e),
        }
    desc["stem"] = job["stem"]
    desc["image"] = job["image_rel"]
    if job.get("pair"):
        desc["pair"] = True
        desc["before"] = job["before"]
        desc["after"] = job["after"]
        desc["model"] = job.get("model_path") or ""
    write_json(job["out_p"], desc)
    return desc


def _collect_pair_jobs(dataset_root, pairs, limit=None, force=False):
    ensure_dir(jsons_dir(dataset_root))
    mdir = ensure_dir(task_model(dataset_root, TASK_SLUG))
    jobs = []
    chosen = pairs[: int(limit)] if limit else pairs
    for stem, before, after in chosen:
        out_p, _old = _desc_paths(dataset_root, stem)
        existing = load_json(out_p) if os.path.isfile(out_p) else None
        if not force and existing is not None and not is_placeholder_desc(existing):
            continue
        jobs.append({
            "stem": stem,
            "pair": True,
            "before": before,
            "after": after,
            "image_abs": before,
            "image_rel": os.path.relpath(before, dataset_root),
            "model_path": os.path.join(mdir, f"{stem}.jpg"),
            "out_p": out_p,
        })
    return jobs


def describe_dataset(dataset_root, base_url="", model="", limit=None, force=False,
                     workers=4, timeout=600, prompt="", images_dirname="images",
                     system="", max_tokens=768):
    from cd_pair import CD_DESCRIBE, list_pairs, pair_roots
    before_dir, after_dir = ("", "")
    if images_dirname == "images":
        before_dir, after_dir = pair_roots(dataset_root)
    if before_dir and after_dir:
        pairs = list_pairs(before_dir, after_dir)
        if not pairs:
            raise SystemExit(f"A/B 没有同名图像: {before_dir}")
        client, model_name = _make_client(base_url, model, timeout)
        jobs = _collect_pair_jobs(dataset_root, pairs, limit=limit, force=force)
        task = (prompt or "").strip() or CD_DESCRIBE
        print(
            f"待描述变化对: {len(jobs)} / 共 {len(pairs)} "
            f"（左前右后, workers={workers}, model={model_name}）"
        )
        if not jobs:
            print("无需描述（均已完成）")
            return
        n_fail = 0
        with ThreadPoolExecutor(max_workers=max(1, int(workers))) as pool:
            futs = [
                pool.submit(_run_job, client, job, task, system, max_tokens)
                for job in jobs
            ]
            for fut in tqdm(as_completed(futs), total=len(futs), desc="describe-cd"):
                desc = fut.result()
                if desc.get("source") == "failed":
                    n_fail += 1
        print(f"描述完成: {len(jobs)} 对 → {jsons_dir(dataset_root)}")
        if n_fail:
            print(f"⚠ 其中 {n_fail} 对失败（已写 failed 占位，可再次运行自动重试）")
        return

    img_dir = resolve_images_dir(dataset_root, images_dirname)
    files = list_image_files(img_dir)
    assert files, f"未找到图像: {img_dir}"

    client, model_name = _make_client(base_url, model, timeout)
    jobs = _collect_jobs(dataset_root, img_dir, limit=limit, force=force)
    print(
        f"待描述图像: {len(jobs)} / 共 {len(files)} "
        f"（workers={workers}, timeout={timeout}s, model={model_name}）"
    )

    if not jobs:
        print("无需描述（均已完成）")
        return

    n_fail = 0
    with ThreadPoolExecutor(max_workers=max(1, int(workers))) as pool:
        futs = [
            pool.submit(_run_job, client, job, prompt, system, max_tokens)
            for job in jobs
        ]
        for fut in tqdm(as_completed(futs), total=len(futs), desc="describe"):
            desc = fut.result()
            if desc.get("source") == "failed":
                n_fail += 1
    print(f"描述完成: {len(jobs)} 张 → {jsons_dir(dataset_root)}")
    if n_fail:
        print(f"⚠ 其中 {n_fail} 张失败（已写 failed 占位，可再次运行自动重试）")


def parse_args():
    p = argparse.ArgumentParser(description="识图并返回中文可见内容理解")
    p.add_argument(
        "--image", action="append", default=[],
        help="单张或多张图路径（可重复；与 --dataset 二选一）",
    )
    p.add_argument("--dataset", default="", help="数据集根目录（images/ 或根下直接放图）")
    p.add_argument("--images", default="images", help="图像子目录名，默认 images")
    p.add_argument("--prompt", default="", help="覆盖默认描述提示词")
    p.add_argument("--system", default="", help="覆盖默认系统提示")
    p.add_argument("--base_url", default="", help="空则读 model/config/vllm_server.json 的 default")
    p.add_argument("--model", default="", help="空则读 model/config/vllm_server.json 的 default")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--force", action="store_true")
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--timeout", type=int, default=600)
    p.add_argument("--max-tokens", type=int, default=768)
    p.add_argument("--json-out", default="", help="把 --image 结果写入该 JSON 文件")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    if args.image:
        if args.dataset:
            raise SystemExit("请只指定 --image 或 --dataset 之一")
        rows = describe_files(
            args.image,
            base_url=args.base_url, model=args.model,
            timeout=args.timeout, prompt=args.prompt, system=args.system,
            max_tokens=args.max_tokens,
        )
        payload = rows[0] if len(rows) == 1 else rows
        text = json.dumps(payload, ensure_ascii=False, indent=2)
        print(text)
        out_p = (args.json_out or "").strip()
        if out_p:
            Path(out_p).parent.mkdir(parents=True, exist_ok=True)
            Path(out_p).write_text(text + "\n", encoding="utf-8")
    elif args.dataset:
        describe_dataset(
            args.dataset, args.base_url, args.model,
            args.limit, args.force, workers=args.workers,
            timeout=args.timeout, prompt=args.prompt,
            images_dirname=args.images, system=args.system,
            max_tokens=args.max_tokens,
        )
    else:
        raise SystemExit("请指定 --image 或 --dataset")
