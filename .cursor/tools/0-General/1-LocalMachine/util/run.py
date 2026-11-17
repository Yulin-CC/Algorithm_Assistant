"""
# @Author: Yullin
# @Date: 2026-09-11
# @Description: 在白名单路径内执行 .py / .sh（Windows 上 .sh 需 bash）
# @Command: python util/run.py <script> [--args "..."] [--timeout 60]
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

_UTIL = Path(__file__).resolve().parent
if str(_UTIL) not in sys.path:
    sys.path.insert(0, str(_UTIL))

from paths import safe_path

ALLOWED_SUFFIX = {".py", ".sh"}
MAX_OUTPUT = 12000


def run_script(path: str, args: str = "", timeout: int = 60) -> str:
    target = safe_path(path)
    if not target.is_file():
        return f"脚本不存在: {target}"
    suffix = target.suffix.lower()
    if suffix not in ALLOWED_SUFFIX:
        return f"不支持的类型: {suffix}，仅允许 {', '.join(sorted(ALLOWED_SUFFIX))}"
    timeout = max(5, min(int(timeout), 300))
    arg_list = args.split() if args.strip() else []
    if suffix == ".py":
        cmd = [sys.executable, str(target), *arg_list]
    else:
        bash = shutil.which("bash")
        if not bash:
            return "未找到 bash，无法执行 .sh"
        cmd = [bash, str(target), *arg_list]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(target.parent),
            check=False,
        )
    except subprocess.TimeoutExpired:
        return f"执行超时（{timeout}s）: {target}"
    out = (result.stdout or "") + (result.stderr or "")
    if len(out) > MAX_OUTPUT:
        out = out[:MAX_OUTPUT] + f"\n...（输出已截断，共超过 {MAX_OUTPUT} 字符）"
    status = "成功" if result.returncode == 0 else f"退出码 {result.returncode}"
    return f"执行{status}: {' '.join(cmd)}\n{'-' * 48}\n{out or '（无输出）'}"


class Tools:
    def run_script(self, path: str, args: str = "", timeout: int = 60) -> str:
        """在白名单路径内执行 .py / .sh。timeout 默认 60，最大 300。"""
        return run_script(path, args, timeout)


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="白名单内执行脚本")
    parser.add_argument("path")
    parser.add_argument("--args", default="")
    parser.add_argument("--timeout", type=int, default=60)
    ns = parser.parse_args(argv)
    try:
        print(run_script(ns.path, ns.args, ns.timeout))
    except ValueError as e:
        print(e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(_main())
