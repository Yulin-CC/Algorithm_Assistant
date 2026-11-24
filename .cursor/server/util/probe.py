"""
# @Author: Yullin
# @Date: 2026-09-11
# @Description: 探测 vLLM /models 与 SAM TCP 端口；不下模型
# @Command: python server/util/probe.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from servers_io import (
    find_service,
    get_default_service,
    probe_hostport,
    probe_services,
    servers_config_path,
)

MODEL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAM_CONFIG_PATH = os.path.join(MODEL_ROOT, "config", "sam.json")


def sam_url() -> str:
    if not os.path.isfile(SAM_CONFIG_PATH):
        return ""
    try:
        with open(SAM_CONFIG_PATH, encoding="utf-8") as f:
            data = json.load(f) or {}
        return str((data or {}).get("url") or "").strip()
    except Exception:
        return ""


def parse_args():
    p = argparse.ArgumentParser(description="探测 vLLM / SAM；不下模型")
    p.add_argument("--skip-sam", action="store_true", help="只测 vLLM（分类 / detect-groundingpi）")
    p.add_argument(
        "--service", default="",
        help="按 name/id/model 探测该条目（如 GroundingPI）；空则要求 default",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    print(f"vllm: {servers_config_path()}")
    rows = probe_services()
    if not rows:
        print("  (清单为空)")
    for s in rows:
        mark = "ok" if s.get("ok") else "FAIL"
        print(f"  [{mark}] id={s.get('id')} {s.get('name')} {s.get('base_url')} model={s.get('model')}")

    want = (args.service or "").strip()
    target = find_service(want) if want else get_default_service()
    target_ok = False
    label = "service" if want else "default"
    if want and not target:
        print(f"{label}: 找不到 {want!r}")
    elif target:
        hit = next((s for s in rows if s.get("id") == target.get("id")), None)
        target_ok = bool(hit and hit.get("ok"))
        print(f"{label}: {target.get('name')} → {'ok' if target_ok else 'FAIL'}")
    else:
        print("default: 无")

    sam_ok = True
    if args.skip_sam:
        print("sam: skipped")
    else:
        url = sam_url()
        sam_ok = bool(url) and probe_hostport(url)
        print(f"sam: {SAM_CONFIG_PATH}")
        print(f"  [{'ok' if sam_ok else 'FAIL'}] {url or '(无 url)'}")

    if target_ok and sam_ok:
        print("probe: PASS")
        return 0
    if not target_ok:
        others = [s for s in rows if s.get("ok") and s.get("id") != (target or {}).get("id")]
        if others:
            print("probe: 目标不通，下列可达（须用户确认后改用）：")
            for s in others:
                print(f"  id={s.get('id')} {s.get('name')} {s.get('base_url')}")
        else:
            print("probe: vLLM 全部不通")
    if not args.skip_sam and not sam_ok:
        print("probe: SAM 端口不通")
    print("probe: FAIL")
    return 1


if __name__ == "__main__":
    sys.exit(main())
