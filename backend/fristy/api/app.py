"""FastAPI application exposed ONLY on 127.0.0.1 and protected by a per-session token."""
from __future__ import annotations

import asyncio
import base64
import os
import hmac
import json
import logging
import time
from contextlib import asynccontextmanager
from typing import Any, Optional

from fastapi import Body, Depends, FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from .. import __version__
from ..automations.models import TEMPLATES
from ..computer_control.base import ActionError, ExecutionContext
from ..config import RuntimeConfig
from ..core.bootstrap import build_services
from ..core.services import Services
from ..security.secrets import KNOWN_SECRETS

log = logging.getLogger(__name__)


class ChatRequest(BaseModel):
    text: str = Field("", max_length=20000)
    conversation_id: Optional[str] = None
    mode: str = Field("chat", pattern="^(chat|agent)$")
    images: list[str] = Field(default_factory=list, max_length=4)
    source: str = Field("chat", pattern="^(chat|voice)$")


class ActionRequest(BaseModel):
    args: dict[str, Any] = Field(default_factory=dict)


class Decision(BaseModel):
    approved: bool


class SecretValue(BaseModel):
    value: str = Field(..., max_length=4000)


class MemoryIn(BaseModel):
    category: str
    key: str
    value: str


class MemoryPatch(BaseModel):
    category: Optional[str] = None
    key: Optional[str] = None
    value: Optional[str] = None


class TTSRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=4000)


def create_app(config: RuntimeConfig | None = None, services: Services | None = None) -> FastAPI:
    config = config or RuntimeConfig.from_env()
    svc = services or build_services(config)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        svc.bus.bind_loop(asyncio.get_running_loop())
        svc.metrics.start()
        svc.automations.start_scheduler()
        if not os.environ.get("FRISTY_DISABLE_PRELOAD"):
            svc.voice.preload()
        try:
            await svc.remote.apply_settings()
        except Exception as exc:
            log.warning("remote server failed to start: %s", exc)
        asyncio.create_task(_initial_discovery())
        svc.audit.record("app.started", source="system", status="ok", detail={"version": __version__})
        yield
        await svc.remote.stop()
        await svc.automations.stop_scheduler()

    async def _initial_discovery():
        try:
            await svc.ai.discover()
            await svc.integrations.check_all()
        except Exception as exc:
            log.info("initial discovery: %s", exc)

    app = FastAPI(title="FRISTY AI Backend", version=__version__, lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url=None)
    app.state.svc = svc
    app.add_middleware(CORSMiddleware, allow_origins=["null", "http://localhost:5173", "http://127.0.0.1:5173",
                                                      "app://fristy"],
                       allow_methods=["*"], allow_headers=["*"])

    allowed_hosts = {f"127.0.0.1:{config.port}", f"localhost:{config.port}", "testserver"}

    @app.middleware("http")
    async def host_guard(request: Request, call_next):
        # Defends against DNS-rebinding: only loopback host headers are accepted.
        if request.headers.get("host") not in allowed_hosts:
            return JSONResponse({"detail": "invalid host"}, status_code=421)
        return await call_next(request)

    def auth(request: Request) -> None:
        h = request.headers.get("authorization", "")
        token = h[7:] if h.lower().startswith("bearer ") else ""
        if not token or not hmac.compare_digest(token, config.token):
            raise HTTPException(401, "unauthorized")

    @app.exception_handler(ActionError)
    async def _action_error(_req, exc: ActionError):
        return JSONResponse({"detail": str(exc), "code": exc.code}, status_code=400)

    @app.get("/health")
    async def health():
        return {"ok": True, "version": __version__}

    A = [Depends(auth)]

    # ------------------------------------------------------------ status
    @app.get("/api/status", dependencies=A)
    async def status():
        st = svc.settings.current
        recent = svc.audit.recent(15)
        autos = svc.automations.list()
        return {
            "version": __version__,
            "uptime_s": round(time.time() - (svc.started_at or time.time())),
            "platform": svc.platform.name,
            "ai": {"provider": st.ai.provider, "model": svc.ai.active_model(), "cloud": svc.ai.is_cloud(),
                   "status": svc.ai.status, "latency_ms": svc.ai.last_latency_ms,
                   "first_token_ms": svc.ai.last_first_token_ms, "supports_vision": svc.ai.supports_vision()},
            "metrics": svc.metrics.latest(), "warnings": svc.metrics.warnings(),
            "recent_actions": recent,
            "automations": {"total": len(autos), "enabled": sum(1 for a in autos if a["enabled"]),
                            "items": [{"id": a["id"], "name": a["name"], "enabled": a["enabled"],
                                       "trigger": a["trigger"]["type"], "last_run_at": a["last_run_at"]}
                                      for a in autos]},
            "integrations": svc.integrations.statuses(),
            "remote": {"enabled": st.remote.enabled, "running": svc.remote.running,
                       "devices": len(svc.remote.devices())},
            "voice": svc.voice.status(),
            "runs": svc.orchestrator.active(),
            "pending_confirmations": svc.confirmations.pending(),
            "secrets_persistent": svc.secrets.persistent,
            "secrets_backend": svc.secrets.backend_name,
        }

    # ---------------------------------------------------------- settings
    @app.get("/api/settings", dependencies=A)
    async def get_settings():
        return svc.settings.current.model_dump()

    @app.patch("/api/settings", dependencies=A)
    async def patch_settings(patch: dict[str, Any] = Body(...)):
        old = svc.settings.current
        try:
            new = svc.settings.update(patch)
        except Exception as exc:
            raise HTTPException(422, f"invalid settings: {exc}")
        changed_perms = {k: v for k, v in new.permissions.items() if old.permissions.get(k) != v}
        if changed_perms:
            svc.audit.record("permissions.changed", source="ui", status="ok", detail=changed_perms)
        if new.remote != old.remote:
            await svc.remote.apply_settings()
        if new.ai.providers != old.ai.providers or new.ai.provider != old.ai.provider:
            asyncio.create_task(svc.ai.discover(new.ai.provider))
        svc.bus.publish("settings.changed")
        return new.model_dump()

    @app.post("/api/full-access", dependencies=A)
    async def full_access(body: dict[str, bool] = Body(...)):
        """One-click full computer access (explicit user consent in the UI)."""
        from pathlib import Path

        from ..core.settings import PERMISSION_NAMES

        enable = bool(body.get("enable"))
        cur = svc.settings.current
        if enable:
            home = str(Path.home())
            patch = {"permissions": {p: True for p in PERMISSION_NAMES}, "confirmation_level": "relaxed",
                     "full_access": True, "closable_apps": sorted(set(cur.closable_apps) | {"*"}),
                     "approved_dirs": cur.approved_dirs if home in cur.approved_dirs else [*cur.approved_dirs, home]}
        else:
            patch = {"permissions": {p: p in ("app_launch", "system_control", "network_access") for p in PERMISSION_NAMES},
                     "confirmation_level": "strict", "full_access": False,
                     "closable_apps": [a for a in cur.closable_apps if a != "*"]}
        new = svc.settings.update(patch)
        svc.audit.record("permissions.full_access", source="ui", status="enabled" if enable else "disabled")
        svc.bus.publish("settings.changed")
        return new.model_dump()

    @app.get("/api/secrets", dependencies=A)
    async def secrets_status():
        return {"persistent": svc.secrets.persistent, "backend": svc.secrets.backend_name,
                "secrets": svc.secrets.status()}

    @app.put("/api/secrets/{name}", dependencies=A)
    async def set_secret(name: str, body: SecretValue):
        if name not in KNOWN_SECRETS:
            raise HTTPException(404, "unknown secret")
        svc.secrets.set(name, body.value)
        svc.audit.record("secret.updated", action=name, source="ui", status="ok")
        return {"ok": True}

    @app.delete("/api/secrets/{name}", dependencies=A)
    async def del_secret(name: str):
        if name not in KNOWN_SECRETS:
            raise HTTPException(404, "unknown secret")
        svc.secrets.delete(name)
        svc.audit.record("secret.deleted", action=name, source="ui", status="ok")
        return {"ok": True}

    # ---------------------------------------------------------------- AI
    @app.get("/api/ai/models", dependencies=A)
    async def models(refresh: bool = False, provider: Optional[str] = None):
        if refresh:
            return await svc.ai.discover(provider)
        return svc.ai.catalog()

    @app.post("/api/ai/test", dependencies=A)
    async def test_ai():
        from ..ai_engine.types import Message, ProviderError

        t0 = time.time()
        try:
            text = await svc.ai.complete([Message("user", "Reply with exactly: FRISTY online")])
            return {"ok": True, "reply": text.strip()[:200], "latency_ms": round((time.time() - t0) * 1000)}
        except ProviderError as exc:
            return {"ok": False, "error": str(exc)}

    @app.get("/api/ai/local-models", dependencies=A)
    async def local_models():
        return await svc.models.status()

    @app.post("/api/ai/local-models/pull", dependencies=A)
    async def pull_model(body: dict[str, str] = Body(...)):
        return svc.models.start(body.get("model", ""))

    @app.post("/api/ai/local-models/cancel", dependencies=A)
    async def cancel_pull(body: dict[str, str] = Body(...)):
        return {"ok": svc.models.cancel(body.get("model", ""))}

    @app.post("/api/ai/local-models/delete", dependencies=A)
    async def delete_model(body: dict[str, str] = Body(...)):
        from ..ai_engine.types import ProviderError

        try:
            await svc.models.delete(body.get("model", ""))
        except ProviderError as exc:
            raise HTTPException(400, str(exc))
        return {"ok": True}

    # -------------------------------------------------------------- chat
    @app.post("/api/chat", dependencies=A)
    async def chat(req: ChatRequest):
        return svc.orchestrator.start(req.text, req.conversation_id, req.mode, req.images, req.source)

    @app.post("/api/agent/plan", dependencies=A)
    async def plan_only(req: ChatRequest):
        """Preview a plan without executing anything."""
        return await svc.orchestrator.make_plan(req.text)

    @app.get("/api/runs", dependencies=A)
    async def runs():
        return svc.orchestrator.active()

    @app.post("/api/runs/{run_id}/{op}", dependencies=A)
    async def run_op(run_id: str, op: str):
        fn = {"pause": svc.orchestrator.pause, "resume": svc.orchestrator.resume,
              "cancel": svc.orchestrator.cancel}.get(op)
        if not fn:
            raise HTTPException(404, "unknown operation")
        return {"ok": fn(run_id)}

    @app.get("/api/conversations", dependencies=A)
    async def conversations(search: Optional[str] = None, limit: int = 50):
        return svc.conversations.list(limit, search)

    @app.get("/api/conversations/{cid}", dependencies=A)
    async def conversation(cid: str):
        c = svc.conversations.get(cid)
        if not c:
            raise HTTPException(404, "not found")
        return {**c, "messages": svc.conversations.messages(cid)}

    @app.patch("/api/conversations/{cid}", dependencies=A)
    async def rename_conversation(cid: str, body: dict[str, str] = Body(...)):
        svc.conversations.rename(cid, body.get("title", "")[:120] or "Conversation")
        return {"ok": True}

    @app.delete("/api/conversations/{cid}", dependencies=A)
    async def delete_conversation(cid: str):
        svc.conversations.delete(cid)
        return {"ok": True}

    @app.delete("/api/conversations", dependencies=A)
    async def clear_conversations():
        svc.conversations.clear()
        svc.audit.record("conversations.cleared", source="ui", status="ok")
        return {"ok": True}

    # ----------------------------------------------------------- actions
    @app.get("/api/actions", dependencies=A)
    async def actions():
        return svc.engine.catalog()

    @app.post("/api/actions/{name}", dependencies=A)
    async def run_action(name: str, req: ActionRequest):
        res = await svc.engine.execute(name, req.args, ExecutionContext(source="ui"))
        return res.to_dict()

    @app.get("/api/confirmations", dependencies=A)
    async def pending():
        return svc.confirmations.pending()

    @app.post("/api/confirmations/{cid}", dependencies=A)
    async def decide(cid: str, d: Decision):
        return {"ok": svc.confirmations.resolve(cid, d.approved)}

    @app.post("/api/emergency-stop", dependencies=A)
    async def emergency_stop():
        n = svc.stop.emergency_stop()
        svc.audit.record("emergency.stop", source="ui", status="ok", detail={"cancelled_runs": n})
        svc.bus.publish("emergency.stop", cancelled=n)
        return {"ok": True, "cancelled": n}

    @app.get("/api/audit", dependencies=A)
    async def audit(limit: int = 100, offset: int = 0, action: Optional[str] = None):
        rows = svc.audit.recent(limit, offset, action)
        for r in rows:
            if r.get("detail"):
                try:
                    r["detail"] = json.loads(r["detail"])
                except ValueError:
                    pass
        return rows

    # ------------------------------------------------------------ memory
    @app.get("/api/memory", dependencies=A)
    async def memory_list(category: Optional[str] = None, search: Optional[str] = None):
        return svc.memory.list(category, search)

    @app.post("/api/memory", dependencies=A)
    async def memory_add(m: MemoryIn):
        return svc.memory.upsert(m.category, m.key, m.value, "user")

    @app.patch("/api/memory/{mid}", dependencies=A)
    async def memory_patch(mid: int, m: MemoryPatch):
        return svc.memory.update(mid, m.value, m.key, m.category)

    @app.delete("/api/memory/{mid}", dependencies=A)
    async def memory_delete(mid: int):
        svc.memory.delete(mid)
        return {"ok": True}

    @app.delete("/api/memory", dependencies=A)
    async def memory_clear():
        n = svc.memory.clear()
        svc.audit.record("memory.cleared", source="ui", status="ok", detail={"deleted": n})
        return {"ok": True, "deleted": n}

    @app.get("/api/memory-export", dependencies=A)
    async def memory_export():
        return svc.memory.export()

    @app.post("/api/memory-import", dependencies=A)
    async def memory_import(data: dict[str, Any] = Body(...)):
        return {"imported": svc.memory.import_(data)}

    # ------------------------------------------------------- automations
    @app.get("/api/automations", dependencies=A)
    async def autos():
        return svc.automations.list()

    @app.get("/api/automation-templates", dependencies=A)
    async def templates():
        return TEMPLATES

    @app.post("/api/automations", dependencies=A)
    async def auto_create(data: dict[str, Any] = Body(...)):
        try:
            return svc.automations.save(data)
        except ActionError:
            raise
        except Exception as exc:
            raise HTTPException(422, str(exc))

    @app.put("/api/automations/{aid}", dependencies=A)
    async def auto_update(aid: str, data: dict[str, Any] = Body(...)):
        try:
            return svc.automations.save(data, aid)
        except ActionError:
            raise
        except Exception as exc:
            raise HTTPException(422, str(exc))

    @app.delete("/api/automations/{aid}", dependencies=A)
    async def auto_delete(aid: str):
        svc.automations.delete(aid)
        return {"ok": True}

    @app.post("/api/automations/{aid}/run", dependencies=A)
    async def auto_run(aid: str):
        res = await svc.automations.run(aid, source="ui")
        return res.to_dict()

    # ------------------------------------------------------ integrations
    @app.get("/api/integrations", dependencies=A)
    async def integrations(check: bool = False):
        return await svc.integrations.check_all() if check else svc.integrations.statuses()

    @app.get("/api/remote", dependencies=A)
    async def remote_status():
        st = svc.settings.current.remote
        return {"enabled": st.enabled, "allow_lan": st.allow_lan, "port": st.port, "running": svc.remote.running,
                "devices": svc.remote.devices()}

    @app.post("/api/remote/pairing", dependencies=A)
    async def remote_pair():
        if not svc.settings.current.remote.enabled:
            raise HTTPException(400, "Enable FRISTY Remote first.")
        return svc.remote.start_pairing()

    @app.delete("/api/remote/devices/{did}", dependencies=A)
    async def remote_revoke(did: str):
        svc.remote.revoke(did)
        return {"ok": True}

    # ------------------------------------------------------------- voice
    @app.get("/api/voice/status", dependencies=A)
    async def voice_status():
        return svc.voice.status()

    @app.post("/api/voice/mic", dependencies=A)
    async def voice_mic(body: dict[str, bool] = Body(...)):
        svc.voice.mic_enabled = bool(body.get("enabled", True))
        svc.audit.record("voice.mic", source="ui", status="enabled" if svc.voice.mic_enabled else "disabled")
        svc.bus.publish("voice.mic", enabled=svc.voice.mic_enabled)
        return {"enabled": svc.voice.mic_enabled}

    @app.post("/api/voice/transcribe", dependencies=A)
    async def transcribe(request: Request, language: Optional[str] = Query(None, pattern="^(he|en)$")):
        data = await request.body()
        if len(data) > 25 * 1024 * 1024:
            raise HTTPException(413, "audio too large")
        return await svc.voice.transcribe(data, language)

    @app.post("/api/voice/wake", dependencies=A)
    async def wake(request: Request):
        return await svc.voice.check_wake(await request.body())

    @app.post("/api/voice/tts", dependencies=A)
    async def tts(req: TTSRequest):
        audio = await svc.voice.synthesize_cloud(req.text)
        return Response(content=audio, media_type="audio/mpeg")

    # ------------------------------------------------------------ screen
    @app.post("/api/screen/snapshot", dependencies=A)
    async def snapshot():
        cap = await asyncio.to_thread(svc.screen.capture, 1, "user request")
        img, factor = await asyncio.to_thread(cap.for_model, 1600)
        svc.audit.record("screen.snapshot", source="ui", status="ok")
        return {"image_b64": img, "width": cap.width, "height": cap.height, "factor": factor}

    @app.get("/api/system/info", dependencies=A)
    async def sysinfo():
        return await asyncio.to_thread(svc.platform.system_info)

    @app.get("/api/metrics", dependencies=A)
    async def metrics():
        return {"latest": svc.metrics.latest(), "history": list(svc.metrics.history), "warnings": svc.metrics.warnings()}

    # --------------------------------------------------------- websocket
    @app.websocket("/ws")
    async def ws(websocket: WebSocket, token: str = ""):
        if websocket.headers.get("host") not in allowed_hosts or not token or not hmac.compare_digest(token, config.token):
            await websocket.close(code=4401)
            return
        await websocket.accept()
        q = svc.bus.subscribe()
        await websocket.send_json({"type": "hello", "version": __version__})

        async def reader():
            while True:
                msg = await websocket.receive_text()
                if msg == "ping":
                    await websocket.send_text("pong")

        rtask = asyncio.create_task(reader())
        try:
            while True:
                get = asyncio.create_task(q.get())
                done, _ = await asyncio.wait({get, rtask}, return_when=asyncio.FIRST_COMPLETED)
                if rtask in done:
                    get.cancel()
                    break
                await websocket.send_text(json.dumps(get.result(), ensure_ascii=False, default=str))
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            rtask.cancel()
            svc.bus.unsubscribe(q)

    svc.confirmations.ui_connected = lambda: len(svc.bus._subscribers) > 0
    return app
