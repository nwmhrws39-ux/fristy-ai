"""OpenCV helpers: resizing for vision models, change detection, template matching."""
from __future__ import annotations

import base64
from typing import Optional

import numpy as np

try:
    import cv2
except ImportError:  # pragma: no cover
    cv2 = None


def _require() -> None:
    if cv2 is None:
        raise RuntimeError("OpenCV is not installed")


def bgra_to_bgr(img: np.ndarray) -> np.ndarray:
    return img[:, :, :3].copy() if img.ndim == 3 and img.shape[2] == 4 else img


def downscale(img: np.ndarray, max_width: int = 1600) -> tuple[np.ndarray, float]:
    """Return resized image and the factor to multiply model coords by to get screen coords."""
    _require()
    h, w = img.shape[:2]
    if w <= max_width:
        return img, 1.0
    scale = max_width / w
    small = cv2.resize(img, (max_width, int(h * scale)), interpolation=cv2.INTER_AREA)
    return small, 1.0 / scale


def encode_png(img: np.ndarray) -> bytes:
    _require()
    ok, buf = cv2.imencode(".png", img)
    if not ok:
        raise RuntimeError("PNG encoding failed")
    return buf.tobytes()


def encode_jpeg_b64(img: np.ndarray, quality: int = 85) -> str:
    _require()
    ok, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    if not ok:
        raise RuntimeError("JPEG encoding failed")
    return base64.b64encode(buf.tobytes()).decode()


def change_ratio(before: np.ndarray, after: np.ndarray, pixel_threshold: int = 25) -> float:
    """Fraction of pixels that changed noticeably between two screenshots."""
    _require()
    if before.shape != after.shape:
        return 1.0
    a = cv2.cvtColor(bgra_to_bgr(before), cv2.COLOR_BGR2GRAY)
    b = cv2.cvtColor(bgra_to_bgr(after), cv2.COLOR_BGR2GRAY)
    a = cv2.resize(a, (a.shape[1] // 4 or 1, a.shape[0] // 4 or 1))
    b = cv2.resize(b, (b.shape[1] // 4 or 1, b.shape[0] // 4 or 1))
    diff = cv2.absdiff(a, b)
    return float(np.count_nonzero(diff > pixel_threshold)) / diff.size


def find_template(screen: np.ndarray, template: np.ndarray, threshold: float = 0.85) -> Optional[tuple[int, int, float]]:
    """Locate ``template`` in ``screen``; returns centre (x, y) and score, or None."""
    _require()
    s = cv2.cvtColor(bgra_to_bgr(screen), cv2.COLOR_BGR2GRAY)
    t = cv2.cvtColor(bgra_to_bgr(template), cv2.COLOR_BGR2GRAY)
    if t.shape[0] > s.shape[0] or t.shape[1] > s.shape[1]:
        return None
    res = cv2.matchTemplate(s, t, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(res)
    if max_val < threshold:
        return None
    return max_loc[0] + t.shape[1] // 2, max_loc[1] + t.shape[0] // 2, float(max_val)
