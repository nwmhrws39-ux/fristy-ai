# Security model

| Threat | Mitigation |
|---|---|
| Other local processes / web pages driving FRISTY | Backend on 127.0.0.1 only; random per-session 256-bit bearer token (HTTP + WS); Host-header allow-list (DNS rebinding); CORS limited to the app origins. |
| Remote control exposure | FRISTY Remote off by default, separate listener, loopback unless “allow LAN” is enabled; one-time 6-digit pairing code (5 min, 5 attempts); device tokens stored as SHA-256 hashes, revocable; rate limiting; every command goes through the action engine with confirmation on the PC. |
| AI executing arbitrary actions | Only registered, schema-validated actions; no generic “run anything” tool. Terminal commands: dedicated permission, always confirmed, denylist (format, diskpart, bcdedit, registry edits, Defender/firewall changes, encoded PowerShell, download-and-execute, `runas`, user management…), cwd restricted to approved folders, secrets removed from the environment, timeout, output limits. |
| Prompt injection from files/web/screen | Untrusted content fenced and labelled; system prompt forbids following it; once read, every state-changing action needs explicit confirmation (tested). |
| Destructive file operations | Approved-folder sandbox (symlink-escape safe, protected system names); delete = Recycle Bin + confirmation; overwrite = confirmation + old file to Recycle Bin; code edits show a diff and are backed up. |
| Typing into the wrong place | No input on secure desktops, credential apps, password fields; typing into shells/Run dialog requires terminal permission; Win+R / Win+X / Ctrl+Alt+Del / Task Manager combos blocked; clicks and typing always confirmed; PyAutoGUI fail-safe; emergency stop interrupts typing. |
| UAC / authentication bypass | Never attempted: no elevation, no credential handling, lock/shutdown via official APIs only, installer is per-user without admin. |
| Secrets leakage | API keys in Windows Credential Manager; never in settings DB, logs or memory; sensitive-data detector rejects passwords/keys/cards from memory; audit details redacted. |
| Cloud data disclosure | Title bar badge shows Local vs Cloud provider; sending a screenshot to a cloud model requires confirmation stating so; voice wake word never leaves the PC. |
| Renderer compromise | contextIsolation, sandbox, no nodeIntegration, strict CSP (no remote scripts/connections except the local backend), navigation and window.open blocked, only microphone permission granted, external links via validated `shell.openExternal`. |
| Runaway agents | Max steps (≤25), max duration, max failures, plan approval, pause/stop, global emergency stop, all runs cancellable. |

All permissions except application launching, system control (volume/windows/media) and network access (opening websites, local FRISTY app integrations) are **off by default**.

Known gaps are tracked in `BUGS.md` (e.g. Remote LAN mode has no TLS; installer unsigned).
