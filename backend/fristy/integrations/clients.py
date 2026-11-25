"""Clients for the FRISTY companion apps' local APIs (see docs/INTEGRATIONS.md for the contract).

All integrations are optional. Each app exposes an HTTP API on 127.0.0.1 and
requires a Bearer token that the user copies from that app into FRISTY AI
(stored in the OS credential store).
"""
from __future__ import annotations

import time
from typing import Any, Optional
from urllib.parse import urlparse

import httpx

from ..computer_control.base import ActionError

APPS = {
    "launcher": "FRISTY Launcher",
    "pc_manager": "FRISTY PC Manager",
    "cleaner": "FRISTY Cleaner",
}


class IntegrationClient:
    def __init__(self, key: str, settings_store, secrets):
        self.key = key
        self.settings = settings_store
        self.secrets = secrets
        self.last_status: dict[str, Any] = {"connected": False, "checked_at": None, "error": None}

    @property
    def cfg(self):
        return getattr(self.settings.current.integrations, self.key)

    @property
    def enabled(self) -> bool:
        return self.cfg.enabled

    def _base(self) -> str:
        url = self.cfg.base_url.rstrip("/")
        host = urlparse(url).hostname or ""
        if host not in ("127.0.0.1", "localhost", "::1"):
            raise ActionError(f"{APPS[self.key]} must run on this computer (127.0.0.1); got '{host}'.",
                              "integration_not_local")
        return url

    def _headers(self) -> dict[str, str]:
        token = self.secrets.get(f"integration_{self.key}_token")
        if not token:
            raise ActionError(f"{APPS[self.key]} token is not set. Copy it from the app into Settings > Integrations.",
                              "integration_no_token")
        return {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    async def request(self, method: str, path: str, json: Any = None, params: dict | None = None,
                      timeout: float = 10.0) -> Any:
        if not self.enabled:
            raise ActionError(f"{APPS[self.key]} integration is disabled.", "integration_disabled")
        try:
            async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
                r = await client.request(method, self._base() + path, json=json, params=params,
                                         headers=self._headers())
        except httpx.HTTPError as exc:
            raise ActionError(f"{APPS[self.key]} is not reachable at {self.cfg.base_url}. Is it running?",
                              "integration_unreachable") from exc
        if r.status_code == 401:
            raise ActionError(f"{APPS[self.key]} rejected the token.", "integration_auth")
        if r.status_code >= 400:
            raise ActionError(f"{APPS[self.key]} error {r.status_code}: {r.text[:200]}", "integration_error")
        try:
            return r.json()
        except ValueError as exc:
            raise ActionError(f"{APPS[self.key]} returned invalid JSON.", "integration_error") from exc

    async def check(self) -> dict[str, Any]:
        status: dict[str, Any] = {"key": self.key, "name": APPS[self.key], "enabled": self.enabled,
                                  "connected": False, "checked_at": time.time(), "error": None, "info": None}
        if self.enabled:
            try:
                info = await self.request("GET", "/api/v1/status", timeout=4)
                status.update(connected=True, info=info)
            except ActionError as exc:
                status["error"] = str(exc)
        self.last_status = status
        return status


class Integrations:
    def __init__(self, settings_store, secrets):
        self.clients = {k: IntegrationClient(k, settings_store, secrets) for k in APPS}

    def __getitem__(self, key: str) -> IntegrationClient:
        return self.clients[key]

    async def check_all(self) -> list[dict[str, Any]]:
        out = []
        for c in self.clients.values():
            out.append(await c.check())
        return out

    def statuses(self) -> list[dict[str, Any]]:
        return [{**c.last_status, "key": k, "name": APPS[k], "enabled": c.enabled} for k, c in self.clients.items()]


def build_integration_actions(svc) -> None:
    from pydantic import BaseModel, Field

    from ..computer_control.base import ActionResult, ActionSpec, EmptyParams, Risk

    reg = svc.registry
    integ: Integrations = svc.integrations

    class GameQuery(BaseModel):
        query: str = Field("", max_length=200, description="Game name filter (empty = all)")

    class GameId(BaseModel):
        game: str = Field(..., min_length=1, max_length=200, description="Game id or name from the FRISTY library")

    class ScanParams(BaseModel):
        kind: str = Field("storage", pattern="^(storage|duplicates|large_files)$")

    class CleanParams(BaseModel):
        scan_id: str = Field(..., min_length=1, max_length=100)
        item_ids: list[str] = Field(default_factory=list, max_length=10000,
                                    description="Items from the scan to clean (empty = all recommended)")

    async def search_games(ctx, a):
        games = await integ["launcher"].request("GET", "/api/v1/games", params={"query": a.query})
        return ActionResult(True, f"{len(games)} game(s) in your FRISTY Launcher library.", data={"games": games},
                            verified=True)

    async def launch_game(ctx, a):
        games = await integ["launcher"].request("GET", "/api/v1/games", params={"query": a.game})
        match = next((g for g in games if str(g.get("id")) == a.game or g.get("name", "").lower() == a.game.lower()),
                     games[0] if len(games) == 1 else None)
        if not match:
            raise ActionError(f"No unique game '{a.game}' in FRISTY Launcher ({len(games)} matches).", "not_found")
        res = await integ["launcher"].request("POST", f"/api/v1/games/{match['id']}/launch")
        ok = bool(res.get("ok", True))
        return ActionResult(ok, f"FRISTY Launcher {'started' if ok else 'failed to start'} {match.get('name')}.",
                            data=res, verified=res.get("running"))

    async def playtime(ctx, a):
        games = await integ["launcher"].request("GET", "/api/v1/games", params={"query": a.query})
        games.sort(key=lambda g: -(g.get("playtime_minutes") or 0))
        top = [{"name": g.get("name"), "hours": round((g.get("playtime_minutes") or 0) / 60, 1)} for g in games[:20]]
        return ActionResult(True, "Playtime from FRISTY Launcher.", data={"playtime": top}, verified=True)

    async def performance(ctx, a):
        if integ["pc_manager"].enabled:
            try:
                m = await integ["pc_manager"].request("GET", "/api/v1/metrics")
                return ActionResult(True, "Performance from FRISTY PC Manager.", data={"source": "pc_manager", **m},
                                    verified=True)
            except ActionError:
                pass
        m = svc.metrics.latest() if svc.metrics else {}
        return ActionResult(True, "Performance from FRISTY AI's built-in monitor.",
                            data={"source": "builtin", **m, "warnings": svc.metrics.warnings() if svc.metrics else []},
                            verified=True)

    async def cleaner_scan(ctx, a):
        res = await integ["cleaner"].request("POST", "/api/v1/scan", json={"kind": a.kind}, timeout=300)
        return ActionResult(True, f"FRISTY Cleaner scan ({a.kind}) finished.", data=res, verified=True)

    async def cleaner_clean(ctx, a):
        res = await integ["cleaner"].request("POST", "/api/v1/clean", json={"scan_id": a.scan_id,
                                                                            "item_ids": a.item_ids}, timeout=600)
        ok = bool(res.get("ok", False))
        return ActionResult(ok, f"FRISTY Cleaner {'freed ' + str(round((res.get('freed_bytes') or 0) / 1e6, 1)) + ' MB' if ok else 'failed'}.",
                            data=res, verified=ok)

    def add(name, desc, params, risk, handler, **kw):
        reg.register(ActionSpec(name=name, description=desc, params=params, permission=kw.pop("perm", None),
                                risk=risk, handler=handler, category="integrations", **kw))

    add("fristy_launcher_games", "Search the FRISTY Launcher game library.", GameQuery, Risk.LOW, search_games)
    add("fristy_launcher_launch", "Launch a game through FRISTY Launcher.", GameId, Risk.LOW, launch_game,
        perm="app_launch", describe=lambda a: f"Launch {a.game} via FRISTY Launcher")
    add("fristy_launcher_playtime", "Show game playtime from FRISTY Launcher.", GameQuery, Risk.LOW, playtime)
    add("pc_performance", "Read CPU/GPU usage, temperatures and RAM (FRISTY PC Manager or built-in monitor).",
        EmptyParams, Risk.LOW, performance)
    add("fristy_cleaner_scan", "Scan storage, duplicates or large files with FRISTY Cleaner.", ScanParams, Risk.LOW,
        cleaner_scan)
    add("fristy_cleaner_clean", "Clean items found by a FRISTY Cleaner scan (always asks for approval).",
        CleanParams, Risk.HIGH, cleaner_clean, perm="file_access", confirm="always",
        describe=lambda a: f"Clean {len(a.item_ids) or 'all recommended'} item(s) from scan {a.scan_id}")
