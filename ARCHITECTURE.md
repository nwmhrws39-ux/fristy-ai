# FRISTY AI — Architecture

```
┌──────────────────────── Electron (desktop/) ────────────────────────┐
│ main process: backend supervisor · tray · global shortcuts ·         │
│               CSP · permission lockdown · compact mode · autostart   │
│ preload: minimal typed bridge (contextIsolation + sandbox)           │
│ renderer (React/TS/Tailwind/Framer Motion):                          │
│   Orb · Chat/Agent · Dashboard · Automations editor · Memory ·       │
│   Action log · Settings · Confirm dialog · mic capture/VAD · TTS     │
└───────────────▲──────────── HTTP + WebSocket (127.0.0.1:<random>) ───┘
                │  Authorization: Bearer <per-session random token>
┌───────────────┴──────────── Python backend (backend/fristy/) ────────┐
│ api/app.py  ── REST routes + /ws event stream, host-header guard     │
│ ai_engine/  ── AIManager (providers, discovery, retries, text-tool   │
│                fallback) · Orchestrator (chat loop, agent mode)      │
│ computer_control/ ── ActionRegistry · ActionEngine · Confirmation-   │
│                Broker · platform backends (windows / generic) ·      │
│                InputController                                       │
│ screen_analysis/ · files/ · coding/ · memory/ · automations/ ·       │
│ integrations/ (clients + Remote server) · voice_engine/ · security/  │
│ core/ ── SQLite DB + migrations · settings · event bus · metrics     │
└──────────────────────────────────────────────────────────────────────┘
```

## Process model
- Electron main picks a free loopback port, generates a 256-bit token and spawns the backend (`python -m fristy.main`) with `FRISTY_PORT`, `FRISTY_TOKEN`, `FRISTY_DATA_DIR`. It polls `/health`, restarts the backend up to 3 times on crash and reports status to the UI.
- In the installer, Python is a bundled standalone CPython 3.12 (`resources/python`) and the backend package lives in `resources/backend`. No system Python is used (`-s`, `PYTHONNOUSERSITE`, `PYTHONPATH` override).
- The backend binds **only** to `127.0.0.1`. Every route except `/health` needs the bearer token; the WebSocket needs it as a query parameter. A Host-header guard defeats DNS-rebinding.

## The action pipeline (`computer_control/engine.py`)
Every action — from the UI, chat model, agent, automation, voice or FRISTY Remote — goes through `ActionEngine.execute`:
1. **Lookup** in the registry (unknown names rejected). The AI only sees actions whose permission is enabled.
2. **Validate** arguments with the action's pydantic model (types, ranges, URL schemes…).
3. **Permission** category check (`screen_view`, `mouse_control`, `keyboard_control`, `file_access`, `app_launch`, `system_control`, `terminal_exec`, `power_management`, `network_access`).
4. **Platform** check (Windows-only actions fail honestly elsewhere).
5. **Confirmation** policy: `HIGH` risk always; `MEDIUM` when the source is agent/automation/remote or after untrusted content was read; per-action rules (`confirm="always"` for clicks/typing/code writes/terminal, `confirm_if` for overwrites or sending a screenshot to a cloud model). The broker fails closed (no UI or timeout ⇒ denied). Previews (diffs, organize plans, commands) are shown in the dialog.
6. **Execute** in a worker thread with a timeout; emergency stop cancels the task.
7. **Verify**: handlers return `verified=True/False/None` (e.g. read volume back, check window appeared, file content matches, screen changed after click).
8. **Audit**: every rejection, confirmation decision, result and timing is written to `audit_log` (secrets redacted).

## AI engine
- Provider-neutral `Message/ToolCall/ToolDef/StreamEvent` types; each provider converts to its wire format (Ollama NDJSON, OpenAI SSE with fragmented tool calls, Anthropic SSE content blocks incl. images in tool results, Gemini SSE with thought-signature round-tripping).
- `AIManager.stream`: native tool calling when supported, automatic fallback to an `<action>{json}</action>` text protocol for models without tools, retry with backoff for transient errors, latency metrics.
- **Chat mode**: tool loop limited to `chat_max_tool_calls`; results fed back as JSON; screenshots attached as images only if the model has vision.
- **Agent mode**: (1) planner prompt → JSON plan, (2) each step validated by the engine, (3) user approves the plan (pre-approves its MEDIUM actions; HIGH still confirmed individually), (4) execution loop with max steps, max duration, max failures, pause/resume/stop, (5) deterministic execution report built from real results, including steps that were planned but not executed.
- Honesty guard: if the model's text claims an action but nothing succeeded, the UI shows a warning.
- Untrusted content (files, screen/UI Automation text, command output) is wrapped in `<<<UNTRUSTED_CONTENT>>>` fences (forged markers neutralised) and escalates confirmation requirements for the rest of the run.
- Fast local intents (`ai_engine/quick.py`) handle simple whole-utterance commands in English/Hebrew without an AI round-trip; custom command phrases are matched before that.

## Data
SQLite (`%APPDATA%\FRISTY AI\fristy.db`, WAL): `settings`, `conversations`, `messages`, `memories`, `usage_stats`, `automations`, `audit_log`, `remote_devices`, `metrics`. API keys and integration tokens live in Windows Credential Manager via `keyring` (memory-only fallback, never plaintext on disk). File edits are backed up to `backups/<timestamp>/`.

## Voice
Renderer captures the mic (selected device) with Web Audio, downsamples to 16 kHz mono and encodes WAV. Push-to-talk auto-stops on silence. Wake word: an energy VAD cuts short speech segments, which the backend transcribes locally with Whisper `tiny` and fuzzy-matches against “Hey Fristy”/“היי פריסטי” (+ common mis-hearings). Commands spoken after the wake phrase in the same breath are executed directly. TTS uses Windows voices via `speechSynthesis` (language picked per answer) or OpenAI TTS; `Esc`/emergency stop interrupts.

## Screen understanding
`ScreenCapture.privacy_check` refuses secure desktops (UAC/lock), credential/password-manager/banking windows and focused password fields. UI Automation (on a dedicated COM thread) lists named elements with ids/bounding boxes and can Invoke/Toggle/SetValue without moving the mouse; vision-model coordinate location is the fallback. A visible “Screen analysis active” indicator is shown during capture.

## Integrations
Clients for FRISTY Launcher / PC Manager / Cleaner speak a documented local REST contract (`docs/INTEGRATIONS.md`), only to loopback hosts, with per-app tokens from the credential store. FRISTY Remote is a separate listener (off by default, loopback unless LAN is enabled) with 6-digit one-time pairing, hashed device tokens, rate limiting, and all commands routed through the same orchestrator/engine with `source="remote"` (so approvals happen on the PC).
