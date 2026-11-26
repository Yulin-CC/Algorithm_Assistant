"""
多模态模型服务配置：server/config/vllm_server.json
"""

from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional
import socket
from urllib import request

MODEL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVERS_PATH = os.path.join(MODEL_ROOT, "config", "vllm_server.json")


def servers_config_path() -> str:
    return SERVERS_PATH


def load_servers_config() -> dict:
    path = SERVERS_PATH
    if not os.path.isfile(path):
        return {"services": []}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f) or {}
        if not isinstance(data, dict):
            return {"services": []}
        services = data.get("services") or []
        if not isinstance(services, list):
            services = []
        data["services"] = [_normalize_service(s) for s in services if isinstance(s, dict)]
        return data
    except Exception:
        return {"services": []}


def _normalize_service(s: dict) -> Dict[str, Any]:
    base = str(s.get("base_url") or "").strip().rstrip("/")
    port = s.get("port")
    if port is None and base:
        try:
            hostport = base.split("://", 1)[-1].split("/", 1)[0]
            if ":" in hostport:
                port = int(hostport.rsplit(":", 1)[-1])
        except Exception:
            port = None
    sid = str(s.get("id") or "").strip()
    name = str(s.get("name") or sid or base or "unnamed").strip()
    if not sid:
        sid = name.lower().replace(" ", "-")
    return {
        "id": sid,
        "name": name,
        "base_url": base,
        "port": port,
        "model": str(s.get("model") or "").strip(),
        "default": bool(s.get("default")),
    }


def list_services() -> List[Dict[str, Any]]:
    return list(load_servers_config().get("services") or [])


def get_service(service_id: str) -> Optional[Dict[str, Any]]:
    sid = (service_id or "").strip()
    for s in list_services():
        if s["id"] == sid:
            return s
    return None


def find_service(key: str) -> Optional[Dict[str, Any]]:
    """按 id、name、model 匹配一条服务。name/model 大小写不敏感，多条命中则返回 None。"""
    text = (key or "").strip()
    if not text:
        return None
    hit = get_service(text)
    if hit:
        return hit
    low = text.lower()
    services = list_services()
    for field in ("name", "model"):
        hits = [s for s in services if str(s.get(field) or "").strip().lower() == low]
        if len(hits) == 1:
            return hits[0]
        if len(hits) > 1:
            return None
    return None


def get_default_service() -> Optional[Dict[str, Any]]:
    services = list_services()
    for s in services:
        if s.get("default"):
            return s
    return services[0] if services else None


def probe_hostport(url: str, timeout: float = 2.5) -> bool:
    """TCP 探测 host:port（Triton SAM 等，不依赖 tritonclient）。"""
    text = (url or "").strip()
    if "://" in text:
        text = text.split("://", 1)[-1]
    text = text.split("/", 1)[0]
    if ":" not in text:
        return False
    host, port_s = text.rsplit(":", 1)
    try:
        port = int(port_s)
    except ValueError:
        return False
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


def probe_base_url(base_url: str, timeout: float = 2.5) -> bool:
    """轻量探测 OpenAI 兼容 /models。"""
    base = (base_url or "").strip().rstrip("/")
    if not base:
        return False
    url = f"{base}/models"
    try:
        req = request.Request(url, method="GET")
        with request.urlopen(req, timeout=timeout) as resp:
            return 200 <= int(resp.status) < 300
    except Exception:
        return False


def probe_services(timeout: float = 2.5) -> List[Dict[str, Any]]:
    """并行探测全部服务，返回带 ok 字段的列表。"""
    services = list_services()
    if not services:
        return []

    def _one(s: dict) -> dict:
        out = dict(s)
        out["ok"] = probe_base_url(s.get("base_url") or "", timeout=timeout)
        return out

    results: Dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=min(8, max(1, len(services)))) as ex:
        futs = {ex.submit(_one, s): s["id"] for s in services}
        for fut in as_completed(futs):
            sid = futs[fut]
            try:
                results[sid] = fut.result()
            except Exception:
                base = next((x for x in services if x["id"] == sid), {})
                results[sid] = {**base, "ok": False}
    return [results.get(s["id"], {**s, "ok": False}) for s in services]
