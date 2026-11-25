"""Interface every platform backend implements."""
from __future__ import annotations

import difflib
import os
import platform
import re
import shutil
import subprocess
import time
import unicodedata
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

import psutil

from ..base import ActionError, UnsupportedPlatform


@dataclass
class AppEntry:
    name: str
    target: str  # .lnk path, exe path, AppUserModelID or launcher URI
    kind: str  # shortcut | uwp | steam | epic | exe
    is_game: bool = False
    process_hint: str = ""
    aliases: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class WindowInfo:
    handle: int
    title: str
    process: str
    pid: int
    minimized: bool = False
    maximized: bool = False
    foreground: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# Common names users say (English + Hebrew) -> canonical app search terms.
APP_ALIASES: dict[str, str] = {
    "דיסקורד": "discord",
    "כרום": "chrome",
    "גוגל כרום": "chrome",
    "ספוטיפיי": "spotify",
    "סטים": "steam",
    "פנקס רשימות": "notepad",
    "נוטפד": "notepad",
    "מחשבון": "calculator",
    "calc": "calculator",
    "וורד": "word",
    "אקסל": "excel",
    "פאוורפוינט": "powerpoint",
    "סייר הקבצים": "file explorer",
    "explorer": "file explorer",
    "vscode": "visual studio code",
    "vs code": "visual studio code",
    "ויז'ואל סטודיו קוד": "visual studio code",
    "edge": "microsoft edge",
    "אדג'": "microsoft edge",
    "פיירפוקס": "firefox",
    "וואטסאפ": "whatsapp",
    "טלגרם": "telegram",
    "זום": "zoom",
    "טימס": "teams",
    "gta 5": "grand theft auto v",
    "gta v": "grand theft auto v",
    "gta": "grand theft auto v",
    "ג'י טי איי": "grand theft auto v",
    "cs2": "counter-strike 2",
    "csgo": "counter-strike 2",
    "lol": "league of legends",
    "פורטנייט": "fortnite",
    "מיינקראפט": "minecraft",
}


def normalize_name(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "").lower().strip()
    s = re.sub(r"[™®©]", "", s)
    s = re.sub(r"\s+", " ", s)
    return s


def match_apps(query: str, apps: list[AppEntry], limit: int = 5, games_only: bool = False) -> list[tuple[float, AppEntry]]:
    q = normalize_name(query)
    q = APP_ALIASES.get(q, q)
    scored: list[tuple[float, AppEntry]] = []
    for app in apps:
        if games_only and not app.is_game:
            continue
        names = [normalize_name(app.name)] + [normalize_name(a) for a in app.aliases]
        best = 0.0
        for n in names:
            if not n:
                continue
            if n == q:
                score = 1.0
            elif n.startswith(q) or q.startswith(n):
                score = 0.9 if len(q) >= 3 else 0.6
            elif q in n.split() or (len(q) >= 4 and q in n):
                score = 0.8
            else:
                score = difflib.SequenceMatcher(None, q, n).ratio() * 0.85
            best = max(best, score)
        # Prefer real applications over "Uninstall X" / "X Help" shortcuts.
        lname = normalize_name(app.name)
        if any(w in lname for w in ("uninstall", "readme", "help", "documentation", "website", "release notes")):
            best -= 0.3
        if best >= 0.55:
            scored.append((round(best, 3), app))
    scored.sort(key=lambda t: (-t[0], len(t[1].name)))
    return scored[:limit]


class PlatformBackend:
    name = "base"

    # --- applications -------------------------------------------------
    def list_apps(self, refresh: bool = False) -> list[AppEntry]:
        raise UnsupportedPlatform("Application discovery")

    def launch(self, app: AppEntry) -> None:
        raise UnsupportedPlatform("Launching applications")

    def open_uri(self, uri: str) -> None:
        import webbrowser

        if not webbrowser.open(uri):
            raise ActionError(f"No handler available to open {uri}")

    def open_path(self, path: str) -> None:
        opener = shutil.which("xdg-open") or shutil.which("open")
        if not opener:
            raise UnsupportedPlatform("Opening files and folders")
        subprocess.Popen([opener, path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def process_running(self, name: str) -> bool:
        n = name.lower()
        for p in psutil.process_iter(["name"]):
            try:
                if (p.info["name"] or "").lower() == n:
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return False

    # --- windows ------------------------------------------------------
    def list_windows(self) -> list[WindowInfo]:
        raise UnsupportedPlatform("Window management")

    def focus_window(self, handle: int) -> bool:
        raise UnsupportedPlatform("Window management")

    def minimize_window(self, handle: int) -> bool:
        raise UnsupportedPlatform("Window management")

    def maximize_window(self, handle: int) -> bool:
        raise UnsupportedPlatform("Window management")

    def restore_window(self, handle: int) -> bool:
        raise UnsupportedPlatform("Window management")

    def close_process_windows(self, process_name: str, force: bool = False, timeout: float = 8.0) -> int:
        raise UnsupportedPlatform("Closing applications")

    def foreground_window(self) -> Optional[WindowInfo]:
        return None

    # --- audio / media ------------------------------------------------
    def get_volume(self) -> tuple[int, bool]:
        raise UnsupportedPlatform("Volume control")

    def set_volume(self, level: int) -> None:
        raise UnsupportedPlatform("Volume control")

    def set_mute(self, mute: bool) -> None:
        raise UnsupportedPlatform("Volume control")

    def media_key(self, command: str) -> None:
        raise UnsupportedPlatform("Media control")

    # --- power --------------------------------------------------------
    def lock(self) -> None:
        raise UnsupportedPlatform("Locking the computer")

    def shutdown(self, delay: int, restart: bool = False) -> None:
        raise UnsupportedPlatform("Shutdown/restart")

    def cancel_shutdown(self) -> None:
        raise UnsupportedPlatform("Cancelling shutdown")

    # --- input ----------------------------------------------------------
    def is_secure_desktop_active(self) -> bool:
        return False

    # --- information --------------------------------------------------
    def system_info(self) -> dict[str, Any]:
        vm = psutil.virtual_memory()
        disks = []
        for part in psutil.disk_partitions(all=False):
            try:
                u = psutil.disk_usage(part.mountpoint)
            except (PermissionError, OSError):
                continue
            disks.append({"mount": part.mountpoint, "total_gb": round(u.total / 1e9, 1),
                          "free_gb": round(u.free / 1e9, 1), "percent": u.percent})
        battery = None
        try:
            b = psutil.sensors_battery()
            if b:
                battery = {"percent": round(b.percent), "plugged": b.power_plugged}
        except Exception:
            pass
        freq = psutil.cpu_freq()
        return {
            "os": f"{platform.system()} {platform.release()} ({platform.version()})",
            "machine": platform.machine(),
            "hostname": platform.node(),
            "cpu": platform.processor() or platform.machine(),
            "cpu_cores_physical": psutil.cpu_count(logical=False),
            "cpu_cores_logical": psutil.cpu_count(),
            "cpu_freq_mhz": round(freq.current) if freq else None,
            "cpu_percent": psutil.cpu_percent(interval=0.3),
            "ram_total_gb": round(vm.total / 1e9, 1),
            "ram_used_percent": vm.percent,
            "disks": disks,
            "battery": battery,
            "uptime_hours": round((time.time() - psutil.boot_time()) / 3600, 1),
            "gpus": self.gpu_info(),
        }

    def gpu_info(self) -> list[dict[str, Any]]:
        exe = shutil.which("nvidia-smi")
        if not exe:
            return []
        try:
            out = subprocess.run(
                [exe, "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5, **_no_window(),
            ).stdout
        except Exception:
            return []
        gpus = []
        for line in out.strip().splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) == 5:
                def num(x: str) -> Optional[float]:
                    try:
                        return float(x)
                    except ValueError:
                        return None
                gpus.append({"name": parts[0], "utilization_percent": num(parts[1]),
                             "memory_used_mb": num(parts[2]), "memory_total_mb": num(parts[3]),
                             "temperature_c": num(parts[4])})
        return gpus

    def temperatures(self) -> dict[str, float]:
        temps: dict[str, float] = {}
        fn = getattr(psutil, "sensors_temperatures", None)
        if fn:
            try:
                for name, entries in fn().items():
                    for e in entries:
                        if e.current:
                            temps[f"{name}:{e.label or 'temp'}"] = float(e.current)
            except Exception:
                pass
        for i, g in enumerate(self.gpu_info()):
            if g.get("temperature_c") is not None:
                temps[f"gpu{i}"] = g["temperature_c"]
        return temps


def _no_window() -> dict[str, Any]:
    if os.name == "nt":
        return {"creationflags": 0x08000000}  # CREATE_NO_WINDOW
    return {}
