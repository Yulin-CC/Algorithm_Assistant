"""
# @Author: Yullin
# @Date: 2026-09-11
# @Description: 本机 CPU/内存/磁盘/GPU/进程/uptime
# @Command: python util/system.py
# @Command: python util/system.py gpu
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

_UTIL = Path(__file__).resolve().parent
if str(_UTIL) not in sys.path:
    sys.path.insert(0, str(_UTIL))

from paths import safe_path


def _gib(n: int) -> str:
    return f"{n / 1024 ** 3:.1f} GiB"


def _mem_linux() -> tuple[int, int]:
    mem: dict[str, int] = {}
    with open("/proc/meminfo", encoding="utf-8") as f:
        for line in f:
            key, value = line.split(":", 1)
            mem[key] = int(value.strip().split()[0])
    total = mem.get("MemTotal", 0) * 1024
    avail = mem.get("MemAvailable", 0) * 1024
    return total, avail


def _mem_windows() -> tuple[int, int]:
    import ctypes

    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    status = MEMORYSTATUSEX()
    status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        raise OSError("GlobalMemoryStatusEx 失败")
    return int(status.ullTotalPhys), int(status.ullAvailPhys)


def system_overview() -> str:
    cpu_count = os.cpu_count() or 1
    load_line = "负载: 本平台无 getloadavg"
    if hasattr(os, "getloadavg"):
        load1, load5, load15 = os.getloadavg()
        load_line = f"负载 (1/5/15 分钟): {load1:.2f} / {load5:.2f} / {load15:.2f}"
    try:
        total, avail = _mem_linux() if Path("/proc/meminfo").exists() else _mem_windows()
    except OSError as e:
        return f"内存查询失败: {e}"
    used = total - avail
    return (
        f"CPU 核心数: {cpu_count}\n"
        f"{load_line}\n"
        f"内存: 已用 {_gib(used)} / 总计 {_gib(total)}（可用 {_gib(avail)}）"
    )


def _run(cmd: list[str], timeout: int = 15) -> subprocess.CompletedProcess[str]:
    enc = "utf-8"
    if os.name == "nt":
        import locale

        enc = locale.getpreferredencoding(False) or "gbk"
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding=enc,
        errors="replace",
        timeout=timeout,
        check=True,
    )


def gpu_status() -> str:
    cmd = [
        "nvidia-smi",
        "--query-gpu=index,name,memory.used,memory.total,utilization.gpu,temperature.gpu",
        "--format=csv,noheader",
    ]
    try:
        result = _run(cmd, timeout=10)
    except FileNotFoundError:
        return "未找到 nvidia-smi。"
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        return f"GPU 查询失败: {e}"
    lines = []
    for row in result.stdout.strip().splitlines():
        parts = [p.strip() for p in row.split(",")]
        if len(parts) < 6:
            continue
        idx, name, used, total, util, temp = parts[:6]
        lines.append(f"GPU {idx} | {name} | 显存 {used}/{total} | 利用率 {util} | {temp}°C")
    return "\n".join(lines) if lines else "未检测到 GPU。"


def top_processes(limit: int = 8) -> str:
    limit = max(1, min(int(limit), 20))
    if os.name == "nt":
        cmd = [
            "powershell",
            "-NoProfile",
            "-Command",
            (
                "Get-Process | Sort-Object CPU -Descending | "
                f"Select-Object -First {limit} Id,CPU,WorkingSet,ProcessName | "
                "Format-Table -AutoSize | Out-String -Width 200"
            ),
        ]
    else:
        cmd = ["ps", "-eo", "pid,user,%cpu,%mem,stat,cmd", "--sort=-%cpu"]
    try:
        result = _run(cmd, timeout=15)
    except FileNotFoundError:
        return "未找到进程查询命令。"
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        return f"进程查询失败: {e}"
    text = (result.stdout or "").strip()
    if not text:
        return "未查询到进程。"
    if os.name != "nt":
        rows = text.splitlines()
        return "\n".join(rows[: limit + 1])
    return text


def disk_space(path: str = "") -> str:
    raw = path.strip() if path else ("C:/" if os.name == "nt" else "/")
    try:
        target = safe_path(raw) if path.strip() else Path(raw)
        if not target.exists():
            return f"路径不存在: {target}"
        usage = shutil.disk_usage(target)
    except (OSError, ValueError) as e:
        return f"磁盘查询失败: {e}"
    used = usage.total - usage.free
    pct = used / usage.total * 100 if usage.total else 0
    return (
        f"路径: {target}\n"
        f"总容量: {_gib(usage.total)}\n"
        f"已用:   {_gib(used)} ({pct:.1f}%)\n"
        f"可用:   {_gib(usage.free)}"
    )


def server_uptime() -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    uptime_sec: float | None = None
    proc = Path("/proc/uptime")
    if proc.exists():
        try:
            uptime_sec = float(proc.read_text(encoding="utf-8").split()[0])
        except OSError as e:
            return f"运行时长查询失败: {e}"
    elif os.name == "nt":
        try:
            import ctypes

            kernel32 = ctypes.windll.kernel32
            kernel32.GetTickCount64.restype = ctypes.c_uint64
            uptime_sec = kernel32.GetTickCount64() / 1000.0
        except OSError as e:
            return f"运行时长查询失败: {e}"
    if uptime_sec is None:
        return f"当前时间: {now}\n已运行: 未知"
    days, rem = divmod(int(uptime_sec), 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)
    return f"当前时间: {now}\n已运行: {days} 天 {hours} 小时 {minutes} 分钟"


class Tools:
    def system_overview(self) -> str:
        """查看本机 CPU、内存、负载。用户问机器状态、内存够不够时用。"""
        return system_overview()

    def gpu_status(self) -> str:
        """查看 GPU 显存、利用率、温度。"""
        return gpu_status()

    def top_processes(self, limit: int = 8) -> str:
        """列出占用较高的进程。limit 默认 8，最大 20。"""
        return top_processes(limit)

    def disk_space(self, path: str = "") -> str:
        """查看磁盘使用。path 为空则用系统盘根。"""
        return disk_space(path)

    def server_uptime(self) -> str:
        """查看当前时间与开机时长。"""
        return server_uptime()


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="本机状态")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("overview")
    sub.add_parser("gpu")
    p_top = sub.add_parser("top")
    p_top.add_argument("--limit", type=int, default=8)
    p_disk = sub.add_parser("disk")
    p_disk.add_argument("--path", default="")
    sub.add_parser("uptime")
    args = parser.parse_args(argv)
    cmd = args.cmd or "overview"
    try:
        if cmd == "overview":
            print(system_overview())
        elif cmd == "gpu":
            print(gpu_status())
        elif cmd == "top":
            print(top_processes(args.limit))
        elif cmd == "disk":
            print(disk_space(args.path))
        elif cmd == "uptime":
            print(server_uptime())
    except ValueError as e:
        print(e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(_main())
