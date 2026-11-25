#!/usr/bin/env bash
# Builds the Windows installer: desktop/release/FRISTY-AI-Setup-<version>-x64.exe
# Works on Linux (needs: node, python venv with uv, makensis) or Windows (Git Bash + NSIS).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VERSION="$(node -p "require('$ROOT/desktop/package.json').version")"
[ -f "$ROOT/vendor/python/python.exe" ] || bash "$ROOT/scripts/build_windows_python.sh"
cd "$ROOT/desktop"
npm run build
rm -rf release/win-unpacked
npx electron-builder --win dir --x64 --publish never
cd "$ROOT/installer"
makensis -V2 -DVERSION="$VERSION" fristy.nsi
ls -la "$ROOT/desktop/release/"*.exe
