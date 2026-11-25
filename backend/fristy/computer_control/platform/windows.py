"""Windows 10/11 backend using official Win32 / Core Audio / shell APIs.

* Window management: EnumWindows, ShowWindow, SetForegroundWindow, WM_CLOSE
* Volume: Core Audio IAudioEndpointVolume (via pycaw), keybd_event fallback
* Media: virtual media keys (VK_MEDIA_*)
* Power: LockWorkStation, shutdown.exe (never bypasses UAC or sign-in)
* Apps: Get-StartApps (shell:AppsFolder), Start Menu shortcuts, Steam, Epic
"""
from __future__ import annotations

import ctypes
import json
import logging
import os
import subprocess
import threading
import time
from ctypes import wintypes
from pathlib import Path
from typing import Any, Optional

import psutil

from ..base import ActionError
from .base import AppEntry, PlatformBackend, WindowInfo, normalize_name
from .game_libraries import epic_games, steam_games

log = logging.getLogger(__name__)

user32 = ctypes.WinDLL("user32", use_last_error=True)
dwmapi = ctypes.WinDLL("dwmapi")

SW_MINIMIZE, SW_MAXIMIZE, SW_RESTORE = 6, 3, 9
WM_CLOSE = 0x0010
GW_OWNER = 4
GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
DWMWA_CLOAKED = 14
KEYEVENTF_EXTENDEDKEY, KEYEVENTF_KEYUP = 0x1, 0x2
VK_MENU = 0x12
MEDIA_KEYS = {
    "play_pause": 0xB3,
    "next": 0xB0,
    "previous": 0xB1,
    "stop": 0xB2,
    "volume_mute": 0xAD,
    "volume_down": 0xAE,
    "volume_up": 0xAF,
}
CREATE_NO_WINDOW = 0x08000000

EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows.argtypes = [EnumWindowsProc, wintypes.LPARAM]
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsIconic.argtypes = [wintypes.HWND]
user32.IsZoomed.argtypes = [wintypes.HWND]
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.GetForegroundWindow.restype = wintypes.HWND
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
user32.GetWindow.restype = wintypes.HWND
user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.IsWindow.argtypes = [wintypes.HWND]
user32.OpenInputDesktop.restype = wintypes.HANDLE
user32.OpenInputDesktop.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
user32.CloseDesktop.argtypes = [wintypes.HANDLE]
user32.GetUserObjectInformationW.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
                                             ctypes.POINTER(wintypes.DWORD)]


def _run_powershell(script: str, timeout: float = 20.0) -> str:
    exe = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    proc = subprocess.run(
        [str(exe), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
        creationflags=CREATE_NO_WINDOW,
    )
    if proc.returncode != 0:
        raise ActionError(f"PowerShell failed: {proc.stderr.strip()[:300]}")
    return proc.stdout


def _system32(exe: str) -> str:
    return str(Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / exe)


class WindowsBackend(PlatformBackend):
    name = "windows"

    def __init__(self) -> None:
        self._apps: list[AppEntry] = []
        self._apps_at = 0.0
        self._apps_lock = threading.Lock()

    # ------------------------------------------------------------------ apps
    def list_apps(self, refresh: bool = False) -> list[AppEntry]:
        with self._apps_lock:
            if self._apps and not refresh and time.time() - self._apps_at < 600:
                return self._apps
            apps: dict[str, AppEntry] = {}

            def add(entry: AppEntry) -> None:
                key = normalize_name(entry.name)
                if key and (key not in apps or (entry.is_game and not apps[key].is_game)):
                    apps[key] = entry

            # 1) Start Menu shortcuts (desktop apps)
            for root in (
                Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "Microsoft/Windows/Start Menu/Programs",
                Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
            ):
                if root.is_dir():
                    for lnk in root.rglob("*.lnk"):
                        add(AppEntry(name=lnk.stem, target=str(lnk), kind="shortcut"))
            # 2) Get-StartApps covers Store (UWP) apps too
            try:
                raw = _run_powershell(
                    "[Console]::OutputEncoding=[Text.Encoding]::UTF8; Get-StartApps | ConvertTo-Json -Compress"
                )
                data = json.loads(raw) if raw.strip() else []
                if isinstance(data, dict):
                    data = [data]
                for item in data:
                    name, appid = item.get("Name"), item.get("AppID")
                    if name and appid and normalize_name(name) not in apps:
                        add(AppEntry(name=name, target=appid, kind="uwp"))
            except Exception as exc:
                log.warning("Get-StartApps failed: %s", exc)
            # 3) Steam & Epic game libraries
            steam = self._steam_root()
            if steam:
                for g in steam_games(steam):
                    add(g)
            for g in epic_games(Path(os.environ.get("ProgramData", r"C:\ProgramData")) /
                                "Epic/EpicGamesLauncher/Data/Manifests"):
                add(g)
            self._apps = sorted(apps.values(), key=lambda a: a.name.lower())
            self._apps_at = time.time()
            return self._apps

    @staticmethod
    def _steam_root() -> Optional[Path]:
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as k:
                p = Path(winreg.QueryValueEx(k, "SteamPath")[0])
                return p if p.exists() else None
        except OSError:
            return None

    def launch(self, app: AppEntry) -> None:
        if app.kind == "uwp":
            explorer = str(Path(os.environ.get("SystemRoot", r"C:\Windows")) / "explorer.exe")
            subprocess.Popen([explorer, f"shell:AppsFolder\\{app.target}"], creationflags=CREATE_NO_WINDOW)
        else:
            os.startfile(app.target)  # type: ignore[attr-defined]

    def open_uri(self, uri: str) -> None:
        os.startfile(uri)  # type: ignore[attr-defined]

    def open_path(self, path: str) -> None:
        os.startfile(path)  # type: ignore[attr-defined]

    # --------------------------------------------------------------- windows
    def _window_info(self, hwnd: int, fg: int) -> Optional[WindowInfo]:
        length = user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return None
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        try:
            pname = psutil.Process(pid.value).name()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pname = ""
        return WindowInfo(handle=int(hwnd), title=buf.value, process=pname, pid=int(pid.value),
                          minimized=bool(user32.IsIconic(hwnd)), maximized=bool(user32.IsZoomed(hwnd)),
                          foreground=int(hwnd) == fg)

    def list_windows(self) -> list[WindowInfo]:
        handles: list[int] = []

        def cb(hwnd, _lparam):
            if not user32.IsWindowVisible(hwnd) or user32.GetWindow(hwnd, GW_OWNER):
                return True
            if user32.GetWindowLongW(hwnd, GWL_EXSTYLE) & WS_EX_TOOLWINDOW:
                return True
            cloaked = ctypes.c_int(0)
            dwmapi.DwmGetWindowAttribute(wintypes.HWND(hwnd), DWMWA_CLOAKED, ctypes.byref(cloaked),
                                         ctypes.sizeof(cloaked))
            if cloaked.value:
                return True
            handles.append(int(hwnd))
            return True

        user32.EnumWindows(EnumWindowsProc(cb), 0)
        fg = int(user32.GetForegroundWindow() or 0)
        out = []
        for h in handles:
            info = self._window_info(h, fg)
            if info and info.title not in ("Program Manager",):
                out.append(info)
        return out

    def foreground_window(self) -> Optional[WindowInfo]:
        fg = int(user32.GetForegroundWindow() or 0)
        return self._window_info(fg, fg) if fg else None

    def focus_window(self, handle: int) -> bool:
        if not user32.IsWindow(handle):
            raise ActionError("That window no longer exists.")
        if user32.IsIconic(handle):
            user32.ShowWindow(handle, SW_RESTORE)
        # Windows only lets the foreground process change focus; a synthetic Alt
        # press is the documented-compatible way to satisfy that rule.
        user32.keybd_event(VK_MENU, 0, 0, 0)
        user32.SetForegroundWindow(handle)
        user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)
        time.sleep(0.25)
        return int(user32.GetForegroundWindow() or 0) == handle

    def minimize_window(self, handle: int) -> bool:
        user32.ShowWindow(handle, SW_MINIMIZE)
        time.sleep(0.2)
        return bool(user32.IsIconic(handle))

    def maximize_window(self, handle: int) -> bool:
        user32.ShowWindow(handle, SW_MAXIMIZE)
        time.sleep(0.2)
        return bool(user32.IsZoomed(handle))

    def restore_window(self, handle: int) -> bool:
        user32.ShowWindow(handle, SW_RESTORE)
        time.sleep(0.2)
        return not user32.IsIconic(handle)

    def close_process_windows(self, process_name: str, force: bool = False, timeout: float = 8.0) -> int:
        target = process_name.lower()
        pids = {p.pid for p in psutil.process_iter(["name"]) if (p.info["name"] or "").lower() == target}
        if not pids:
            return 0
        for w in self.list_windows():
            if w.pid in pids:
                user32.PostMessageW(w.handle, WM_CLOSE, 0, 0)
        procs = []
        for pid in pids:
            try:
                procs.append(psutil.Process(pid))
            except psutil.NoSuchProcess:
                pass
        gone, alive = psutil.wait_procs(procs, timeout=timeout)
        if alive and force:
            for p in alive:
                try:
                    p.terminate()
                except psutil.Error:
                    pass
            gone2, alive = psutil.wait_procs(alive, timeout=5)
            gone += gone2
        if alive:
            raise ActionError(
                f"{process_name} did not close (it may be asking to save work). {len(alive)} process(es) still running."
            )
        return len(gone)

    # ----------------------------------------------------------------- audio
    def _endpoint(self):
        import comtypes  # type: ignore
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume  # type: ignore

        comtypes.CoInitialize()
        dev = AudioUtilities.GetSpeakers()
        vol = getattr(dev, "EndpointVolume", None)
        if vol is None:
            from ctypes import POINTER, cast

            iface = dev.Activate(IAudioEndpointVolume._iid_, comtypes.CLSCTX_ALL, None)
            vol = cast(iface, POINTER(IAudioEndpointVolume))
        return vol

    def get_volume(self) -> tuple[int, bool]:
        vol = self._endpoint()
        return round(vol.GetMasterVolumeLevelScalar() * 100), bool(vol.GetMute())

    def set_volume(self, level: int) -> None:
        level = max(0, min(100, int(level)))
        try:
            vol = self._endpoint()
            vol.SetMasterVolumeLevelScalar(level / 100.0, None)
            if level > 0 and vol.GetMute():
                vol.SetMute(0, None)
        except ImportError:
            # Fallback: each volume key press moves the system volume by 2%.
            for _ in range(50):
                self._tap(MEDIA_KEYS["volume_down"])
            for _ in range(level // 2):
                self._tap(MEDIA_KEYS["volume_up"])

    def set_mute(self, mute: bool) -> None:
        try:
            self._endpoint().SetMute(1 if mute else 0, None)
        except ImportError:
            self._tap(MEDIA_KEYS["volume_mute"])

    def _tap(self, vk: int) -> None:
        user32.keybd_event(vk, 0, KEYEVENTF_EXTENDEDKEY, 0)
        user32.keybd_event(vk, 0, KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP, 0)

    def media_key(self, command: str) -> None:
        if command not in MEDIA_KEYS:
            raise ActionError(f"Unknown media command {command}")
        self._tap(MEDIA_KEYS[command])

    # ----------------------------------------------------------------- power
    def lock(self) -> None:
        if not user32.LockWorkStation():
            raise ActionError(f"LockWorkStation failed (error {ctypes.get_last_error()})")

    def shutdown(self, delay: int, restart: bool = False) -> None:
        args = [_system32("shutdown.exe"), "/r" if restart else "/s", "/t", str(max(0, int(delay)))]
        proc = subprocess.run(args, capture_output=True, text=True, timeout=15, creationflags=CREATE_NO_WINDOW)
        if proc.returncode != 0:
            raise ActionError(f"shutdown.exe failed: {(proc.stderr or proc.stdout).strip()}")

    def cancel_shutdown(self) -> None:
        proc = subprocess.run([_system32("shutdown.exe"), "/a"], capture_output=True, text=True, timeout=15,
                              creationflags=CREATE_NO_WINDOW)
        if proc.returncode != 0:
            raise ActionError("No scheduled shutdown to cancel.")

    # -------------------------------------------------------------- security
    def is_secure_desktop_active(self) -> bool:
        """True while the UAC prompt, lock screen or Ctrl+Alt+Del screen is shown."""
        DESKTOP_READOBJECTS = 0x0001
        h = user32.OpenInputDesktop(0, False, DESKTOP_READOBJECTS)
        if not h:
            return True
        try:
            buf = ctypes.create_unicode_buffer(256)
            needed = wintypes.DWORD()
            if user32.GetUserObjectInformationW(h, 2, buf, ctypes.sizeof(buf), ctypes.byref(needed)):
                return buf.value.lower() != "default"
            return True
        finally:
            user32.CloseDesktop(h)

    def gpu_info(self) -> list[dict[str, Any]]:
        gpus = super().gpu_info()
        if gpus:
            return gpus
        try:
            raw = _run_powershell(
                "Get-CimInstance Win32_VideoController | Select-Object Name,AdapterRAM,DriverVersion | ConvertTo-Json -Compress",
                timeout=10,
            )
            data = json.loads(raw) if raw.strip() else []
            if isinstance(data, dict):
                data = [data]
            return [{"name": d.get("Name"), "driver": d.get("DriverVersion"),
                     "memory_total_mb": round((d.get("AdapterRAM") or 0) / 1048576) or None} for d in data]
        except Exception:
            return []

    def temperatures(self) -> dict[str, float]:
        temps = super().temperatures()
        try:
            # Requires the WMI ACPI thermal zone provider; many PCs don't expose it
            # without administrator rights. We never elevate to read it.
            raw = _run_powershell(
                "Get-CimInstance -Namespace root/wmi -ClassName MSAcpi_ThermalZoneTemperature -ErrorAction Stop | "
                "Select-Object InstanceName,CurrentTemperature | ConvertTo-Json -Compress",
                timeout=8,
            )
            data = json.loads(raw) if raw.strip() else []
            if isinstance(data, dict):
                data = [data]
            for i, d in enumerate(data):
                k = d.get("CurrentTemperature")
                if k:
                    temps[f"acpi{i}"] = round(k / 10.0 - 273.15, 1)
        except Exception:
            pass
        return temps
