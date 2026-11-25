"""Downloads/removes local Ollama models from inside FRISTY, with live progress."""
from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Any, Optional

from ..computer_control.base import ActionError
from .models_catalog import CURATED, recommend
from .providers.ollama import ollama_delete, ollama_pull, ollama_version
from .types import ProviderError

log = logging.getLogger(__name__)
MODEL_NAME = re.compile(r"^[a-zA-Z0-9][\w.\-/]{0,80}(:[\w.\-]{1,40})?$")


class ModelInstaller:
    def __init__(self, ai, settings_store, bus, audit):
        self.ai = ai
        self.settings = settings_store
        self.bus = bus
        self.audit = audit
        self.jobs: dict[str, dict[str, Any]] = {}
        self._tasks: dict[str, asyncio.Task] = {}

    @property
    def base_url(self) -> str:
        return self.settings.current.ai.providers["ollama"].base_url or "http://127.0.0.1:11434"

    async def status(self) -> dict[str, Any]:
        version = await ollama_version(self.base_url)
        installed = [m.id for m in self.ai._models.get("ollama", [])] if version else []
        rec = recommend()
        for m in rec["models"]:
            m["installed"] = m["id"] in installed or f"{m['id']}:latest" in installed
        return {"ollama_running": version is not None, "ollama_version": version, "installed": installed,
                "jobs": list(self.jobs.values()), **rec}

    def start(self, model: str) -> dict[str, Any]:
        model = model.strip()
        if not MODEL_NAME.match(model):
            raise ActionError(f"Invalid model name '{model}'.", "invalid_model")
        job = self.jobs.get(model)
        if job and job["status"] == "downloading":
            return job
        job = {"model": model, "status": "downloading", "percent": 0.0, "completed": 0, "total": 0,
               "detail": "starting", "error": None, "started_at": time.time()}
        self.jobs[model] = job
        self._tasks[model] = asyncio.create_task(self._run(job))
        self.audit.record("model.pull", action=model, source="ui", status="started")
        return job

    def cancel(self, model: str) -> bool:
        t = self._tasks.get(model)
        if t and not t.done():
            t.cancel()
            return True
        return False

    async def _run(self, job: dict[str, Any]) -> None:
        model = job["model"]
        layers: dict[str, tuple[int, int]] = {}
        last_emit = 0.0
        try:
            async for ev in ollama_pull(self.base_url, model):
                job["detail"] = ev.get("status", "")
                if ev.get("digest") and ev.get("total"):
                    layers[ev["digest"]] = (int(ev.get("completed") or 0), int(ev["total"]))
                    job["completed"] = sum(c for c, _ in layers.values())
                    job["total"] = sum(t for _, t in layers.values())
                    job["percent"] = round(100 * job["completed"] / max(1, job["total"]), 1)
                now = time.time()
                if now - last_emit > 0.4:
                    last_emit = now
                    self.bus.publish("ai.pull", **job)
            job.update(status="done", percent=100.0, detail="success")
            await self.ai.discover("ollama")
            self._auto_select(model)
            self.audit.record("model.pull", action=model, source="ui", status="success")
        except asyncio.CancelledError:
            job.update(status="cancelled", detail="cancelled")
            self.audit.record("model.pull", action=model, source="ui", status="cancelled")
        except (ProviderError, ActionError) as exc:
            job.update(status="error", error=str(exc))
            self.audit.record("model.pull", action=model, source="ui", status="error", detail={"error": str(exc)})
        except Exception as exc:  # pragma: no cover
            log.exception("pull failed")
            job.update(status="error", error=f"{type(exc).__name__}: {exc}")
        finally:
            self._tasks.pop(model, None)
            self.bus.publish("ai.pull", **job)

    def _auto_select(self, model: str) -> None:
        """Use the new model if nothing usable is selected yet (only tool-capable 'main' models)."""
        ai = self.settings.current.ai
        curated = next((m for m in CURATED if m["id"] == model), None)
        if curated and (curated["role"] != "main" or not curated["tools"]):
            return
        installed = {m.id for m in self.ai._models.get("ollama", [])}
        if ai.provider == "ollama" and (not ai.model or ai.model not in installed):
            self.settings.update({"ai": {"model": model}})
            self.bus.publish("settings.changed")

    async def delete(self, model: str) -> None:
        if not MODEL_NAME.match(model):
            raise ActionError(f"Invalid model name '{model}'.", "invalid_model")
        await ollama_delete(self.base_url, model)
        if self.settings.current.ai.model == model:
            self.settings.update({"ai": {"model": ""}})
        await self.ai.discover("ollama")
        self.audit.record("model.delete", action=model, source="ui", status="success")
