"""Restricts file operations to user-approved directories."""
from __future__ import annotations

import os
from pathlib import Path

from ..computer_control.base import ActionError

# Never touched even if a parent directory was approved.
_PROTECTED_NAMES = {
    "windows", "system32", "syswow64", "$recycle.bin", "system volume information",
    "program files", "program files (x86)", "programdata", ".ssh", ".gnupg", "appdata",
}
_PROTECTED_FILES = {"ntuser.dat", "pagefile.sys", "hiberfil.sys", "swapfile.sys", "bootmgr"}


class FileSandbox:
    def __init__(self, settings_store):
        self.settings = settings_store

    @property
    def roots(self) -> list[Path]:
        out = []
        for d in self.settings.current.approved_dirs:
            try:
                out.append(Path(d).expanduser().resolve())
            except OSError:
                continue
        return out

    def resolve(self, path: str, must_exist: bool = False) -> Path:
        if not self.settings.current.permissions.get("file_access"):
            raise ActionError("File access permission is disabled.", "permission_denied")
        roots = self.roots
        if not roots:
            raise ActionError("No approved folders. Add folders in Settings > Files before using file actions.",
                              "no_approved_dirs")
        raw = Path(os.path.expandvars(str(path))).expanduser()
        if not raw.is_absolute():
            raw = roots[0] / raw
        # resolve() follows symlinks/junctions, so links that point outside an
        # approved root are rejected too.
        p = raw.resolve()
        if not any(p == r or r in p.parents for r in roots):
            raise ActionError(f"'{p}' is outside the approved folders.", "path_not_allowed")
        rel_parts = []
        for r in roots:
            if p == r or r in p.parents:
                rel_parts = [x.lower() for x in p.relative_to(r).parts]
                break
        if any(part in _PROTECTED_NAMES for part in rel_parts) or p.name.lower() in _PROTECTED_FILES:
            raise ActionError(f"'{p}' is a protected system location.", "path_protected")
        if must_exist and not p.exists():
            raise ActionError(f"'{p}' does not exist.", "not_found")
        return p

    def default_root(self) -> Path:
        roots = self.roots
        if not roots:
            raise ActionError("No approved folders configured.", "no_approved_dirs")
        return roots[0]
