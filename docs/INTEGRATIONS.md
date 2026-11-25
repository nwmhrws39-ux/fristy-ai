# FRISTY app integration contract (v1)

FRISTY AI talks to the other FRISTY apps over HTTP on **127.0.0.1 only**. Each app generates an access token that the user copies into *FRISTY AI → Settings → Integrations* (stored in Windows Credential Manager). Every request carries `Authorization: Bearer <token>`; apps must reject anything else with `401`. All integrations are optional.

Default ports: Launcher `47801`, PC Manager `47802`, Cleaner `47803` (configurable).

## Common
`GET /api/v1/status` → `200 {"app": "fristy-launcher", "version": "1.2.0"}` (used for the “Connected” indicator).

## FRISTY Launcher
- `GET /api/v1/games?query=<text>` → `[{"id": "g1", "name": "Valorant", "installed": true, "playtime_minutes": 600, "last_played": 1732400000}]`
- `POST /api/v1/games/{id}/launch` → `{"ok": true, "running": true}`
FRISTY actions: `fristy_launcher_games`, `fristy_launcher_launch`, `fristy_launcher_playtime`.

## FRISTY PC Manager
- `GET /api/v1/metrics` → `{"cpu_percent": 12.5, "gpu_percent": 30, "cpu_temp_c": 55, "gpu_temp_c": 61, "ram_percent": 48, "warnings": ["…"]}`
FRISTY action: `pc_performance` (falls back to FRISTY AI's built-in monitor when PC Manager is unavailable).

## FRISTY Cleaner
- `POST /api/v1/scan {"kind": "storage" | "duplicates" | "large_files"}` → `{"scan_id": "s1", "items": [{"id": "i1", "path": "…", "bytes": 1234, "recommended": true}], "total_bytes": 1234}`
- `POST /api/v1/clean {"scan_id": "s1", "item_ids": ["i1"]}` → `{"ok": true, "freed_bytes": 1234}` — FRISTY AI always asks the user before calling this; Cleaner should move items to the Recycle Bin.
FRISTY actions: `fristy_cleaner_scan`, `fristy_cleaner_clean` (HIGH risk).

## FRISTY Remote (mobile app → FRISTY AI)
Enable in *Settings → Integrations → FRISTY Remote* (port `47810`).
1. User clicks **Pair a device** on the PC → 6-digit code (valid 5 min).
2. `POST /api/v1/pair {"code": "123456", "device_name": "Pixel 9"}` → `{"device_id": "…", "token": "…"}` (store the token securely on the phone).
3. `GET /api/v1/status` (Bearer token) → `{"ok": true, "device": "Pixel 9", "metrics": {…}, "ai": {"provider": "ollama", "model": "…"}, "active_runs": 0}`
4. `POST /api/v1/command {"text": "open discord", "mode": "chat" | "agent"}` → `{"run_id": "…", "conversation_id": "…"}`. Risky actions wait for approval on the PC.
Limits: 30 requests/minute/device; pairing 10 attempts/minute/IP and 5 per code.
