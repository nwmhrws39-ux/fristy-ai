"""Screenshot capture with privacy enforcement and a visible activity signal."""
from __future__ import annotations

import base64
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np

from ..computer_control.base import ActionError
from . import cv_utils
from .privacy import window_is_sensitive


@dataclass
class Capture:
    image: np.ndarray  # BGR, full resolution
    width: int
    height: int
    left: int
    top: int
    taken_at: float

    def for_model(self, max_width: int = 1600) -> tuple[str, float]:
        small, factor = cv_utils.downscale(self.image, max_width)
        return cv_utils.encode_jpeg_b64(small), factor


class ScreenCapture:
    def __init__(self, platform, settings_store, bus=None, uia=None):
        self.platform = platform
        self.settings = settings_store
        self.bus = bus
        self.uia = uia

    def privacy_check(self) -> None:
        if not self.settings.current.permissions.get("screen_view"):
            raise ActionError("Screen viewing permission is disabled.", "permission_denied")
        if self.platform.is_secure_desktop_active():
            raise ActionError("A secure Windows screen (UAC, lock or sign-in) is active; capture refused.",
                              "secure_screen")
        fg = self.platform.foreground_window()
        if fg:
            reason = window_is_sensitive(fg.process, fg.title)
            if reason:
                raise ActionError(f"Screen capture refused because {reason}.", "sensitive_screen")
        if self.uia is not None:
            try:
                if self.uia.focused_is_password():
                    raise ActionError("Screen capture refused because a password field is focused.",
                                      "sensitive_screen")
            except ActionError:
                raise
            except Exception:
                pass

    def capture(self, monitor: int = 1, reason: str = "") -> Capture:
        self.privacy_check()
        try:
            import mss
        except ImportError as exc:  # pragma: no cover
            raise ActionError("Screen capture library (mss) is not installed.") from exc
        if self.bus:
            self.bus.publish("screen.capture", active=True, reason=reason)
        try:
            with mss.mss() as sct:
                monitors = sct.monitors
                if monitor < 1 or monitor >= len(monitors):
                    monitor = 1
                mon = monitors[monitor]
                shot = sct.grab(mon)
                img = np.asarray(shot)[:, :, :3].copy()
        except ActionError:
            raise
        except Exception as exc:
            raise ActionError(f"Screen capture failed: {exc}", "capture_failed") from exc
        finally:
            if self.bus:
                self.bus.publish("screen.capture", active=False, reason=reason)
        return Capture(image=img, width=img.shape[1], height=img.shape[0], left=mon["left"], top=mon["top"],
                       taken_at=time.time())

    def save(self, cap: Capture, directory: Path) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / time.strftime("screenshot-%Y%m%d-%H%M%S.png")
        path.write_bytes(cv_utils.encode_png(cap.image))
        return path

    @staticmethod
    def png_b64(cap: Capture) -> str:
        return base64.b64encode(cv_utils.encode_png(cap.image)).decode()

    def grab_quiet(self) -> Optional[np.ndarray]:
        """Capture for verification (e.g. did the click change anything); never raises."""
        try:
            return self.capture(reason="verification").image
        except Exception:
            return None
