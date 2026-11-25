"""Non-Windows backend used for development and CI.

Only portable features are implemented; Windows-specific actions raise
``UnsupportedPlatform`` with a clear message instead of pretending to work.
"""
from __future__ import annotations

from .base import PlatformBackend


class GenericBackend(PlatformBackend):
    name = "generic"
