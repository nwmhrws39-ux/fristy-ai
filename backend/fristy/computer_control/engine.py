"""The restricted action engine.

Every computer action - whether requested from the UI, the chat model, the
agent, an automation, a voice command or the paired mobile app - goes through
``ActionEngine.execute``:

  1. look up the action in the registry (unknown actions are rejected)
  2. validate arguments against the action's pydantic schema
  3. check the permission category is enabled in settings
  4. check platform support
  5. decide whether human confirmation is required, and ask for it
  6. execute with a timeout, honouring the emergency stop
  7. record everything in the audit log

The engine never reports success unless the handler returned ``ok=True``.
"""
from __future__ import annotations

import asyncio
import logging
import sys
import time
from typing import Any

from pydantic import ValidationError

from .base import ActionError, ActionRegistry, ActionResult, ExecutionContext, Risk

log = logging.getLogger(__name__)

# Sources that are not a human directly clicking a button in FRISTY.
INDIRECT_SOURCES = {"agent", "automation", "remote", "chat", "voice"}


class ActionEngine:
    def __init__(self, registry: ActionRegistry, settings_store, confirmations, audit, stop, bus=None,
                 default_timeout: float = 60.0):
        self.registry = registry
        self.settings = settings_store
        self.confirmations = confirmations
        self.audit = audit
        self.stop = stop
        self.bus = bus
        self.default_timeout = default_timeout
        self.is_windows = sys.platform == "win32"

    def needs_confirmation(self, spec, args, ctx: ExecutionContext) -> bool:
        if spec.confirm == "always":
            return True
        if spec.confirm_if and spec.confirm_if(args):
            return True
        if spec.confirm == "never":
            return False
        if spec.risk == Risk.HIGH:
            return True
        if spec.risk == Risk.MEDIUM:
            if ctx.untrusted_seen:
                return True
            if spec.name in ctx.preapproved:
                return False
            return ctx.source in ("agent", "remote", "automation")
        return False

    def validate(self, name: str, raw_args: dict[str, Any] | None):
        """Return (spec, parsed_args) or raise ActionError. No side effects."""
        spec = self.registry.get(name)
        if spec is None:
            raise ActionError(f"Unknown action '{name}'. Only registered actions can be executed.", "unknown_action")
        try:
            args = spec.params.model_validate(raw_args or {})
        except ValidationError as exc:
            errs = "; ".join(f"{'.'.join(map(str, e['loc'])) or 'args'}: {e['msg']}" for e in exc.errors())
            raise ActionError(f"Invalid arguments for {name}: {errs}", "invalid_arguments") from exc
        perm = spec.permission
        if perm and not self.settings.current.permissions.get(perm, False):
            raise ActionError(
                f"Permission '{perm}' is disabled. Enable it in Settings > Permissions to allow {name}.",
                "permission_denied",
            )
        if spec.windows_only and not self.is_windows:
            raise ActionError(f"{name} is only supported on Windows 10/11.", "unsupported_platform")
        return spec, args

    async def execute(self, name: str, raw_args: dict[str, Any] | None, ctx: ExecutionContext | None = None,
                      timeout: float | None = None) -> ActionResult:
        ctx = ctx or ExecutionContext()
        started = time.time()
        try:
            spec, args = self.validate(name, raw_args)
        except ActionError as exc:
            self.audit.record("action.rejected", action=name, source=ctx.source, status=exc.code,
                              detail={"args": raw_args, "reason": str(exc), "run_id": ctx.run_id})
            return ActionResult(False, str(exc), code=exc.code)

        summary = spec.summary(args)
        self._emit("action.started", name, summary, ctx)
        if self.needs_confirmation(spec, args, ctx):
            self._emit("action.awaiting_confirmation", name, summary, ctx)
            details = {"args": args.model_dump(), "run_id": ctx.run_id, "untrusted_context": ctx.untrusted_seen}
            if spec.preview:
                try:
                    details["preview"] = await asyncio.to_thread(spec.preview, args)
                except ActionError as exc:
                    self.audit.record("action.rejected", action=name, source=ctx.source, status=exc.code,
                                      detail={"reason": str(exc)})
                    return ActionResult(False, str(exc), code=exc.code)
                except Exception as exc:
                    details["preview"] = {"error": str(exc)}
            approved = await self.confirmations.request(
                action=name, summary=summary, risk=spec.risk.value, source=ctx.source,
                details=details,
            )
            self.audit.record("action.confirmation", action=name, source=ctx.source,
                              status="approved" if approved else "denied", detail={"summary": summary})
            if not approved:
                self._emit("action.finished", name, summary, ctx, ok=False, message="Denied by user")
                return ActionResult(False, f"The user did not approve: {summary}", code="not_approved")

        if ctx.dry_run:
            return ActionResult(True, f"Dry run: would execute {summary}", code="dry_run", verified=None)

        try:
            result = await asyncio.wait_for(spec.handler(ctx, args), timeout or self.default_timeout)
            if not isinstance(result, ActionResult):
                raise TypeError(f"handler for {name} returned {type(result).__name__}")
        except asyncio.CancelledError:
            self.audit.record("action.cancelled", action=name, source=ctx.source, status="cancelled",
                              detail={"summary": summary})
            self._emit("action.finished", name, summary, ctx, ok=False, message="Cancelled")
            raise
        except asyncio.TimeoutError:
            result = ActionResult(False, f"{name} timed out", code="timeout")
        except ActionError as exc:
            result = ActionResult(False, str(exc), code=exc.code)
        except Exception as exc:  # unexpected bug or OS error
            log.exception("action %s crashed", name)
            result = ActionResult(False, f"{name} failed: {type(exc).__name__}: {exc}", code="exception")

        elapsed = round((time.time() - started) * 1000)
        self.audit.record(
            "action.executed", action=name, source=ctx.source,
            status="success" if result.ok else result.code,
            detail={"summary": summary, "message": result.message, "verified": result.verified,
                    "elapsed_ms": elapsed, "run_id": ctx.run_id},
        )
        self._emit("action.finished", name, summary, ctx, ok=result.ok, message=result.message,
                   verified=result.verified)
        return result

    def _emit(self, type_: str, name: str, summary: str, ctx: ExecutionContext, **extra) -> None:
        if self.bus:
            self.bus.publish(type_, action=name, summary=summary, source=ctx.source, run_id=ctx.run_id, **extra)

    def catalog(self, ai_only: bool = False) -> list[dict[str, Any]]:
        perms = self.settings.current.permissions
        out = []
        for spec in self.registry.all():
            if ai_only and not spec.ai_visible:
                continue
            out.append({
                "name": spec.name,
                "description": spec.description,
                "permission": spec.permission,
                "permission_enabled": perms.get(spec.permission, True) if spec.permission else True,
                "risk": spec.risk.value,
                "confirm": spec.confirm,
                "category": spec.category,
                "windows_only": spec.windows_only,
                "available": (not spec.windows_only or self.is_windows),
                "schema": spec.tool_schema(),
            })
        return out
