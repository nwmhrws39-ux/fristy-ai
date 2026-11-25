"""File operations. Every path goes through FileSandbox.resolve()."""
from __future__ import annotations

import fnmatch
import hashlib
import os
import shutil
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterator

from ..computer_control.base import ActionError
from .sandbox import FileSandbox

TEXT_EXTS = {
    ".txt", ".md", ".markdown", ".csv", ".json", ".xml", ".yaml", ".yml", ".ini", ".cfg", ".toml", ".log",
    ".py", ".js", ".ts", ".tsx", ".jsx", ".html", ".css", ".scss", ".java", ".c", ".h", ".cpp", ".hpp",
    ".cs", ".go", ".rs", ".rb", ".php", ".sh", ".ps1", ".bat", ".sql", ".kt", ".swift", ".lua", ".vue",
}
DOC_EXTS = TEXT_EXTS | {".pdf", ".docx"}

ORGANIZE_CATEGORIES: dict[str, set[str]] = {
    "Images": {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg", ".heic", ".ico", ".tiff"},
    "Videos": {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".webm", ".flv"},
    "Audio": {".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".wma"},
    "Documents": {".pdf", ".doc", ".docx", ".txt", ".rtf", ".odt", ".xls", ".xlsx", ".ppt", ".pptx", ".csv", ".md"},
    "Archives": {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz"},
    "Installers": {".exe", ".msi", ".msix", ".appx"},
    "Code": {".py", ".js", ".ts", ".html", ".css", ".json", ".java", ".c", ".cpp", ".cs", ".go", ".rs"},
}
SKIP_DIRS = {"node_modules", ".git", "__pycache__", ".venv", "venv", "$recycle.bin", "system volume information"}
MAX_SCAN = 200_000


def _walk(root: Path, max_depth: int = 12) -> Iterator[Path]:
    count = 0
    stack = [(root, 0)]
    while stack:
        d, depth = stack.pop()
        try:
            with os.scandir(d) as it:
                for e in it:
                    count += 1
                    if count > MAX_SCAN:
                        return
                    try:
                        if e.is_dir(follow_symlinks=False):
                            if depth < max_depth and e.name.lower() not in SKIP_DIRS:
                                stack.append((Path(e.path), depth + 1))
                        elif e.is_file(follow_symlinks=False):
                            yield Path(e.path)
                    except OSError:
                        continue
        except (PermissionError, OSError):
            continue


def _info(p: Path) -> dict[str, Any]:
    try:
        st = p.stat()
        return {"path": str(p), "name": p.name, "size": st.st_size, "modified": st.st_mtime}
    except OSError:
        return {"path": str(p), "name": p.name}


class FileOps:
    def __init__(self, sandbox: FileSandbox):
        self.sb = sandbox

    def _search_roots(self, root: str | None) -> list[Path]:
        if root:
            return [self.sb.resolve(root, must_exist=True)]
        self.sb.resolve(str(self.sb.default_root()))
        return self.sb.roots

    def find_files(self, query: str, root: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        q = query.strip().lower()
        if not q:
            raise ActionError("Empty search query.")
        pattern = q if any(c in q for c in "*?[") else f"*{q}*"
        out = []
        for r in self._search_roots(root):
            for p in _walk(r):
                if fnmatch.fnmatch(p.name.lower(), pattern):
                    out.append(_info(p))
                    if len(out) >= limit:
                        return out
        return out

    def search_contents(self, text: str, root: str | None = None, limit: int = 30,
                        max_file_mb: float = 5.0) -> list[dict[str, Any]]:
        needle = text.lower()
        if len(needle) < 2:
            raise ActionError("Search text must be at least 2 characters.")
        out = []
        for r in self._search_roots(root):
            for p in _walk(r):
                if p.suffix.lower() not in TEXT_EXTS:
                    continue
                try:
                    if p.stat().st_size > max_file_mb * 1e6:
                        continue
                    with open(p, "r", encoding="utf-8", errors="ignore") as fh:
                        for lineno, line in enumerate(fh, 1):
                            if needle in line.lower():
                                out.append({**_info(p), "line": lineno, "snippet": line.strip()[:200]})
                                break
                except OSError:
                    continue
                if len(out) >= limit:
                    return out
        return out

    def create_folder(self, path: str) -> Path:
        p = self.sb.resolve(path)
        if p.exists():
            raise ActionError(f"'{p}' already exists.", "exists")
        p.mkdir(parents=True)
        return p

    def rename(self, path: str, new_name: str) -> Path:
        if any(c in new_name for c in '\\/:*?"<>|') or new_name in (".", ".."):
            raise ActionError("New name contains invalid characters.")
        src = self.sb.resolve(path, must_exist=True)
        dst = self.sb.resolve(str(src.parent / new_name))
        if dst.exists():
            raise ActionError(f"'{dst.name}' already exists.", "exists")
        src.rename(dst)
        return dst

    def _dest(self, src: Path, destination: str) -> Path:
        dst = self.sb.resolve(destination)
        if dst.is_dir():
            dst = self.sb.resolve(str(dst / src.name))
        return dst

    def copy(self, source: str, destination: str, overwrite: bool = False) -> Path:
        src = self.sb.resolve(source, must_exist=True)
        dst = self._dest(src, destination)
        if dst.exists() and not overwrite:
            raise ActionError(f"'{dst}' already exists. Ask again with overwrite to replace it.", "exists")
        if src.is_dir():
            if dst.exists():
                self.trash(str(dst))
            shutil.copytree(src, dst)
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            if dst.exists():
                self.trash(str(dst))
            shutil.copy2(src, dst)
        return dst

    def move(self, source: str, destination: str, overwrite: bool = False) -> Path:
        src = self.sb.resolve(source, must_exist=True)
        dst = self._dest(src, destination)
        if dst == src:
            raise ActionError("Source and destination are the same.")
        if src in dst.parents:
            raise ActionError("Cannot move a folder into itself.")
        if dst.exists():
            if not overwrite:
                raise ActionError(f"'{dst}' already exists. Ask again with overwrite to replace it.", "exists")
            self.trash(str(dst))
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        return dst

    def trash(self, path: str) -> Path:
        p = self.sb.resolve(path, must_exist=True)
        if p in self.sb.roots:
            raise ActionError("Refusing to delete an approved root folder itself.", "path_protected")
        try:
            from send2trash import send2trash
        except ImportError as exc:  # pragma: no cover
            raise ActionError("Recycle Bin support (send2trash) is not installed; deletion refused.") from exc
        send2trash(str(p))
        return p

    def plan_organize(self, folder: str) -> dict[str, list[str]]:
        root = self.sb.resolve(folder, must_exist=True)
        if not root.is_dir():
            raise ActionError(f"'{root}' is not a folder.")
        plan: dict[str, list[str]] = defaultdict(list)
        for e in root.iterdir():
            if not e.is_file() or e.name.startswith("."):
                continue
            ext = e.suffix.lower()
            if ext in (".crdownload", ".part", ".tmp"):
                continue  # still downloading
            cat = next((c for c, exts in ORGANIZE_CATEGORIES.items() if ext in exts), "Other")
            plan[cat].append(e.name)
        return dict(plan)

    def organize(self, folder: str) -> dict[str, int]:
        root = self.sb.resolve(folder, must_exist=True)
        moved: dict[str, int] = {}
        for cat, names in self.plan_organize(folder).items():
            target_dir = root / cat
            target_dir.mkdir(exist_ok=True)
            for n in names:
                src = root / n
                dst = target_dir / n
                i = 1
                while dst.exists():
                    dst = target_dir / f"{src.stem} ({i}){src.suffix}"
                    i += 1
                shutil.move(str(src), str(dst))
                moved[cat] = moved.get(cat, 0) + 1
        return moved

    def large_files(self, root: str | None = None, min_mb: float = 100, limit: int = 30) -> list[dict[str, Any]]:
        out = []
        for r in self._search_roots(root):
            for p in _walk(r):
                try:
                    size = p.stat().st_size
                except OSError:
                    continue
                if size >= min_mb * 1e6:
                    out.append(_info(p))
        out.sort(key=lambda x: -x.get("size", 0))
        return out[:limit]

    def duplicates(self, root: str | None = None, min_kb: float = 1, limit_groups: int = 50) -> list[dict[str, Any]]:
        by_size: dict[int, list[Path]] = defaultdict(list)
        for r in self._search_roots(root):
            for p in _walk(r):
                try:
                    s = p.stat().st_size
                except OSError:
                    continue
                if s >= min_kb * 1024:
                    by_size[s].append(p)
        groups = []
        for size, paths in by_size.items():
            if len(paths) < 2:
                continue
            by_hash: dict[str, list[Path]] = defaultdict(list)
            for p in paths:
                h = _hash_file(p)
                if h:
                    by_hash[h].append(p)
            for h, same in by_hash.items():
                if len(same) > 1:
                    groups.append({"hash": h, "size": size, "files": [str(x) for x in same],
                                   "wasted_bytes": size * (len(same) - 1)})
        groups.sort(key=lambda g: -g["wasted_bytes"])
        return groups[:limit_groups]

    def read_text(self, path: str, max_chars: int = 40_000) -> str:
        p = self.sb.resolve(path, must_exist=True)
        ext = p.suffix.lower()
        if p.stat().st_size > 50e6:
            raise ActionError("File is too large to read (>50 MB).")
        if ext == ".pdf":
            try:
                from pypdf import PdfReader
            except ImportError as exc:
                raise ActionError("PDF support is not installed.") from exc
            reader = PdfReader(str(p))
            text = "\n".join((page.extract_text() or "") for page in reader.pages[:200])
        elif ext == ".docx":
            try:
                import docx  # python-docx
            except ImportError as exc:
                raise ActionError("Word document support is not installed.") from exc
            text = "\n".join(par.text for par in docx.Document(str(p)).paragraphs)
        elif ext in TEXT_EXTS or ext == "":
            text = p.read_text(encoding="utf-8", errors="replace")
        else:
            raise ActionError(f"Unsupported document type '{ext}'. Supported: txt, md, code files, pdf, docx.")
        if len(text) > max_chars:
            text = text[:max_chars] + f"\n\n[... truncated, {len(text) - max_chars} more characters]"
        return text

    def write_text(self, path: str, content: str, overwrite: bool = False) -> Path:
        p = self.sb.resolve(path)
        if p.exists():
            if not overwrite:
                raise ActionError(f"'{p}' already exists. Ask again with overwrite to replace it.", "exists")
            if p.is_dir():
                raise ActionError(f"'{p}' is a folder.")
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + f".fristy-tmp-{int(time.time()*1000)}")
        tmp.write_text(content, encoding="utf-8")
        os.replace(tmp, p)
        return p

    def listdir(self, path: str, limit: int = 200) -> list[dict[str, Any]]:
        p = self.sb.resolve(path, must_exist=True)
        if not p.is_dir():
            raise ActionError(f"'{p}' is not a folder.")
        out = []
        for e in sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))[:limit]:
            item = _info(e)
            item["is_dir"] = e.is_dir()
            out.append(item)
        return out


def _hash_file(p: Path, chunk: int = 1 << 20) -> str | None:
    h = hashlib.blake2b(digest_size=20)
    try:
        with open(p, "rb") as fh:
            while True:
                b = fh.read(chunk)
                if not b:
                    break
                h.update(b)
    except OSError:
        return None
    return h.hexdigest()
