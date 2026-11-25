# Changelog

## 0.2.3 — 2026-11-25
- Smart app lookup: “close epic games” / “epicgames” / “אפיק גיימס” finds EpicGamesLauncher.exe (process name, window title, install folder, fuzzy). Asks when ambiguous; never touches Windows system processes.
- Closes tray/background apps via their hidden windows; “force close …” / “סגור בכוח …” when an app refuses.
- The AI sees the list of open apps on every request and has a new list_running_apps tool; open/switch matching ignores spaces.

## 0.2.2 — 2026-11-25
- Installer size fix: the Windows build accidentally packed the whole repository into app.asar (npm --prefix linked the workspace root). Build now refuses oversized app.asar.

## 0.2.1 — 2026-11-25
- Much smaller installer (maximum compression).
- Fix: model download reported “done” before the new model was selected.

## 0.2.0 — 2026-11-25
- **Update button**: checks GitHub Releases, downloads the installer, verifies SHA-256, installs silently and restarts FRISTY. Automatic check at startup.
- **Full computer access** mode (all permissions + user folder + close any app) with a relaxed approval level; destructive actions (delete, shutdown/restart, terminal, closing apps) still ask.
- **Better Hebrew**: Hebrew-language directive written in Hebrew, Hebrew replies for fast commands, agent reports and plans in Hebrew, Hebrew quality rating per model (Gemma 3 12B, Aya Expanse 8B added), Whisper large-v3-turbo for Hebrew speech.
- **More reliable computer control with local models**: only relevant tools are offered per request; many more instant commands in Hebrew/English (volume up/down, close/switch/minimize/maximize, Google/YouTube search, system status, shutdown/restart).
- One-click local AI models: curated catalog with RAM-based recommendation, download progress (banner, settings, title bar), cancel, delete, auto-select; “Ollama not running” guidance.
- `npm run dist` builds the Windows EXE on Windows (rcedit icon, no admin) and Linux (NSIS, no Wine).

## 0.1.0 — 2026-11-25
First complete version.
- Backend: FastAPI on loopback with token auth; SQLite storage; settings; event bus; audit log; OS credential storage.
- AI: Ollama, OpenAI, Anthropic, Gemini, custom OpenAI-compatible; discovery; streaming; tool calling with text fallback; vision; chat and agent modes; honest execution reports.
- 55+ actions: apps/games/websites, windows, volume/media, power, files, screen/UI Automation/vision, mouse/keyboard, coding/terminal, memory, automations, FRISTY integrations.
- Voice: local Whisper STT, local wake word, Windows/OpenAI TTS, push-to-talk, continuous conversation.
- Desktop: JARVIS-style UI (orb, waveform, glassmorphism), compact mode, Hebrew/RTL, dashboard, automation editor, memory manager, action log, full settings.
- Security: 9 permissions, confirmations with previews, emergency stop, untrusted-content handling, sandboxed file access, CSP.
- Windows installer with bundled Python runtime.
