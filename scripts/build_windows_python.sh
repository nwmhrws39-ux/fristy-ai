#!/usr/bin/env bash
# Builds a self-contained Windows x64 Python runtime with all backend
# dependencies into vendor/python. Runs on Linux or Windows (Git Bash).
#   1. downloads python-build-standalone CPython (Windows, install_only)
#   2. installs win_amd64 wheels into its site-packages (cross-platform pip)
#   3. builds wheels for pure-Python sdist-only packages locally
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY_VER="${PY_VER:-3.12.8}"
PBS_TAG="${PBS_TAG:-20241206}"
URL="https://github.com/astral-sh/python-build-standalone/releases/download/${PBS_TAG}/cpython-${PY_VER}+${PBS_TAG}-x86_64-pc-windows-msvc-install_only.tar.gz"
VENDOR="$ROOT/vendor"
OUT="$VENDOR/python"
CACHE="$VENDOR/cache"
if [ -z "${HOSTPY:-}" ]; then
  if [ -x "$ROOT/.venv/Scripts/python.exe" ]; then HOSTPY="$ROOT/.venv/Scripts/python.exe"; else HOSTPY="$ROOT/.venv/bin/python"; fi
fi
"$HOSTPY" -m pip install -q uv wheel
mkdir -p "$CACHE"

TARBALL="$CACHE/$(basename "$URL" | sed 's/+/_/')"
if [ ! -f "$TARBALL" ]; then
  echo ">> downloading Windows CPython $PY_VER"
  curl -fL --retry 4 -o "$TARBALL.part" "$URL"
  mv "$TARBALL.part" "$TARBALL"
fi
rm -rf "$OUT" && mkdir -p "$VENDOR/extract"
tar -xzf "$TARBALL" -C "$VENDOR/extract"
mv "$VENDOR/extract/python" "$OUT" && rmdir "$VENDOR/extract"
test -f "$OUT/python.exe"

SITE="$OUT/Lib/site-packages"
PYV="$(echo "$PY_VER" | cut -d. -f1,2)"

echo ">> building wheels for pure-Python sdist-only packages"
WHEELS="$CACHE/purewheels"
mkdir -p "$WHEELS"
"$HOSTPY" -m pip wheel --no-deps -q -w "$WHEELS" \
  pyautogui pymsgbox pytweening pyscreeze pygetwindow pyrect mouseinfo pyperclip

echo ">> resolving + installing win_amd64 wheels into $SITE (uv, target=windows)"
UV="${UV:-$(dirname "$HOSTPY")/uv}"
"$UV" pip install --quiet --python-platform x86_64-pc-windows-msvc --python-version "$PYV" \
  --only-binary :all: --find-links "$WHEELS" --target "$SITE" --no-cache \
  -r "$ROOT/backend/requirements.txt"

echo ">> trimming"
find "$OUT" -name "__pycache__" -type d -prune -exec rm -rf {} +
rm -rf "$OUT/Lib/test" "$OUT/Lib/idlelib" "$OUT/Lib/tkinter" "$OUT/tcl" "$OUT/Lib/ensurepip" "$OUT/include"
rm -rf "$SITE"/*/tests "$SITE/cv2/data" 2>/dev/null || true
du -sh "$OUT"
echo ">> done: $OUT"
