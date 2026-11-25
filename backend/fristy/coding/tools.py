"""Coding assistant helpers: diffs, backed-up edits, VS Code, restricted terminal."""
from __future__ import annotations

import difflib
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from ..computer_control.base import ActionError
from ..files.sandbox import FileSandbox

# Commands that are never run, even with approval.
DENY_PATTERNS = [
    r"\bformat(\.com)?\s+[a-z]:", r"\bdiskpart\b", r"\bbcdedit\b", r"\bvssadmin\b.*\bdelete\b",
    r"\bcipher\s+/w", r"\breg(\.exe)?\s+(delete|add)\b", r"\bnetsh\s+advfirewall\b",
    r"Set-MpPreference", r"Add-MpPreference", r"\bsc(\.exe)?\s+(stop|delete|config)\b",
    r"\brm\s+-[a-z]*r[a-z]*f?\s+(/|~|[a-z]:\\?)\s*$", r"\brd\s+/s\s+/q\s+[a-z]:\\?\s*$",
    r"\bdel\s+/[a-z\s/]*\s+[a-z]:\\\*", r"\bshutdown\b", r"\btakeown\b", r"\bicacls\b.*\/grant",
    r"\bschtasks\b.*\/create", r"\bwmic\b.*\bdelete\b", r"Invoke-Expression|\biex\b",
    r"DownloadString|DownloadFile|Invoke-WebRequest.*\|\s*iex", r"\bcurl\b.*\|\s*(sh|bash|iex)",
    r"\bmkfs\b", r"\bdd\s+if=", r"-EncodedCommand|\s-enc\s", r"\brunas\b", r"Start-Process.*-Verb\s+RunAs",
    r"\bnet\s+user\b", r"\bnet\s+localgroup\b", r"Disable-WindowsOptionalFeature|Uninstall-WindowsFeature",
]
_DENY = [re.compile(p, re.IGNORECASE) for p in DENY_PATTERNS]
INSTALL_PATTERNS = re.compile(r"(?i)\b(npm|pnpm|yarn)\s+(i|install|add)\b|\bpip3?\s+install\b|\bwinget\s+install\b|"
                              r"\bchoco\s+install\b|\bcargo\s+(install|add)\b|\bdotnet\s+add\b")
SECRET_ENV = re.compile(r"(?i)(key|token|secret|password|passwd|credential)")


def check_command(command: str) -> dict[str, Any]:
    cmd = command.strip()
    if not cmd:
        raise ActionError("Empty command.")
    if len(cmd) > 2000:
        raise ActionError("Command too long.")
    for pat in _DENY:
        if pat.search(cmd):
            raise ActionError(f"This command is blocked by FRISTY's safety policy (matched '{pat.pattern}').",
                              "blocked_command")
    return {"installs_dependencies": bool(INSTALL_PATTERNS.search(cmd))}


def unified_diff(old: str, new: str, name: str) -> str:
    diff = difflib.unified_diff(old.splitlines(keepends=True), new.splitlines(keepends=True),
                                fromfile=f"a/{name}", tofile=f"b/{name}", n=3)
    out = "".join(diff)
    return out if len(out) < 60_000 else out[:60_000] + "\n... (diff truncated)"


class CodingTools:
    def __init__(self, sandbox: FileSandbox, backups_dir: Path):
        self.sb = sandbox
        self.backups_dir = backups_dir

    def preview_write(self, path: str, content: str) -> dict[str, Any]:
        p = self.sb.resolve(path)
        old = p.read_text(encoding="utf-8", errors="replace") if p.is_file() else ""
        return {"path": str(p), "exists": p.exists(), "diff": unified_diff(old, content, p.name),
                "new_lines": content.count("\n") + 1}

    def backup(self, p: Path) -> Path | None:
        if not p.is_file():
            return None
        stamp = time.strftime("%Y%m%d-%H%M%S")
        dest_dir = self.backups_dir / stamp
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / p.name
        i = 1
        while dest.exists():
            dest = dest_dir / f"{p.stem}.{i}{p.suffix}"
            i += 1
        shutil.copy2(p, dest)
        return dest

    def write_file(self, path: str, content: str) -> dict[str, Any]:
        p = self.sb.resolve(path)
        if p.is_dir():
            raise ActionError(f"'{p}' is a folder.")
        backup = self.backup(p)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".fristy-tmp")
        tmp.write_text(content, encoding="utf-8")
        os.replace(tmp, p)
        if p.read_text(encoding="utf-8") != content:
            raise ActionError("Write verification failed: file content differs.")
        return {"path": str(p), "backup": str(backup) if backup else None}

    def create_structure(self, root: str, files: dict[str, str]) -> list[str]:
        base = self.sb.resolve(root)
        created = []
        for rel, content in files.items():
            if Path(rel).is_absolute() or ".." in Path(rel).parts:
                raise ActionError(f"Invalid relative path '{rel}'.")
            target = self.sb.resolve(str(base / rel))
            if target.exists():
                raise ActionError(f"'{target}' already exists; refusing to overwrite.", "exists")
        for rel, content in files.items():
            target = base / rel
            if rel.endswith("/"):
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
            created.append(str(target))
        return created

    @staticmethod
    def find_vscode() -> str | None:
        exe = shutil.which("code")
        if exe:
            return exe
        if sys.platform == "win32":
            for base in (os.environ.get("LOCALAPPDATA", ""), os.environ.get("ProgramFiles", "")):
                for rel in ("Programs/Microsoft VS Code/Code.exe", "Microsoft VS Code/Code.exe"):
                    p = Path(base) / rel
                    if p.exists():
                        return str(p)
        return None

    def open_vscode(self, path: str | None) -> str:
        exe = self.find_vscode()
        if not exe:
            raise ActionError("Visual Studio Code was not found. Install it or add 'code' to PATH.", "not_found")
        args = [exe]
        if path:
            args.append(str(self.sb.resolve(path, must_exist=True)))
        subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         creationflags=0x08000000 if os.name == "nt" else 0)
        return exe

    def run_command(self, command: str, cwd: str, timeout: int = 300) -> dict[str, Any]:
        check_command(command)
        wd = self.sb.resolve(cwd, must_exist=True)
        if not wd.is_dir():
            raise ActionError(f"'{wd}' is not a folder.")
        env = {k: v for k, v in os.environ.items() if not SECRET_ENV.search(k) and not k.startswith("FRISTY_")}
        started = time.time()
        try:
            proc = subprocess.run(command, shell=True, cwd=str(wd), env=env, capture_output=True, text=True,
                                  encoding="utf-8", errors="replace", timeout=timeout, stdin=subprocess.DEVNULL,
                                  creationflags=0x08000000 if os.name == "nt" else 0)
        except subprocess.TimeoutExpired:
            raise ActionError(f"Command timed out after {timeout}s.", "timeout")

        def tail(s: str, n: int = 8000) -> str:
            return s if len(s) <= n else "...(truncated)...\n" + s[-n:]

        return {"exit_code": proc.returncode, "stdout": tail(proc.stdout), "stderr": tail(proc.stderr),
                "elapsed_s": round(time.time() - started, 2), "cwd": str(wd)}
