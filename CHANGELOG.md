# Changelog

## Unreleased
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
