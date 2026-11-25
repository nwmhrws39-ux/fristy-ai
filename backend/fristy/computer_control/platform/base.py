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
    "אפיק": "epic games",
    "אפיק גיימס": "epic games",
    "epic": "epic games",
    "epicgames": "epic games",
    "epic games launcher": "epic games",
    "מיינקראפט": "minecraft",
}


_HE2LAT = {"א": "a", "ב": "b", "ג": "g", "ד": "d", "ה": "h", "ו": "o", "ז": "z", "ח": "h", "ט": "t", "י": "i",
           "כ": "k", "ך": "k", "ל": "l", "מ": "m", "ם": "m", "נ": "n", "ן": "n", "ס": "s", "ע": "a", "פ": "p", "ף": "f",
           "צ": "ts", "ץ": "ts", "ק": "k", "ר": "r", "ש": "sh", "ת": "t", "'": ""}


def transliterate_he(s: str) -> str:
    """Rough Hebrew -> Latin transliteration ("אפיק גיימס" -> "apik giims") for fuzzy name matching."""
    out = "".join(_HE2LAT.get(ch, ch) for ch in s)
    return out.replace("ii", "i").replace("ph", "f")


# Words people add around an app name: "close the epic games that's running on my screen".
_FILLER = re.compile(
    r"(?i)^(?:the|my|this|that|app|application|program|game|ה|את|של|האפליקציה|התוכנה|המשחק|אפליקציית|תוכנת)\s+|"
    r"\s+(?:app|application|program|window|game|please|now|for me|that'?s|that is|which is|that'?s (?:running|open)|which is (?:running|open)|"
    r"(?:running|open)(?: on (?:my|the) (?:screen|pc|computer))?|on (?:my|the) (?:screen|pc|computer)|in the background|"
    r"בבקשה|עכשיו|שלי|לי|שרץ.*|שפתוח.*|שפתוחה.*|שרצה.*|שעובד.*|במסך|בבמסך|ברקע|במחשב|פתוח|פתוחה)$"
)


def clean_app_query(raw: str) -> str:
    t = re.sub(r"\s+", " ", (raw or "").strip())
    for _ in range(6):
        new = _FILLER.sub("", t).strip()
        if new == t:
            break
        t = new
    # Hebrew definite article glued to the name: "האפיק גיימס" -> "אפיק גיימס"
    t = re.sub(r"^ה(?=[\u0590-\u05ff]{3,})", "", t)
    return t


def normalize_name(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "").lower().strip()
    s = re.sub(r"[™®©]", "", s)
    s = re.sub(r"\s+", " ", s)
    return s


def match_apps(query: str, apps: list[AppEntry], limit: int = 5, games_only: bool = False) -> list[tuple[float, AppEntry]]:
    q = normalize_name(clean_app_query(query))
    q = APP_ALIASES.get(q, q)
    if re.search(r"[\u0590-\u05ff]", q) and q not in APP_ALIASES.values():
        q = transliterate_he(q)
    scored: list[tuple[float, AppEntry]] = []
    for app in apps:
        if games_only and not app.is_game:
            continue
        names = [normalize_name(app.name)] + [normalize_name(a) for a in app.aliases]
        best = 0.0
        nq = re.sub(r"[^a-z0-9\u0590-\u05ff]", "", q)
        for n in names:
            if not n:
                continue
            nn = re.sub(r"[^a-z0-9\u0590-\u05ff]", "", n)
            if nq and nn == nq:
                best = max(best, 1.0)
                continue
            if len(nq) >= 4 and nn.startswith(nq):
                best = max(best, 0.9)
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

    def running_processes(self) -> list[dict[str, Any]]:
        """Running processes with their main window title (if any)."""
        titles: dict[int, str] = {}
        try:
            for w in self.list_windows():
                titles.setdefault(w.pid, w.title)
        except ActionError:
            pass
        out = []
        for p in psutil.process_iter(["name", "pid", "exe"]):
            try:
                out.append({"name": p.info["name"] or "", "pid": p.info["pid"], "exe": p.info.get("exe") or "",
                            "title": titles.get(p.info["pid"], "")})
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return out

    def close_pids(self, pids: list[int], force: bool = False, timeout: float = 8.0) -> int:
        raise UnsupportedPlatform("Closing applications")

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


# ------------------------------------------------------------- process lookup
# Never closed by FRISTY, whatever the request.
PROTECTED_PROCESSES = {
    "system", "idle", "registry", "smss.exe", "csrss.exe", "wininit.exe", "winlogon.exe", "services.exe",
    "lsass.exe", "svchost.exe", "dwm.exe", "explorer.exe", "fontdrvhost.exe", "sihost.exe", "ctfmon.exe",
    "taskhostw.exe", "runtimebroker.exe", "searchhost.exe", "startmenuexperiencehost.exe", "shellexperiencehost.exe",
    "securityhealthservice.exe", "msmpeng.exe", "audiodg.exe", "conhost.exe", "lockapp.exe", "logonui.exe",
    "fristy ai.exe", "python.exe", "pythonw.exe", "ollama.exe", "ollama app.exe",
}


def _norm(s: str) -> str:
    s = normalize_name(s)
    s = re.sub(r"\.exe$", "", s)
    return re.sub(r"[^a-z0-9֐-׿]", "", s)


def find_running(query: str, processes: list[dict[str, Any]], allow_protected: bool = False) -> list[dict[str, Any]]:
    """Rank running applications for a spoken/written name.

    Matches the process name, window titles and the install folder, so "epic games",
    "epicgames" or "Epic" all find EpicGamesLauncher.exe. Returns groups (one per
    process name) sorted by score: {name, pids, titles, exe, score}.
    """
    q_raw = normalize_name(clean_app_query(query))
    q_raw = APP_ALIASES.get(q_raw, q_raw)
    if re.search(r"[\u0590-\u05ff]", q_raw):
        q_raw = transliterate_he(q_raw)
    q = _norm(q_raw)
    if not q:
        return []
    groups: dict[str, dict[str, Any]] = {}
    for p in processes:
        name = (p.get("name") or "").strip()
        if not name or (not allow_protected and name.lower() in PROTECTED_PROCESSES):
            continue
        n = _norm(name)
        title = p.get("title") or ""
        t = _norm(title)
        exe = p.get("exe") or ""
        folders = [_norm(part) for part in re.split(r"[\\/]", exe)[:-1] if part and ":" not in part]
        folders = [f for f in folders if f not in ("programfiles", "programfilesx86", "users", "appdata", "local",
                                                   "roaming", "programs", "windows", "bin", "app", "")]
        if n == q:
            score = 1.0
        elif len(q) >= 3 and n.startswith(q):
            score = 0.95
        elif len(q) >= 4 and (q in n or (len(n) >= 4 and n in q)):
            score = 0.9
        elif len(q) >= 3 and t and (q in t or t == q):
            score = 0.86
        elif len(q) >= 4 and any(q in f or (len(f) >= 4 and f in q) for f in folders):
            score = 0.82
        else:
            score = difflib.SequenceMatcher(None, q, n).ratio() * 0.8
        if score < 0.6:
            continue
        g = groups.setdefault(name.lower(), {"name": name, "pids": [], "titles": [], "exe": exe, "score": 0.0})
        g["pids"].append(p.get("pid"))
        if title and title not in g["titles"]:
            g["titles"].append(title[:80])
        g["score"] = max(g["score"], score)
    return sorted(groups.values(), key=lambda g: (-g["score"], -len(g["titles"])))
