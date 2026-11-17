"""
# @Author: Yullin
# @Date: 2026-09-11
# @Description: 白名单路径内浏览与文件增删改、压缩解压
# @Command: python util/files.py ls <path>
"""

from __future__ import annotations

import argparse
import fnmatch
import shutil
import sys
import tarfile
import zipfile
from pathlib import Path

_UTIL = Path(__file__).resolve().parent
if str(_UTIL) not in sys.path:
    sys.path.insert(0, str(_UTIL))

from paths import is_subpath, safe_path


def _safe_extract(archive: Path, dest: Path) -> int:
    dest = dest.resolve()
    dest.mkdir(parents=True, exist_ok=True)
    name = archive.name.lower()
    count = 0

    if name.endswith(".zip"):
        with zipfile.ZipFile(archive) as zf:
            for info in zf.infolist():
                target = (dest / info.filename).resolve()
                if not is_subpath(target, dest) and target != dest:
                    raise ValueError(f"压缩包内含非法路径: {info.filename}")
                if info.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(zf.read(info))
                count += 1
        return count

    if name.endswith((".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tbz2")):
        with tarfile.open(archive) as tf:
            for member in tf.getmembers():
                if member.name.startswith("/") or ".." in Path(member.name).parts:
                    raise ValueError(f"压缩包内含非法路径: {member.name}")
                target = (dest / member.name).resolve()
                if not is_subpath(target, dest) and target != dest:
                    raise ValueError(f"压缩包内含非法路径: {member.name}")
                try:
                    tf.extract(member, dest, filter="data")
                except TypeError:
                    tf.extract(member, dest)
                count += 1
        return count

    shutil.unpack_archive(str(archive), str(dest))
    return len(list(dest.rglob("*")))


def list_directory(path: str = ".", show_hidden: bool = False) -> str:
    target = safe_path(path)
    if not target.is_dir():
        return f"不是目录: {target}"
    entries = sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    lines = [f"目录: {target}", "-" * 48]
    for item in entries:
        if not show_hidden and item.name.startswith("."):
            continue
        kind = "DIR " if item.is_dir() else "FILE"
        size = "" if item.is_dir() else f"  {item.stat().st_size:,} B"
        lines.append(f"{kind}  {item.name}{size}")
    if len(lines) == 2:
        lines.append("（空目录）")
    return "\n".join(lines)


def search_files(root: str, pattern: str = "*", keyword: str = "", max_results: int = 30) -> str:
    base = safe_path(root)
    if not base.is_dir():
        return f"不是目录: {base}"
    max_results = max(1, min(int(max_results), 100))
    hits: list[str] = []
    for item in base.rglob("*"):
        if len(hits) >= max_results:
            break
        if not item.is_file() or item.name.startswith("."):
            continue
        if not fnmatch.fnmatch(item.name, pattern):
            continue
        if keyword:
            try:
                text = item.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if keyword not in text:
                continue
        hits.append(str(item))
    if not hits:
        return f"未找到匹配: root={base}, pattern={pattern}, keyword={keyword or '(无)'}"
    return "\n".join([f"共 {len(hits)} 条（上限 {max_results}）:", *hits])


def read_file(path: str, max_chars: int = 8000) -> str:
    target = safe_path(path)
    if not target.is_file():
        return f"不是文件: {target}"
    max_chars = max(500, min(int(max_chars), 50000))
    try:
        text = target.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return f"读取失败: {e}"
    note = f"\n\n...（已截断，共 {len(text)} 字符）" if len(text) > max_chars else ""
    return f"文件: {target}\n{'-' * 48}\n{text[:max_chars]}{note}"


def create_file(path: str, content: str = "") -> str:
    target = safe_path(path)
    if target.exists():
        return f"文件已存在: {target}"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return f"已创建文件: {target}（{len(content)} 字符）"


def update_file(path: str, content: str) -> str:
    target = safe_path(path)
    if not target.exists():
        return f"文件不存在，请先 create_file: {target}"
    if not target.is_file():
        return f"不是文件: {target}"
    old_size = target.stat().st_size
    target.write_text(content, encoding="utf-8")
    return f"已更新文件: {target}\n原大小 {old_size:,} B → 新内容 {len(content)} 字符"


def replace_in_file(path: str, old_text: str, new_text: str, replace_all: bool = False) -> str:
    target = safe_path(path)
    if not target.is_file():
        return f"不是文件: {target}"
    if not old_text:
        return "old_text 不能为空"
    try:
        text = target.read_text(encoding="utf-8")
    except OSError as e:
        return f"读取失败: {e}"
    count = text.count(old_text)
    if count == 0:
        return f"未找到匹配内容: {target}"
    if replace_all:
        updated = text.replace(old_text, new_text)
        replaced = count
    else:
        updated = text.replace(old_text, new_text, 1)
        replaced = 1
    target.write_text(updated, encoding="utf-8")
    return f"已修改文件: {target}\n替换 {replaced} 处（共匹配 {count} 处）"


def append_to_file(path: str, content: str) -> str:
    target = safe_path(path)
    if not target.exists():
        return f"文件不存在，请先 create_file: {target}"
    if not target.is_file():
        return f"不是文件: {target}"
    with target.open("a", encoding="utf-8") as f:
        f.write(content)
    return f"已追加到文件: {target}（+{len(content)} 字符，现共 {target.stat().st_size:,} B）"


def create_directory(path: str) -> str:
    target = safe_path(path)
    if target.exists():
        if target.is_dir():
            return f"目录已存在: {target}"
        return f"同名文件已存在: {target}"
    target.mkdir(parents=True, exist_ok=True)
    return f"已创建目录: {target}"


def remove_path(path: str, force: bool = False) -> str:
    target = safe_path(path)
    if not target.exists():
        return f"路径不存在: {target}"
    if target.is_file() or target.is_symlink():
        target.unlink()
        return f"已删除文件: {target}"
    if not force:
        if any(target.iterdir()):
            return f"目录非空，请 force=True 再删除: {target}"
        target.rmdir()
        return f"已删除空目录: {target}"
    shutil.rmtree(target)
    return f"已递归删除目录: {target}"


def move_path(src: str, dst: str) -> str:
    source = safe_path(src)
    dest = safe_path(dst)
    if not source.exists():
        return f"源路径不存在: {source}"
    if dest.exists():
        return f"目标已存在: {dest}"
    if source.is_dir() and is_subpath(dest, source):
        return f"不能将目录移动到其子路径: {dest}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(dest))
    return f"已移动: {source} → {dest}"


def copy_path(src: str, dst: str) -> str:
    source = safe_path(src)
    dest = safe_path(dst)
    if not source.exists():
        return f"源路径不存在: {source}"
    if dest.exists():
        return f"目标已存在: {dest}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        shutil.copytree(source, dest)
    else:
        shutil.copy2(source, dest)
    return f"已复制: {source} → {dest}"


def compress_path(path: str, archive_path: str, fmt: str = "zip") -> str:
    source = safe_path(path)
    archive = safe_path(archive_path)
    if not source.exists():
        return f"源路径不存在: {source}"
    if archive.exists():
        return f"压缩包已存在: {archive}"
    archive.parent.mkdir(parents=True, exist_ok=True)
    fmt = fmt.lower().strip().replace(".", "")
    if fmt in ("targz", "tar.gz"):
        fmt = "gztar"
    if fmt == "zip":
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
            if source.is_file():
                zf.write(source, source.name)
            else:
                for item in source.rglob("*"):
                    if item.is_file():
                        zf.write(item, item.relative_to(source))
    elif fmt == "tar":
        with tarfile.open(archive, "w") as tf:
            tf.add(source, arcname=source.name)
    elif fmt == "gztar":
        with tarfile.open(archive, "w:gz") as tf:
            tf.add(source, arcname=source.name)
    else:
        return f"不支持的格式: {fmt}，可用 zip / tar / gztar"
    return f"已压缩: {source} → {archive}（{archive.stat().st_size:,} B）"


def extract_archive(archive_path: str, dest_dir: str) -> str:
    archive = safe_path(archive_path)
    dest = safe_path(dest_dir)
    if not archive.is_file():
        return f"不是文件: {archive}"
    try:
        count = _safe_extract(archive, dest)
    except (OSError, ValueError, tarfile.TarError, zipfile.BadZipFile) as e:
        return f"解压失败: {e}"
    return f"已解压: {archive} → {dest}（{count} 项）"


class Tools:
    def list_directory(self, path: str = ".", show_hidden: bool = False) -> str:
        """列出目录。"""
        return list_directory(path, show_hidden)

    def search_files(self, root: str, pattern: str = "*", keyword: str = "", max_results: int = 30) -> str:
        """按文件名通配符或内容关键词搜索。"""
        return search_files(root, pattern, keyword, max_results)

    def read_file(self, path: str, max_chars: int = 8000) -> str:
        """读取文本文件（过长截断）。"""
        return read_file(path, max_chars)

    def create_file(self, path: str, content: str = "") -> str:
        """新建文件；已存在则拒绝。"""
        return create_file(path, content)

    def update_file(self, path: str, content: str) -> str:
        """覆盖已有文件全文。"""
        return update_file(path, content)

    def replace_in_file(self, path: str, old_text: str, new_text: str, replace_all: bool = False) -> str:
        """精确替换一段文本。"""
        return replace_in_file(path, old_text, new_text, replace_all)

    def append_to_file(self, path: str, content: str) -> str:
        """文件末尾追加。"""
        return append_to_file(path, content)

    def create_directory(self, path: str) -> str:
        """创建目录（含父级）。"""
        return create_directory(path)

    def remove_path(self, path: str, force: bool = False) -> str:
        """删文件或空目录；force 可递归删目录。"""
        return remove_path(path, force)

    def move_path(self, src: str, dst: str) -> str:
        """移动或重命名。"""
        return move_path(src, dst)

    def copy_path(self, src: str, dst: str) -> str:
        """复制文件或目录。"""
        return copy_path(src, dst)

    def compress_path(self, path: str, archive_path: str, fmt: str = "zip") -> str:
        """压缩为 zip / tar / gztar。"""
        return compress_path(path, archive_path, fmt)

    def extract_archive(self, archive_path: str, dest_dir: str) -> str:
        """解压 zip / tar / tar.gz。"""
        return extract_archive(archive_path, dest_dir)


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="白名单内文件操作")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("ls")
    p.add_argument("path")
    p.add_argument("--hidden", action="store_true")

    p = sub.add_parser("search")
    p.add_argument("root")
    p.add_argument("--pattern", default="*")
    p.add_argument("--keyword", default="")
    p.add_argument("--max", type=int, default=30)

    p = sub.add_parser("read")
    p.add_argument("path")
    p.add_argument("--max-chars", type=int, default=8000)

    p = sub.add_parser("create")
    p.add_argument("path")
    p.add_argument("--content", default="")

    p = sub.add_parser("write")
    p.add_argument("path")
    p.add_argument("--content", required=True)

    p = sub.add_parser("replace")
    p.add_argument("path")
    p.add_argument("--old", required=True)
    p.add_argument("--new", required=True)
    p.add_argument("--all", action="store_true")

    p = sub.add_parser("append")
    p.add_argument("path")
    p.add_argument("--content", required=True)

    p = sub.add_parser("mkdir")
    p.add_argument("path")

    p = sub.add_parser("rm")
    p.add_argument("path")
    p.add_argument("--force", action="store_true")

    p = sub.add_parser("mv")
    p.add_argument("src")
    p.add_argument("dst")

    p = sub.add_parser("cp")
    p.add_argument("src")
    p.add_argument("dst")

    p = sub.add_parser("zip")
    p.add_argument("path")
    p.add_argument("archive")
    p.add_argument("--fmt", default="zip")

    p = sub.add_parser("unzip")
    p.add_argument("archive")
    p.add_argument("dest")

    args = parser.parse_args(argv)
    try:
        if args.cmd == "ls":
            print(list_directory(args.path, args.hidden))
        elif args.cmd == "search":
            print(search_files(args.root, args.pattern, args.keyword, args.max))
        elif args.cmd == "read":
            print(read_file(args.path, args.max_chars))
        elif args.cmd == "create":
            print(create_file(args.path, args.content))
        elif args.cmd == "write":
            print(update_file(args.path, args.content))
        elif args.cmd == "replace":
            print(replace_in_file(args.path, args.old, args.new, args.all))
        elif args.cmd == "append":
            print(append_to_file(args.path, args.content))
        elif args.cmd == "mkdir":
            print(create_directory(args.path))
        elif args.cmd == "rm":
            print(remove_path(args.path, args.force))
        elif args.cmd == "mv":
            print(move_path(args.src, args.dst))
        elif args.cmd == "cp":
            print(copy_path(args.src, args.dst))
        elif args.cmd == "zip":
            print(compress_path(args.path, args.archive, args.fmt))
        elif args.cmd == "unzip":
            print(extract_archive(args.archive, args.dest))
    except ValueError as e:
        print(e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(_main())
