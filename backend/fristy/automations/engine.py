"""Runs automations through the ActionEngine; handles phrase matching and schedules."""
from __future__ import annotations

import asyncio
import difflib
import json
import logging
import re
import time
import uuid
from datetime import datetime
from typing import Any, Optional

from ..computer_control.base import ActionError, ActionResult, ExecutionContext
from ..core.db import Database, dumps, now
from .models import Automation, Condition

log = logging.getLogger(__name__)


def _norm(s: str) -> str:
    return re.sub(r"[^\w֐-׿ ]", "", s.lower()).strip()


def _in_range(now_hm: str, start: str, end: str) -> bool:
    return start <= now_hm < end if start <= end else (now_hm >= start or now_hm < end)


class AutomationEngine:
    def __init__(self, db: Database, engine, confirmations, platform, bus, audit, stop):
        self.db = db
        self.engine = engine
        self.confirmations = confirmations
        self.platform = platform
        self.bus = bus
        self.audit = audit
        self.stop = stop
        self._task: Optional[asyncio.Task] = None
        self._running: set[str] = set()

    # ------------------------------------------------------------ storage
    def list(self) -> list[dict[str, Any]]:
        rows = self.db.query("SELECT * FROM automations ORDER BY name")
        return [self._row(r) for r in rows]

    @staticmethod
    def _row(r: dict) -> dict[str, Any]:
        d = json.loads(r["definition"])
        d.update({"id": r["id"], "enabled": bool(r["enabled"]), "last_run_at": r["last_run_at"],
                  "updated_at": r["updated_at"]})
        return d

    def get(self, aid: str) -> dict[str, Any]:
        r = self.db.query_one("SELECT * FROM automations WHERE id=?", (aid,))
        if not r:
            raise ActionError(f"Automation {aid} not found.", "not_found")
        return self._row(r)

    def validate(self, data: dict[str, Any]) -> Automation:
        auto = Automation.model_validate(data)
        for i, step in enumerate(auto.steps):
            if step.action not in self.engine.registry:
                raise ActionError(f"Step {i + 1}: unknown action '{step.action}'.", "invalid_automation")
            if step.action == "run_custom_command":
                raise ActionError("Automations cannot call other automations.", "invalid_automation")
            spec = self.engine.registry.get(step.action)
            try:
                spec.params.model_validate(step.args)
            except Exception as exc:
                raise ActionError(f"Step {i + 1} ({step.action}): invalid arguments - {exc}",
                                  "invalid_automation") from exc
        if auto.trigger.type == "phrase" and not [p for p in auto.trigger.phrases if p.strip()]:
            raise ActionError("Phrase triggers need at least one phrase.", "invalid_automation")
        if auto.trigger.type == "schedule" and not auto.trigger.time:
            raise ActionError("Schedule triggers need a time (HH:MM).", "invalid_automation")
        return auto

    def save(self, data: dict[str, Any], aid: Optional[str] = None) -> dict[str, Any]:
        auto = self.validate(data)
        t = now()
        defn = auto.model_dump()
        enabled = defn.pop("enabled")
        if aid:
            self.get(aid)
            self.db.execute("UPDATE automations SET name=?, definition=?, enabled=?, updated_at=? WHERE id=?",
                            (auto.name, dumps(defn), int(enabled), t, aid))
        else:
            aid = uuid.uuid4().hex
            self.db.execute("INSERT INTO automations(id, name, definition, enabled, created_at, updated_at) "
                            "VALUES(?,?,?,?,?,?)", (aid, auto.name, dumps(defn), int(enabled), t, t))
        self.audit.record("automation.saved", action=auto.name, source="ui", status="ok")
        return self.get(aid)

    def delete(self, aid: str) -> None:
        self.db.execute("DELETE FROM automations WHERE id=?", (aid,))

    def set_enabled(self, aid: str, enabled: bool) -> dict[str, Any]:
        self.db.execute("UPDATE automations SET enabled=?, updated_at=? WHERE id=?", (int(enabled), now(), aid))
        return self.get(aid)

    # ----------------------------------------------------------- matching
    def match_phrase(self, text: str) -> Optional[dict[str, Any]]:
        t = _norm(text)
        if not t:
            return None
        # Allow "run X" / "start X" / "הפעל X" prefixes.
        t2 = re.sub(r"^(run|start|activate|הפעל|תפעיל|הרץ|תריץ)\s+", "", t)
        best, best_score = None, 0.0
        for a in self.list():
            if not a["enabled"] or a["trigger"]["type"] not in ("phrase", "manual"):
                continue
            phrases = list(a["trigger"].get("phrases") or [])
            phrases.append(a["name"])
            for p in phrases:
                pn = _norm(p)
                if not pn:
                    continue
                score = max(difflib.SequenceMatcher(None, t, pn).ratio(),
                            difflib.SequenceMatcher(None, t2, pn).ratio())
                if score > best_score:
                    best, best_score = a, score
        return best if best_score >= 0.88 else None

    def check_conditions(self, conditions: list[dict], at: Optional[datetime] = None) -> Optional[str]:
        at = at or datetime.now()
        hm = at.strftime("%H:%M")
        for c in conditions:
            cond = Condition.model_validate(c)
            if cond.type == "time_between" and cond.start and cond.end and not _in_range(hm, cond.start, cond.end):
                return f"only runs between {cond.start} and {cond.end}"
            if cond.type == "weekday" and cond.days and at.weekday() not in cond.days:
                return "not scheduled for today"
            if cond.type in ("process_running", "process_not_running") and cond.process:
                running = self.platform.process_running(cond.process if cond.process.lower().endswith(".exe")
                                                        else cond.process + ".exe")
                if cond.type == "process_running" and not running:
                    return f"{cond.process} is not running"
                if cond.type == "process_not_running" and running:
                    return f"{cond.process} is already running"
        return None

    # ------------------------------------------------------------ running
    async def run_by_name(self, name: str, source: str = "ui") -> ActionResult:
        a = self.match_phrase(name)
        if not a:
            names = ", ".join(x["name"] for x in self.list()) or "none defined"
            return ActionResult(False, f"No custom command named '{name}'. Available: {names}.", code="not_found")
        return await self.run(a["id"], source=source)

    async def run(self, aid: str, source: str = "ui") -> ActionResult:
        a = self.get(aid)
        if not a["enabled"]:
            return ActionResult(False, f"'{a['name']}' is disabled.", code="disabled")
        if aid in self._running:
            return ActionResult(False, f"'{a['name']}' is already running.", code="busy")
        blocked = self.check_conditions(a.get("conditions") or [])
        if blocked:
            return ActionResult(False, f"'{a['name']}' did not run: {blocked}.", code="condition_failed")
        ctx = ExecutionContext(source="automation", run_id=f"auto-{aid[:8]}-{int(time.time())}")
        if a.get("confirmation") == "once" or source in ("remote", "schedule"):
            steps_txt = [f"{i + 1}. {s['action']} {json.dumps(s['args'], ensure_ascii=False)}"
                         for i, s in enumerate(a["steps"])]
            ok = await self.confirmations.request(
                action="automation", summary=f"Run custom command '{a['name']}'", risk="medium", source=source,
                details={"steps": steps_txt})
            if not ok:
                return ActionResult(False, f"'{a['name']}' was not approved.", code="not_approved")
            ctx.preapproved = {s["action"] for s in a["steps"]}
        self._running.add(aid)
        self.bus.publish("automation.started", id=aid, name=a["name"], source=source)
        results = []
        try:
            for i, step in enumerate(a["steps"]):
                if step.get("delay_seconds"):
                    await asyncio.sleep(step["delay_seconds"])
                res = await self.engine.execute(step["action"], step.get("args") or {}, ctx)
                results.append({"step": i + 1, "action": step["action"], "ok": res.ok, "message": res.message,
                                "verified": res.verified})
                self.bus.publish("automation.step", id=aid, index=i + 1, total=len(a["steps"]), ok=res.ok,
                                 message=res.message)
                if not res.ok and not step.get("continue_on_error"):
                    break
        finally:
            self._running.discard(aid)
            self.db.execute("UPDATE automations SET last_run_at=? WHERE id=?", (now(), aid))
        good = sum(1 for r in results if r["ok"])
        all_ok = good == len(a["steps"])
        lines = "\n".join(f"{'✅' if r['ok'] else '❌'} {r['message']}" for r in results)
        skipped = len(a["steps"]) - len(results)
        msg = f"'{a['name']}': {good}/{len(a['steps'])} steps succeeded.\n{lines}"
        if skipped:
            msg += f"\n⏭ {skipped} step(s) skipped after a failure."
        self.bus.publish("automation.finished", id=aid, name=a["name"], ok=all_ok)
        return ActionResult(all_ok, msg, data={"results": results}, verified=all_ok or None,
                            code="ok" if all_ok else "partial_failure")

    # ---------------------------------------------------------- scheduler
    def start_scheduler(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop())
            asyncio.create_task(self._startup_triggers())

    async def stop_scheduler(self) -> None:
        if self._task:
            self._task.cancel()
            self._task = None

    async def _startup_triggers(self) -> None:
        await asyncio.sleep(5)
        for a in self.list():
            if a["enabled"] and a["trigger"]["type"] == "startup":
                try:
                    await self.run(a["id"], source="schedule")
                except Exception as exc:
                    log.warning("startup automation failed: %s", exc)

    def due(self, at: datetime) -> list[dict[str, Any]]:
        hm = at.strftime("%H:%M")
        out = []
        for a in self.list():
            t = a["trigger"]
            if not a["enabled"] or t["type"] != "schedule" or t.get("time") != hm:
                continue
            if at.weekday() not in (t.get("days") or list(range(7))):
                continue
            if a.get("last_run_at") and at.timestamp() - a["last_run_at"] < 90:
                continue
            out.append(a)
        return out

    async def _loop(self) -> None:
        while True:
            try:
                for a in self.due(datetime.now()):
                    asyncio.create_task(self.run(a["id"], source="schedule"))
            except Exception as exc:
                log.warning("scheduler error: %s", exc)
            await asyncio.sleep(20)
