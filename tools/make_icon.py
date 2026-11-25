"""Generates the FRISTY orb icon (PNG + multi-size ICO)."""
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

out = Path(sys.argv[1] if len(sys.argv) > 1 else "desktop/build")
out.mkdir(parents=True, exist_ok=True)
S = 1024
y, x = np.mgrid[0:S, 0:S].astype(np.float32)
cx = cy = S / 2
d = np.sqrt((x - cx) ** 2 + (y - cy) ** 2) / (S / 2)
img = np.zeros((S, S, 4), np.float32)
# background rounded square
bg = np.array([6, 3, 10], np.float32)
img[..., :3] = bg
margin = 0.06 * S
r = 0.22 * S
qx = np.maximum(np.abs(x - cx) - (S / 2 - margin - r), 0)
qy = np.maximum(np.abs(y - cy) - (S / 2 - margin - r), 0)
inside = np.sqrt(qx ** 2 + qy ** 2) <= r
img[..., 3] = inside * 255
accent = np.array([168, 85, 247], np.float32)
glow = np.clip(1 - d / 0.95, 0, 1) ** 2.2
img[..., :3] += glow[..., None] * accent * 0.55
# ring
ring = np.exp(-((d - 0.72) ** 2) / 0.0006)
img[..., :3] += ring[..., None] * np.array([216, 180, 254]) * 0.9
# sphere
sd = np.sqrt((x - cx) ** 2 + (y - cy) ** 2) / (S * 0.27)
sphere = sd <= 1
hx, hy = cx - 0.1 * S, cy - 0.12 * S
hl = np.clip(1 - np.sqrt((x - hx) ** 2 + (y - hy) ** 2) / (S * 0.2), 0, 1)
col = accent * (1 - 0.55 * sd[..., None] ** 2) + hl[..., None] ** 1.5 * np.array([255, 255, 255]) * 0.9
img[..., :3] = np.where(sphere[..., None], col, img[..., :3])
img[..., :3] = np.clip(img[..., :3], 0, 255)
im = Image.fromarray(img.astype(np.uint8), "RGBA")
im.filter(ImageFilter.SMOOTH)
im.resize((512, 512), Image.LANCZOS).save(out / "icon.png")
im.resize((256, 256), Image.LANCZOS).save(out / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("icons written to", out)
