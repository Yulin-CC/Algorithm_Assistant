"""
# @Author: Yullin
# @Date: 2026-09-11
# @Description: 路径白名单。额外根目录：LOCALMACHINE_ROOTS（os.pathsep 分隔）
"""

from __future__ import annotations

import os
from pathlib import Path

_CANDIDATES = (
    Path.home(),
    Path(os.environ.get("TEMP") or os.environ.get("TMP") or "/tmp"),
    Path("/tmp"),
    Path("D:/0-data"),
    Path("D:/1-project"),
    Path("D:/4-docs"),
    Path("/path/to/home"),
    Path("/path/to/home"),
)


def allowed_roots() -> list[Path]:
    extra = [
        Path(p.strip()).expanduser()
        for p in os.environ.get("LOCALMACHINE_ROOTS", "").split(os.pathsep)
        if p.strip()
    ]
    roots: list[Path] = []
    seen: set[str] = set()
    for raw in (*extra, *_CANDIDATES):
        try:
            resolved = raw.resolve()
        except OSError:
            continue
        if not resolved.exists():
            continue
        key = str(resolved).casefold() if os.name == "nt" else str(resolved)
        if key in seen:
            continue
        seen.add(key)
        roots.append(resolved)
    return roots


def safe_path(raw: str) -> Path:
    if not raw or not str(raw).strip():
        raise ValueError("路径不能为空")
    path = Path(raw).expanduser().resolve()
    roots = allowed_roots()
    for root in roots:
        try:
            path.relative_to(root)
            return path
        except ValueError:
            continue
    shown = ", ".join(str(r) for r in roots) or "(无可用根目录)"
    raise ValueError(f"路径不在允许范围内: {path}\n允许: {shown}")


def is_subpath(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False
