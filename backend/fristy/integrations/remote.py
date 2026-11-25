"""FRISTY Remote: authenticated API for the paired mobile app.

* Disabled by default. Runs as a separate listener from the main backend API.
* Binds to 127.0.0.1 unless the user explicitly enables LAN access.
* Devices pair with a 6-digit one-time code shown in the desktop UI (valid 5
  minutes, 5 attempts). Each device receives a random token; only its SHA-256
  hash is stored. Tokens can be revoked at any time.
* Commands go through the same orchestrator/ActionEngine as desktop requests,
  with source="remote", so state-changing actions need confirmation ON THE PC.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import secrets
import time
import uuid
from typing import Any, Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from ..core.db import now

log = logging.getLogger(__name__)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class PairRequest(BaseModel):
    code: str = Field(..., min_length=6, max_length=6)
    device_name: str = Field(..., min_length=1, max_length=60)


class CommandRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)
    mode: str = Field("chat", pattern="^(chat|agent)$")


class RemoteServer:
    def __init__(self, svc):
        self.svc = svc
        self._code: Optional[str] = None
        self._code_expires = 0.0
        self._attempts = 0
        self._server = None
        self._task: Optional[asyncio.Task] = None
        self._rate: dict[str, list[float]] = {}
        self.app = self._build_app()

    # ------------------------------------------------------------ pairing
    def start_pairing(self) -> dict[str, Any]:
        self._code = f"{secrets.randbelow(1_000_000):06d}"
        self._code_expires = time.time() + 300
        self._attempts = 0
        self.svc.audit.record("remote.pairing_started", source="ui", status="ok")
        return {"code": self._code, "expires_at": self._code_expires}

    def pair(self, code: str, device_name: str) -> dict[str, str]:
        if not self._code or time.time() > self._code_expires:
            raise HTTPException(403, "No active pairing code. Start pairing on the PC.")
        self._attempts += 1
        if self._attempts > 5:
            self._code = None
            raise HTTPException(429, "Too many attempts; start pairing again on the PC.")
        if not hmac.compare_digest(code, self._code):
            raise HTTPException(403, "Wrong pairing code.")
        self._code = None
        token = secrets.token_urlsafe(32)
        did = uuid.uuid4().hex
        self.svc.db.execute("INSERT INTO remote_devices(id, name, token_hash, created_at) VALUES(?,?,?,?)",
                            (did, device_name, _hash(token), now()))
        self.svc.audit.record("remote.paired", source="remote", status="ok", detail={"device": device_name})
        self.svc.bus.publish("remote.paired", device=device_name)
        return {"device_id": did, "token": token}

    def devices(self) -> list[dict[str, Any]]:
        return self.svc.db.query("SELECT id, name, created_at, last_seen FROM remote_devices ORDER BY created_at")

    def revoke(self, did: str) -> None:
        self.svc.db.execute("DELETE FROM remote_devices WHERE id=?", (did,))
        self.svc.audit.record("remote.revoked", source="ui", status="ok", detail={"device_id": did})

    def authenticate(self, token: str) -> Optional[dict[str, Any]]:
        if not token:
            return None
        row = self.svc.db.query_one("SELECT id, name FROM remote_devices WHERE token_hash=?", (_hash(token),))
        if row:
            self.svc.db.execute("UPDATE remote_devices SET last_seen=? WHERE id=?", (now(), row["id"]))
        return row

    def _rate_ok(self, key: str, limit: int = 30, window: float = 60) -> bool:
        t = time.time()
        hits = [h for h in self._rate.get(key, []) if t - h < window]
        hits.append(t)
        self._rate[key] = hits
        return len(hits) <= limit

    # ---------------------------------------------------------------- app
    def _build_app(self) -> FastAPI:
        app = FastAPI(title="FRISTY Remote API", docs_url=None, redoc_url=None, openapi_url=None)

        def device(request: Request) -> dict[str, Any]:
            if not self.svc.settings.current.remote.enabled:
                raise HTTPException(503, "FRISTY Remote is disabled on this PC.")
            auth = request.headers.get("authorization", "")
            token = auth[7:] if auth.lower().startswith("bearer ") else ""
            dev = self.authenticate(token)
            if not dev:
                raise HTTPException(401, "Unauthorized")
            if not self._rate_ok(dev["id"]):
                raise HTTPException(429, "Rate limited")
            return dev

        @app.post("/api/v1/pair")
        async def pair(req: PairRequest, request: Request):
            if not self.svc.settings.current.remote.enabled:
                raise HTTPException(503, "FRISTY Remote is disabled on this PC.")
            if not self._rate_ok("pair:" + (request.client.host if request.client else "?"), limit=10):
                raise HTTPException(429, "Rate limited")
            return self.pair(req.code, req.device_name)

        @app.get("/api/v1/status")
        async def status(dev=Depends(device)):
            m = self.svc.metrics.latest() if self.svc.metrics else {}
            return {"ok": True, "device": dev["name"], "metrics": m,
                    "ai": {"provider": self.svc.settings.current.ai.provider, "model": self.svc.ai.active_model()},
                    "active_runs": len(self.svc.orchestrator.active())}

        @app.post("/api/v1/command")
        async def command(req: CommandRequest, dev=Depends(device)):
            self.svc.audit.record("remote.command", source="remote", status="received",
                                  detail={"device": dev["name"], "text": req.text[:200]})
            return self.svc.orchestrator.start(req.text, None, req.mode, None, source="remote")

        return app

    # ------------------------------------------------------------- server
    async def apply_settings(self) -> None:
        cfg = self.svc.settings.current.remote
        await self.stop()
        if not cfg.enabled:
            return
        import uvicorn

        host = "0.0.0.0" if cfg.allow_lan else "127.0.0.1"
        config = uvicorn.Config(self.app, host=host, port=cfg.port, log_level="warning", access_log=False)
        self._server = uvicorn.Server(config)
        self._server.install_signal_handlers = lambda: None  # type: ignore[method-assign]
        self._task = asyncio.create_task(self._server.serve())
        log.info("FRISTY Remote listening on %s:%s", host, cfg.port)

    async def stop(self) -> None:
        if self._server:
            self._server.should_exit = True
            if self._task:
                try:
                    await asyncio.wait_for(self._task, 5)
                except (asyncio.TimeoutError, Exception):
                    self._task.cancel()
            self._server = None
            self._task = None

    @property
    def running(self) -> bool:
        return self._server is not None and bool(getattr(self._server, "started", False))
