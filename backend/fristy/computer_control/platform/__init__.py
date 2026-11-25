"""Platform backends. ``get_platform()`` returns the backend for this OS."""
from __future__ import annotations

import sys

from .base import AppEntry, PlatformBackend, WindowInfo


def get_platform() -> PlatformBackend:
    if sys.platform == "win32":
        from .windows import WindowsBackend

        return WindowsBackend()
    from .generic import GenericBackend

    return GenericBackend()


__all__ = ["AppEntry", "PlatformBackend", "WindowInfo", "get_platform"]
