"""Mouse and keyboard control via PyAutoGUI, with safety guards.

Guards applied to every call:
* PyAutoGUI fail-safe (slam the mouse into a screen corner to abort)
* the FRISTY emergency stop interrupts long typing loops
* secure desktops (UAC / lock screen) are never automated
* no typing into password fields or credential apps
* typing into shells / the Run dialog additionally needs terminal permission
"""
from __future__ import annotations

import time
from typing import Optional

from ..screen_analysis.privacy import window_executes_commands, window_is_sensitive
from .base import ActionError

BLOCKED_COMBOS = {
    frozenset({"ctrl", "alt", "delete"}),
    frozenset({"ctrl", "alt", "del"}),
    frozenset({"win", "r"}),  # Run dialog = arbitrary command execution
    frozenset({"win", "x"}),  # power-user menu (terminal as admin)
    frozenset({"ctrl", "shift", "escape"}),  # Task Manager
}
KEY_ALIASES = {"control": "ctrl", "windows": "win", "super": "win", "cmd": "win", "return": "enter",
               "escape": "esc", "del": "delete", "pgup": "pageup", "pgdn": "pagedown"}


def normalize_keys(keys: list[str]) -> list[str]:
    return [KEY_ALIASES.get(k.strip().lower(), k.strip().lower()) for k in keys if k.strip()]


class InputController:
    def __init__(self, platform, settings_store, stop, uia=None):
        self.platform = platform
        self.settings = settings_store
        self.stop = stop
        self.uia = uia
        self._pg = None

    @property
    def pg(self):
        if self._pg is None:
            try:
                import pyautogui  # type: ignore
            except Exception as exc:
                raise ActionError(f"Mouse/keyboard automation unavailable: {exc}", "unsupported_platform") from exc
            pyautogui.FAILSAFE = True
            pyautogui.PAUSE = 0.05
            self._pg = pyautogui
        return self._pg

    def _guard(self, typing: bool = False) -> None:
        if self.platform.is_secure_desktop_active():
            raise ActionError("A secure Windows screen is active; input automation refused.", "secure_screen")
        fg = self.platform.foreground_window()
        if fg:
            reason = window_is_sensitive(fg.process, fg.title)
            if reason:
                raise ActionError(f"Input refused because {reason}.", "sensitive_screen")
            if typing and window_executes_commands(fg.process, fg.title):
                if not self.settings.current.permissions.get("terminal_exec"):
                    raise ActionError(
                        "The focused window runs commands (terminal/Run dialog). Typing there requires the "
                        "terminal execution permission.", "permission_denied")
        if typing and self.uia is not None:
            try:
                if self.uia.focused_is_password():
                    raise ActionError("Refusing to type into a password field.", "sensitive_field")
            except ActionError:
                raise
            except Exception:
                pass

    def screen_size(self) -> tuple[int, int]:
        w, h = self.pg.size()
        return int(w), int(h)

    def click(self, x: int, y: int, button: str = "left", clicks: int = 1) -> None:
        self._guard()
        w, h = self.screen_size()
        if not (0 <= x < w and 0 <= y < h):
            raise ActionError(f"Point ({x}, {y}) is outside the screen ({w}x{h}).", "out_of_bounds")
        self.pg.click(x=x, y=y, button=button, clicks=clicks, interval=0.1)

    def move(self, x: int, y: int) -> None:
        self._guard()
        self.pg.moveTo(x, y, duration=0.2)

    def scroll(self, amount: int, x: Optional[int] = None, y: Optional[int] = None) -> None:
        self._guard()
        self.pg.scroll(int(amount), x=x, y=y)

    def type_text(self, text: str, interval: float = 0.01) -> int:
        self._guard(typing=True)
        typed = 0
        # Chunked so emergency stop can interrupt long text.
        for i in range(0, len(text), 20):
            if self.stop.stopped_recently(window=5):
                raise ActionError("Typing interrupted by emergency stop.", "stopped")
            chunk = text[i:i + 20]
            if chunk.isascii():
                self.pg.write(chunk, interval=interval)
            else:
                self._paste_unicode(chunk)
            typed += len(chunk)
        return typed

    def _paste_unicode(self, chunk: str) -> None:
        """PyAutoGUI can't type non-ASCII (e.g. Hebrew); send Unicode via SendInput on Windows."""
        import sys

        if sys.platform != "win32":
            raise ActionError("Typing non-ASCII text is only supported on Windows.", "unsupported_platform")
        import ctypes
        from ctypes import wintypes

        KEYEVENTF_UNICODE, KEYEVENTF_KEYUP = 0x0004, 0x0002

        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                        ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]

        class INPUT(ctypes.Structure):
            class _U(ctypes.Union):
                _fields_ = [("ki", KEYBDINPUT), ("pad", ctypes.c_byte * 32)]
            _anonymous_ = ("u",)
            _fields_ = [("type", wintypes.DWORD), ("u", _U)]

        for ch in chunk:
            code = ord(ch)
            units = [code] if code <= 0xFFFF else [0xD800 + ((code - 0x10000) >> 10), 0xDC00 + ((code - 0x10000) & 0x3FF)]
            for u in units:
                for flags in (KEYEVENTF_UNICODE, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP):
                    inp = INPUT(type=1)
                    inp.ki = KEYBDINPUT(0, u, flags, 0, 0)
                    ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
            time.sleep(0.005)

    def press(self, keys: list[str]) -> None:
        keys = normalize_keys(keys)
        if not keys:
            raise ActionError("No keys given.")
        if frozenset(keys) in BLOCKED_COMBOS:
            raise ActionError(f"The key combination {'+'.join(keys)} is blocked for safety.", "blocked_combo")
        self._guard(typing=True)
        valid = set(self.pg.KEYBOARD_KEYS)
        bad = [k for k in keys if k not in valid]
        if bad:
            raise ActionError(f"Unknown key(s): {', '.join(bad)}")
        if len(keys) == 1:
            self.pg.press(keys[0])
        else:
            self.pg.hotkey(*keys)
