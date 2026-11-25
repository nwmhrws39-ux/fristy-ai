# Next steps

1. Run the Windows validation checklist (`docs/TESTING.md`) on Windows 10 and Windows 11; fix any API issues found in `platform/windows.py`, `uia.py`, `input_control.py`.
2. Measure Whisper `small` vs `base` Hebrew accuracy/latency on typical CPUs; tune VAD thresholds for the wake word.
3. Code-sign installer and app; set the exe icon (build on Windows).
4. Optional dedicated keyword-spotting model for the wake word (lower CPU than Whisper tiny).
5. TLS (self-signed + certificate pinning during pairing) for FRISTY Remote LAN mode.
6. Implement the server side of the integration contract in FRISTY Launcher / PC Manager / Cleaner / Remote.
7. Auto-update channel (electron-updater) once signing is in place.
8. More UI tests (Playwright E2E in CI with the mock Ollama server).
