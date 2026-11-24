"""
# @Author: Yullin
# @Date: 2026-08-31
# @Description: Qwen 任务包共用：找图、draft、JSON 读写
"""

import json
import os
import threading
import time
from pathlib import Path


IMG_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}
IMAGES_CANDIDATES = (
    "images", "image", "imgs", "img",
    "JPEGImages", "jpegimages", "JPG", "jpg", "PNG", "png",
)


def draft_dir(dataset_root: str) -> str:
    return os.path.join(dataset_root, "draft")


def task_draft(dataset_root: str, slug: str) -> str:
    return os.path.join(draft_dir(dataset_root), slug)


def task_cache(dataset_root: str, slug: str) -> str:
    return os.path.join(task_draft(dataset_root, slug), "cache")


def task_result(dataset_root: str, slug: str) -> str:
    return os.path.join(task_draft(dataset_root, slug), "result")


def task_model(dataset_root: str, slug: str) -> str:
    """发给模型看的图。"""
    return os.path.join(task_draft(dataset_root, slug), "model")


def task_vis(dataset_root: str, slug: str) -> str:
    """给人看的图和表。"""
    return os.path.join(task_draft(dataset_root, slug), "vis")


def ensure_dir(path: str) -> str:
    os.makedirs(path, exist_ok=True)
    return path


def dir_has_images(path: str, max_check: int = 400) -> bool:
    if not path or not os.path.isdir(path):
        return False
    try:
        n = 0
        with os.scandir(path) as it:
            for ent in it:
                if not ent.is_file(follow_symlinks=False):
                    continue
                n += 1
                if Path(ent.name).suffix.lower() in IMG_EXTS:
                    return True
                if n >= max_check:
                    return False
    except OSError:
        return False
    return False


def resolve_images_dir(dataset_root: str, images_dirname: str = "images") -> str:
    """解析图像目录：指定名 → 常见子目录 → 根目录自身有图。"""
    root = os.path.realpath(dataset_root or "")
    raw = (images_dirname or "images").strip()
    if os.path.isabs(raw) and os.path.isdir(raw):
        return os.path.realpath(raw)
    cand = os.path.join(root, raw) if raw not in {".", ""} else root
    if os.path.isdir(cand) and dir_has_images(cand):
        return os.path.realpath(cand)
    for name in IMAGES_CANDIDATES:
        nested = os.path.join(root, name)
        if os.path.isdir(nested) and dir_has_images(nested):
            return os.path.realpath(nested)
    if dir_has_images(root):
        return root
    return os.path.realpath(cand)


def list_image_files(img_dir: str) -> list:
    """返回图像绝对路径，按文件名排序。"""
    out = []
    if not img_dir or not os.path.isdir(img_dir):
        return out
    try:
        with os.scandir(img_dir) as it:
            for ent in it:
                if not ent.is_file(follow_symlinks=False):
                    continue
                if Path(ent.name).suffix.lower() in IMG_EXTS:
                    out.append(ent.path)
    except OSError:
        return []
    out.sort(key=lambda p: Path(p).name.lower())
    return out


def _win_file_busy(err):
    code = getattr(err, "winerror", None)
    if code in (5, 32):
        return True
    return isinstance(err, PermissionError)


def write_json(path, data):
    """原子写入。Windows 上目标文件被占用时 replace 会失败，需重试。"""
    ensure_dir(os.path.dirname(path) or ".")
    tmp = f"{path}.{os.getpid()}.{threading.get_ident()}.{time.time_ns()}.tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
        last_err = None
        for attempt in range(12):
            try:
                os.replace(tmp, path)
                return
            except OSError as e:
                if not _win_file_busy(e):
                    raise
                last_err = e
                time.sleep(0.03 * (attempt + 1))
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.flush()
        except OSError:
            if last_err:
                raise last_err
            raise
    finally:
        if os.path.isfile(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def load_json_first(paths, default=None, repair=True):
    """按顺序读第一个存在且能解析的 JSON。"""
    for path in paths or []:
        if not path:
            continue
        data = load_json(path, default=None, repair=repair)
        if data is not None:
            return data
    return default


def load_json(path, default=None, repair=True):
    if not path or not os.path.isfile(path):
        return default
    for attempt in range(8):
        try:
            with open(path, encoding="utf-8") as f:
                raw = f.read()
        except OSError:
            time.sleep(0.03 * (attempt + 1))
            continue
        text = (raw or "").lstrip("\ufeff").strip()
        if not text:
            time.sleep(0.03)
            continue
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            if "Extra data" in str(e):
                try:
                    obj, _end = json.JSONDecoder().raw_decode(text)
                except Exception:
                    obj = None
                if obj is not None:
                    if repair:
                        try:
                            write_json(path, obj)
                        except Exception:
                            pass
                    return obj
            time.sleep(0.03)
    return default
