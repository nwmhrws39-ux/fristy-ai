# FRISTY AI – Task checklist

Legend: [x] done and tested here · [~] implemented, needs validation on real Windows hardware · [ ] not done

## Phase 1 – Interface, chat, AI
- [x] Electron shell: frameless window, custom title bar, tray, single instance, compact floating mode
- [x] React UI: orb with 6 states, waveform, glassmorphism, Framer Motion transitions, accent colors
- [x] Hebrew/English UI with RTL; per-message direction detection
- [x] Ollama provider (discovery w/ capabilities, streaming, tools, vision)
- [x] OpenAI / custom OpenAI-compatible provider (streaming, fragmented tool calls, vision, temperature fallback)
- [x] Anthropic provider (SSE content blocks, tool_use, images in tool results)
- [x] Gemini provider (SSE, function calling, thought signatures)
- [x] Text-protocol tool fallback for models without native tools; retries; latency metrics
- [x] Conversation history, search, summaries into memory
- [x] Honesty guard (claims without executed actions flagged)

## Phase 2 – Voice
- [x] Mic capture + selection, 16 kHz WAV, push-to-talk with silence auto-stop, mic kill switch
- [x] Local Whisper STT (faster-whisper) + optional OpenAI STT; Hebrew/English/auto
- [x] Local wake word “Hey Fristy” / “היי פריסטי” (VAD + Whisper tiny + fuzzy matching)
- [x] TTS: Windows voices (speechSynthesis) or OpenAI; rate, voice selection, interrupt; continuous conversation
- [~] Real-microphone/Whisper accuracy validation (model download blocked in build sandbox)

## Phase 3 – Computer control
- [~] App discovery (Start Menu, Get-StartApps/UWP, Steam, Epic) + fuzzy/alias launch with verification
- [x] Websites (http/https only), system info, file search
- [~] Window list/switch/minimize/maximize, close approved apps (graceful → optional force)
- [~] Master volume/mute via Core Audio (pycaw) with read-back verification; media keys
- [~] Screenshot, lock, restart/shutdown/cancel via official APIs
- [x] Restricted action engine: registry, validation, permissions, confirmations, timeouts, audit

## Phase 4 – Screen, input, agent
- [x] Privacy guard (secure desktop, credential apps, password fields), activity indicator
- [~] UI Automation element listing / invoke / set value on a COM thread
- [x] Vision-model coordinate fallback; OpenCV change detection & template matching
- [~] Mouse click/scroll, keyboard typing (incl. Hebrew via SendInput), key combos with blocklist
- [x] Agent mode: plan → validate → approve → execute → verify → report; pause/stop/limits; injection defense

## Phase 5 – Memory, automations, integrations
- [x] Local memory: CRUD, categories, export/import, sensitive-data rejection, auto-learn statements, usage stats
- [x] Automations: phrase/schedule/manual/startup triggers, conditions, steps, confirm-once, visual editor, templates
- [x] FRISTY Launcher / PC Manager / Cleaner clients (documented contract) + built-in performance monitor
- [x] FRISTY Remote: pairing, hashed tokens, rate limiting, separate listener
- [x] Coding assistant: diffs, backups, project scaffolding, VS Code, restricted terminal

## Phase 6 – Security, tests, installer
- [x] Security review items in docs/SECURITY.md implemented and tested
- [x] 183 backend tests (Python 3.12 and 3.13), 9 frontend tests, browser + Electron E2E (dev and packaged)
- [x] Windows installer (NSIS, per-user, bundled CPython 3.12 + win_amd64 wheels)
- [ ] Code signing (needs a certificate)
- [ ] Validation pass on real Windows 10 and 11 machines
