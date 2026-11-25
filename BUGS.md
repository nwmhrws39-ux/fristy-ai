# Known issues & limitations

## Open
1. **Windows code paths not executed on real Windows yet.** The build environment is Linux without a working Wine, so `platform/windows.py`, `screen_analysis/uia.py`, `input_control.py` (SendInput), pycaw volume and keyring/Credential Manager are written against official APIs and covered by fake-platform tests, but have not run on a Windows PC. First thing to do on Windows: follow `docs/TESTING.md` → “Windows validation checklist”.
2. **Bundled Windows Python not smoke-tested.** The `win_amd64` wheel set is resolved with `uv --python-platform windows` and verified to contain Windows binaries; the identical packaged layout was run end-to-end with a Linux CPython 3.12.
3. **App .exe icon is the default Electron icon** (rcedit needs Wine/Windows). Installer, shortcuts and tray use the FRISTY icon. Fix: build on Windows, or set `signAndEditExecutable: true` where rcedit works.
4. **Unsigned installer** → SmartScreen warning.
5. **FRISTY Remote LAN mode has no TLS.** Token-authenticated but sniffable on the LAN. Mitigation: loopback default, warning in UI.
6. **Wake word** uses Whisper tiny on VAD segments: CPU cost while enabled, ~0.5–1.5 s detection latency, possible false positives in noisy rooms.
7. **CPU temperatures** usually unavailable on Windows without vendor tools (by design we never elevate).
8. **Get-StartApps** takes 1–3 s on first app lookup (cached for 10 minutes).
9. `SetForegroundWindow` can be refused by Windows focus-stealing rules; FRISTY reports “Windows did not allow switching” honestly instead of claiming success.

## Fixed during development
- `javascript:` URLs were coerced into `https://javascript:…` and accepted → strict scheme detection (test added).
- Quick local intents swallowed sentences like “start X right now for me” → only confident app matches use the fast path.
- Unknown `<action>` blocks leaked into visible text in the text-tool protocol → all action blocks stripped.
- Hebrew password statements were not detected as sensitive → Hebrew pattern added.
- Packaged backend failed to import (`python -I` ignores `PYTHONPATH`) → `-s` + explicit env; verified with a packaged build.
- Agent report omitted planned-but-not-executed steps → listed as “Not executed”.
- Emergency-stop default `Ctrl+Shift+Esc` collides with Task Manager → `Ctrl+Shift+F12`.
- Backend INFO logs were shown as startup “errors” → only real errors surfaced.
