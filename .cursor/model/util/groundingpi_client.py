"""
# @Author: Yullin
# @Date: 2026-11-06
# @Description: GroundingPI OpenAI 兼容客户端；须 skip_special_tokens=false
# @Command: python groundingpi_client.py --image /path.jpg --classes car,truck
"""

from __future__ import annotations

import base64
import json
import mimetypes
import os
import re
import threading
from urllib import error, request

from servers_io import find_service, get_default_service

_CALL_GATE = threading.Semaphore(6)

REF_RE = re.compile(
    r"<\|object_ref_start\|>(.*?)<\|object_ref_end\|>\s*<\|box_start\|>(.*?)<\|box_end\|>",
    re.S,
)
COORD_RE = re.compile(r"<(\d{1,4})>")
SERVICE_KEY = "GroundingPI"


def encode_data_url(path: str) -> str:
    mime = mimetypes.guess_type(path)[0] or "image/jpeg"
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    return f"data:{mime};base64,{b64}"


def resolve_service(base_url: str = "", model: str = "", name: str = SERVICE_KEY) -> tuple[str, str]:
    url = (base_url or "").strip().rstrip("/")
    model_name = (model or "").strip()
    if url and model_name:
        return url, model_name
    svc = find_service(name) or {}
    if not svc and not name:
        svc = get_default_service() or {}
    url = url or str(svc.get("base_url") or "").strip().rstrip("/")
    model_name = model_name or str(svc.get("model") or "").strip()
    if not url or not model_name:
        raise RuntimeError(
            f"未指定 --base_url/--model，且 vllm_server.json 无 {name} 服务"
        )
    return url, model_name


def locate_prompt(classes) -> str:
    names = [str(c).strip() for c in (classes or []) if str(c).strip()]
    if not names:
        raise ValueError("类别为空")
    if len(names) == 1:
        body = names[0] + "."
    else:
        body = "</c>".join(names[:-1]) + "</c>" + names[-1] + "."
    return f"Locate all the instances that match the following categories: {body}"


def grid_to_xyxy(nums, w: int, h: int):
    if len(nums) != 4:
        return None
    x1, y1, x2, y2 = [int(v) for v in nums]

    def px(v, size):
        v = max(0, min(999, int(v)))
        return int(round(v / 999.0 * (size - 1)))

    xa, ya, xb, yb = px(x1, w), px(y1, h), px(x2, w), px(y2, h)
    if xa > xb:
        xa, xb = xb, xa
    if ya > yb:
        ya, yb = yb, ya
    if xb <= xa or yb <= ya:
        return None
    return [float(xa), float(ya), float(xb), float(yb)]


def parse_boxes(raw: str, w: int, h: int) -> list:
    out = []
    for m in REF_RE.finditer(raw or ""):
        label = (m.group(1) or "").strip()
        inner = (m.group(2) or "").strip()
        if not label or inner.lower() == "none":
            continue
        for g in [x.strip() for x in inner.split(",") if x.strip()]:
            nums = [int(x) for x in COORD_RE.findall(g)]
            if len(nums) < 4:
                continue
            xyxy = grid_to_xyxy(nums[:4], w, h)
            if xyxy is None:
                continue
            out.append({
                "label": label,
                "box": xyxy,
                "bbox_2d": [int(v) for v in nums[:4]],
            })
    return out


class GroundingPIClient:
    def __init__(self, base_url="", model="", timeout=600, service_name=SERVICE_KEY):
        url, model_name = resolve_service(base_url, model, name=service_name)
        self.base_url = url
        self.model = model_name
        self.timeout = timeout

    def health_check(self) -> bool:
        url = f"{self.base_url}/models"
        try:
            req = request.Request(url, method="GET")
            with request.urlopen(req, timeout=10) as resp:
                return 200 <= int(resp.status) < 300
        except Exception:
            return False

    def locate(self, image_path: str, classes, extra_text: str = "", max_tokens=8192) -> str:
        prompt = locate_prompt(classes)
        extra = str(extra_text or "").strip()
        if extra:
            prompt = prompt + "\n" + extra
        return self.chat_image(image_path, prompt, max_tokens=max_tokens)

    def chat_image(self, image_path: str, prompt: str, max_tokens=8192) -> str:
        if not os.path.isfile(image_path):
            raise FileNotFoundError(image_path)
        url = self.base_url.rstrip("/") + "/chat/completions"
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": encode_data_url(image_path)}},
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
            "max_tokens": int(max_tokens),
            "temperature": 0,
            "skip_special_tokens": False,
            "spaces_between_special_tokens": False,
            "enable_thinking": False,
            "chat_template_kwargs": {"enable_thinking": False, "thinking": False},
            "reasoning_effort": "none",
        }
        req = request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with _CALL_GATE:
                with request.urlopen(req, timeout=self.timeout) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
        except error.URLError as e:
            raise RuntimeError(f"GroundingPI 请求失败 ({url}): {e}") from e
        msg = (body.get("choices") or [{}])[0].get("message") or {}
        content = msg.get("content")
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError(f"空 content: {msg!r}")
        return content
