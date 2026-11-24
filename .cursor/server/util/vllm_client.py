"""
# @Author: Yullin
# @Date: 2026-08-31
# @Description: 本地 / 远程 vLLM OpenAI 兼容客户端（各任务包共用）
"""

import base64
import json
import mimetypes
import threading
from typing import Optional
from urllib import error, request

_CALL_GATE = threading.Semaphore(6)

DEFAULT_BASE = "http://127.0.0.1:8081/v1"
DEFAULT_MODEL = "qwen3.6-35b-a3b"


def _ensure_no_think(prompt: str) -> str:
    text = str(prompt or "").strip()
    head = text[:24].lower().replace(" ", "")
    if head.startswith("/no_think") or head.startswith("/nothink"):
        return text
    return "/no_think\n" + text


def _guess_mime(path: str) -> str:
    mime, _ = mimetypes.guess_type(path)
    return mime or "image/jpeg"


def encode_image_data_url(path: str) -> str:
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    return f"data:{_guess_mime(path)};base64,{b64}"


class VLLMClient:
    def __init__(self, base_url=DEFAULT_BASE, model=DEFAULT_MODEL, timeout=600,
                 enable_thinking=False):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.enable_thinking = enable_thinking

    def health_check(self):
        url = f"{self.base_url}/models"
        try:
            req = request.Request(url, method="GET")
            with request.urlopen(req, timeout=10) as resp:
                return resp.status == 200
        except Exception:
            return False

    def chat(self, messages, max_tokens=1024, temperature=0.7):
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "enable_thinking": self.enable_thinking,
            "chat_template_kwargs": {
                "enable_thinking": self.enable_thinking,
                "thinking": self.enable_thinking,
            },
        }
        if not self.enable_thinking:
            payload["reasoning_effort"] = "none"
        data = json.dumps(payload).encode("utf-8")
        req = request.Request(
            url, data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with _CALL_GATE:
                with request.urlopen(req, timeout=self.timeout) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
        except error.URLError as e:
            raise RuntimeError(f"vLLM 请求失败 ({url}): {e}") from e
        msg = body["choices"][0]["message"]
        content = msg.get("content")
        if content is None or (isinstance(content, str) and not content.strip()):
            for key in ("reasoning_content", "reasoning"):
                alt = msg.get(key)
                if isinstance(alt, str) and "{" in alt:
                    content = alt
                    break
        if content is None or (isinstance(content, str) and not str(content).strip()):
            raise RuntimeError(
                "vLLM 返回空 content（若开启了 thinking，请关闭 enable_thinking）"
            )
        if not isinstance(content, str):
            content = str(content)
        return content

    def describe_images(self, image_paths, prompt: str, system: Optional[str] = None,
                        max_tokens=1024, temperature=0.7):
        paths = [p for p in (image_paths or []) if p]
        if not paths:
            raise ValueError("未提供图像")
        text = str(prompt or "")
        if not self.enable_thinking:
            text = _ensure_no_think(text)
        content = []
        for path in paths:
            content.append({
                "type": "image_url",
                "image_url": {"url": encode_image_data_url(path)},
            })
        content.append({"type": "text", "text": text})
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": content})
        return self.chat(messages, max_tokens=max_tokens, temperature=temperature)

    def describe_image(self, image_path: str, prompt: str, system: Optional[str] = None,
                       max_tokens=256, temperature=0.7):
        return self.describe_images(
            [image_path], prompt, system=system,
            max_tokens=max_tokens, temperature=temperature,
        )

    def text(self, prompt: str, system: Optional[str] = None, temperature=0.7,
             max_tokens=1024):
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": _ensure_no_think(prompt) if not self.enable_thinking else prompt})
        return self.chat(messages, max_tokens=max_tokens, temperature=temperature)


def extract_json_object(text: str):
    """Best-effort parse JSON object from model output."""
    if text is None:
        raise ValueError("模型输出为空 (None)")
    text = str(text).strip()
    if not text:
        raise ValueError("模型输出为空字符串")
    for tag in ("</think>", "</reasoning>"):
        if tag in text:
            text = text.split(tag)[-1].strip()
    if text.startswith("```"):
        lines = text.splitlines()
        lines = [ln for ln in lines if not ln.strip().startswith("```")]
        text = "\n".join(lines).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass
    raise ValueError(f"无法解析 JSON: {text[:200]}")
