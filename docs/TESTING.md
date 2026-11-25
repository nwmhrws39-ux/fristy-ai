# Testing

## Automated results (2026-11-25, Linux build environment)
| Suite | Command | Result |
|---|---|---|
| Backend unit + integration (Python 3.13) | `.venv/bin/python -m pytest -q` | **182 passed** |
| Backend on Python 3.12 (bundled version) | same, with a 3.12 venv | **182 passed** |
| Frontend unit (vitest/jsdom) | `cd desktop && npm test` | **9 passed** |
| TypeScript (renderer + Electron) | `npm run typecheck` | clean |
| Static lint (ruff F/E9) | `ruff check backend tools --select F,E9` | clean |
| Browser E2E (Chromium + real backend + mock Ollama) | Playwright | chat streaming, tool card verified, agent plan dialog → approve → file actually created, Hebrew RTL UI; 0 console errors |
| Electron E2E (dev) | Playwright `_electron` under Xvfb | backend spawned on random port, token enforced (401 without), compact mode |
| Electron E2E (packaged layout, `app.isPackaged`) | linux-unpacked with bundled CPython 3.12 | backend ready despite hostile `PYTHONPATH`, tool call verified, CSP blocks external fetch |

What the backend tests cover: action engine (unknown/invalid/permission/platform/confirmation/timeout/cancel/dry-run/audit), every action family against a recording **FakePlatform** (safe environment — nothing touches the real PC), file sandbox (traversal, symlink escape, protected names, recycle bin, overwrite confirmation, organize, duplicates, docx/pdf), security (sensitive-data detection in EN/HE, redaction, untrusted fences, terminal denylist, env scrubbing, blocked key combos, privacy rules), wire formats of all four AI providers (mocked HTTP), text-tool fallback, retries, orchestrator (chat tools, honesty warning, limits, agent plan/approve/deny/report, pause/resume, emergency stop, prompt-injection escalation, learning, history), automations (validation, phrases EN/HE, conditions, schedules, confirm-once, high-risk re-confirmation), API (auth, host guard, WS auth, settings validation, secrets, memory, automations, voice), FRISTY Remote pairing/brute-force/revocation, integrations, Steam/Epic parsers, wake-word matching, WAV handling.

## Windows validation checklist (run on Windows 10 and 11)
Enable permissions as needed in Settings, then verify each and note results in BUGS.md:
1. Install with the Setup .exe (no UAC prompt), launch, backend becomes ready, tray icon present, `Ctrl+Shift+F` toggles window.
2. Settings → AI: Ollama models discovered; send a chat; switch to a cloud provider with a key (title badge turns “Cloud AI”); key appears in Credential Manager (“FRISTY AI”).
3. “open notepad”, “open discord”, “launch <steam game>” → app starts, card shows Verified.
4. “switch to notepad”, “minimize notepad”, “maximize notepad”; “close notepad” (approval dialog).
5. “set volume to 30” → Windows volume slider shows 30; “mute”, “next song”.
6. “take a screenshot” → PNG in `%APPDATA%\FRISTY AI\screenshots`; open a UAC prompt / Windows Security / a password field → capture refused.
7. Screen question with a vision model; “list UI elements”; agent: “click the Save button in Notepad” (approval).
8. Type Hebrew text into Notepad via agent (`type_text`) → correct characters.
9. Push-to-talk in Hebrew and English (first use downloads Whisper); wake word “Hey Fristy”; Esc interrupts speech.
10. Lock / restart (cancel with “cancel shutdown”) / shutdown with delay → approval required.
11. Files: add an approved folder, find/organize/delete (→ Recycle Bin).
12. Terminal: `run_terminal_command` in an approved project (approval + preview); `format c:` refused.
13. Emergency stop shortcut during an agent run → run cancelled, pending approvals denied.
14. Start with Windows toggle → entry under Task Manager → Startup apps; uninstall removes it.
