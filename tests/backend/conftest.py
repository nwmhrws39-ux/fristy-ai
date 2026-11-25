"""Shared fixtures. FakePlatform records every call so computer actions are
tested in a safe environment without touching the real machine."""
from __future__ import annotations

import asyncio
import pathlib

import pytest

from fristy.computer_control.platform.base import AppEntry, PlatformBackend, WindowInfo
from fristy.config import RuntimeConfig
from fristy.core.bootstrap import build_services


class FakePlatform(PlatformBackend):
    name = "fake"

    def __init__(self):
        self.calls: list[tuple] = []
        self.volume, self.muted = 50, False
        self.apps = [
            AppEntry("Discord", r"C:\fake\Discord.lnk", "shortcut", process_hint="discord"),
            AppEntry("Grand Theft Auto V", "steam://rungameid/271590", "steam", is_game=True, process_hint="gta5"),
            AppEntry("Visual Studio Code", r"C:\fake\Code.lnk", "shortcut"),
            AppEntry("Uninstall Discord", r"C:\fake\Uninst.lnk", "shortcut"),
            AppEntry("Notepad", "notepad", "uwp", process_hint="notepad"),
        ]
        self.windows = [WindowInfo(1, "Untitled - Notepad", "notepad.exe", 100),
                        WindowInfo(2, "Discord", "Discord.exe", 200)]
        self.running = {"notepad.exe"}
        self.secure = False
        self.fg: WindowInfo | None = None
        self.volume_readback_offset = 0

    def list_apps(self, refresh=False):
        return self.apps

    def launch(self, app):
        self.calls.append(("launch", app.name))
        self.windows.append(WindowInfo(10 + len(self.windows), app.name, (app.process_hint or "x") + ".exe", 900 + len(self.windows)))

    def open_uri(self, uri):
        self.calls.append(("open_uri", uri))

    def open_path(self, path):
        self.calls.append(("open_path", path))

    def process_running(self, name):
        return name.lower() in self.running

    def list_windows(self):
        return list(self.windows)

    def focus_window(self, handle):
        self.calls.append(("focus", handle))
        return True

    def minimize_window(self, handle):
        self.calls.append(("minimize", handle))
        return True

    def maximize_window(self, handle):
        self.calls.append(("maximize", handle))
        return True

    def close_process_windows(self, process_name, force=False, timeout=8.0):
        self.calls.append(("close", process_name, force))
        self.running.discard(process_name.lower())
        return 1

    def foreground_window(self):
        return self.fg

    def get_volume(self):
        return self.volume + self.volume_readback_offset, self.muted

    def set_volume(self, level):
        self.calls.append(("set_volume", level))
        self.volume = level

    def set_mute(self, mute):
        self.calls.append(("mute", mute))
        self.muted = mute

    def media_key(self, command):
        self.calls.append(("media", command))

    def lock(self):
        self.calls.append(("lock",))

    def shutdown(self, delay, restart=False):
        self.calls.append(("shutdown", delay, restart))

    def cancel_shutdown(self):
        self.calls.append(("cancel_shutdown",))

    def is_secure_desktop_active(self):
        return self.secure

    def gpu_info(self):
        return []


@pytest.fixture
def platform():
    return FakePlatform()


@pytest.fixture
def svc(tmp_path: pathlib.Path, platform):
    cfg = RuntimeConfig()
    cfg.data_dir = tmp_path / "data"
    cfg.token = "test-token"
    cfg.port = 8765
    s = build_services(cfg, platform=platform, use_keyring=False)
    s.engine.is_windows = True  # exercise Windows actions against the fake backend
    yield s
    s.db.close()


@pytest.fixture
def approve_all(svc):
    """Auto-answer confirmation requests; records what was asked."""
    asked = []
    decision = {"value": True}

    async def request(action, summary, risk, source, details=None, timeout=None):
        asked.append({"action": action, "summary": summary, "risk": risk, "source": source, "details": details})
        return decision["value"]

    svc.confirmations.request = request
    return type("Approver", (), {"asked": asked, "decision": decision})


@pytest.fixture
def workdir(tmp_path, svc):
    d = tmp_path / "approved"
    d.mkdir()
    svc.settings.update({"approved_dirs": [str(d)], "permissions": {**svc.settings.current.permissions,
                                                                     "file_access": True}})
    return d


def enable(svc, *perms):
    svc.settings.update({"permissions": {**svc.settings.current.permissions, **{p: True for p in perms}}})
