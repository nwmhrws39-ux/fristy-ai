"""Pure-Python parsers for Steam and Epic Games library metadata (testable on any OS)."""
from __future__ import annotations

import json
import re
from pathlib import Path

from .base import AppEntry

_KV = re.compile(r'"([^"]*)"\s+"((?:[^"\\]|\\.)*)"')


def parse_vdf_paths(text: str) -> list[str]:
    """Extract library folder paths from Steam's libraryfolders.vdf (old & new formats)."""
    paths: list[str] = []
    for key, value in _KV.findall(text):
        if key == "path" or key.isdigit():
            v = value.replace("\\\\", "\\")
            if (":" in v or v.startswith("/")) and v not in paths:
                paths.append(v)
    return paths


def parse_acf(text: str) -> dict[str, str]:
    """Top-level key/values of a Steam appmanifest_*.acf file."""
    out: dict[str, str] = {}
    for key, value in _KV.findall(text):
        out.setdefault(key, value)
    return out


STEAM_NON_GAMES = re.compile(r"(?i)(redistributable|steamworks common|proton|steam linux runtime|soundtrack|dedicated server|sdk)")


def steam_games(steam_root: Path) -> list[AppEntry]:
    libraries = [steam_root]
    vdf = steam_root / "steamapps" / "libraryfolders.vdf"
    if vdf.exists():
        try:
            for p in parse_vdf_paths(vdf.read_text(encoding="utf-8", errors="ignore")):
                lp = Path(p)
                if lp not in libraries:
                    libraries.append(lp)
        except OSError:
            pass
    games: dict[str, AppEntry] = {}
    for lib in libraries:
        apps_dir = lib / "steamapps"
        if not apps_dir.is_dir():
            continue
        for acf in apps_dir.glob("appmanifest_*.acf"):
            try:
                data = parse_acf(acf.read_text(encoding="utf-8", errors="ignore"))
            except OSError:
                continue
            appid, name = data.get("appid"), data.get("name")
            if not appid or not name or STEAM_NON_GAMES.search(name):
                continue
            games[appid] = AppEntry(name=name, target=f"steam://rungameid/{appid}", kind="steam", is_game=True,
                                    process_hint=data.get("installdir", ""))
    return list(games.values())


def epic_games(manifest_dir: Path) -> list[AppEntry]:
    out: list[AppEntry] = []
    if not manifest_dir.is_dir():
        return out
    for item in manifest_dir.glob("*.item"):
        try:
            data = json.loads(item.read_text(encoding="utf-8", errors="ignore"))
        except (OSError, ValueError):
            continue
        name = data.get("DisplayName")
        app_name = data.get("AppName")
        if not name or not app_name:
            continue
        if "games" not in [c.lower() for c in data.get("AppCategories", ["games"])]:
            continue
        exe = Path(data.get("LaunchExecutable") or "").name
        out.append(AppEntry(
            name=name,
            target=f"com.epicgames.launcher://apps/{app_name}?action=launch&silent=true",
            kind="epic", is_game=True, process_hint=exe,
        ))
    return out
