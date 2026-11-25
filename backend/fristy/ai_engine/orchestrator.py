"""Conversation orchestrator: chat mode (tool calling) and agent mode (plan -> approve -> execute -> verify)."""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from ..computer_control.base import ActionError, ActionResult, ExecutionContext
from ..memory.store import extract_learnable
from ..security.sanitize import redact
from .prompts import AGENT_EXEC_PROMPT, AGENT_PLAN_PROMPT, SUMMARY_PROMPT, build_system_prompt
from .quick import claims_action, match_quick
from .types import Message, ProviderError, ToolCall, ToolDef, simplify_schema

log = logging.getLogger(__name__)
MAX_RESULT_CHARS = 6000


@dataclass
class RunState:
    id: str
    conversation_id: str
    mode: str
    source: str
    started_at: float = field(default_factory=time.time)
    status: str = "running"
    resume: asyncio.Event = field(default_factory=asyncio.Event)
    actions: list[dict[str, Any]] = field(default_factory=list)
    plan: Optional[dict[str, Any]] = None

    def __post_init__(self) -> None:
        self.resume.set()

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "conversation_id": self.conversation_id, "mode": self.mode, "source": self.source,
                "status": self.status, "started_at": self.started_at, "actions": self.actions,
                "plan": self.plan, "paused": not self.resume.is_set()}


def result_for_model(res: ActionResult) -> str:
    data = json.dumps(res.data, ensure_ascii=False, default=str)
    if len(data) > MAX_RESULT_CHARS:
        data = data[:MAX_RESULT_CHARS] + '..."(truncated)"'
    return json.dumps({"ok": res.ok, "message": res.message, "verified": res.verified, "code": res.code,
                       "data": data}, ensure_ascii=False)


def extract_json(text: str) -> Optional[dict]:
    text = re.sub(r"```(?:json)?", "", text)
    start = text.find("{")
    while start != -1:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        obj = json.loads(text[start:i + 1])
                        if isinstance(obj, dict):
                            return obj
                    except ValueError:
                        break
                    break
        start = text.find("{", start + 1)
    return None


class Orchestrator:
    def __init__(self, svc):
        self.svc = svc
        self.runs: dict[str, RunState] = {}

    # ------------------------------------------------------------- public
    def start(self, text: str, conversation_id: Optional[str] = None, mode: str = "chat",
              images: Optional[list[str]] = None, source: str = "chat") -> dict[str, str]:
        text = (text or "").strip()
        if not text and not images:
            raise ActionError("Empty message.")
        conv = self.svc.conversations.ensure(conversation_id, text)
        run = RunState(id=uuid.uuid4().hex, conversation_id=conv["id"], mode=mode, source=source)
        self.runs[run.id] = run
        self.svc.stop.clear()
        task = asyncio.create_task(self._run(run, text, images or []))
        self.svc.stop.register(run.id, task)
        return {"run_id": run.id, "conversation_id": conv["id"]}

    def pause(self, run_id: str) -> bool:
        run = self.runs.get(run_id)
        if run and run.status == "running":
            run.resume.clear()
            self._publish("run.status", run, state="paused")
            return True
        return False

    def resume(self, run_id: str) -> bool:
        run = self.runs.get(run_id)
        if run and not run.resume.is_set():
            run.resume.set()
            self._publish("run.status", run, state="executing")
            return True
        return False

    def cancel(self, run_id: str) -> bool:
        return self.svc.stop.cancel(run_id)

    def active(self) -> list[dict[str, Any]]:
        return [r.to_dict() for r in self.runs.values() if r.status in ("running",)]

    # ------------------------------------------------------------ helpers
    def _publish(self, type_: str, run: RunState, **data) -> None:
        self.svc.bus.publish(type_, run_id=run.id, conversation_id=run.conversation_id, **data)

    def _orb(self, state: str) -> None:
        self.svc.bus.publish("orb.state", state=state)

    def tools(self) -> list[ToolDef]:
        eng = self.svc.engine
        perms = self.svc.settings.current.permissions
        out = []
        for spec in self.svc.registry.all():
            if not spec.ai_visible:
                continue
            if spec.permission and not perms.get(spec.permission):
                continue
            if spec.windows_only and not eng.is_windows:
                continue
            out.append(ToolDef(spec.name, spec.description, simplify_schema(spec.tool_schema())))
        return out

    def _disabled_note(self) -> str:
        perms = self.svc.settings.current.permissions
        off = [p for p, v in perms.items() if not v]
        note = ""
        if off:
            note += ("\nThese permissions are currently DISABLED by the user, so related actions are unavailable: "
                     + ", ".join(off) + ". If asked, explain they can enable them in Settings > Permissions.")
        if not self.svc.engine.is_windows:
            note += "\nNote: this backend is not running on Windows, so Windows-only actions are unavailable."
        return note

    def _system(self) -> Message:
        st = self.svc.settings.current
        mem = self.svc.memory.context_block() if st.memory.enabled else ""
        return Message("system", build_system_prompt(st, mem) + self._disabled_note())

    def _history(self, conversation_id: str) -> list[Message]:
        n = self.svc.settings.current.ai.history_messages
        msgs: list[Message] = []
        conv = self.svc.conversations.get(conversation_id)
        if conv and conv.get("summary"):
            msgs.append(Message("user", f"(Summary of earlier conversation: {conv['summary']})"))
            msgs.append(Message("assistant", "Understood."))
        for row in self.svc.conversations.messages(conversation_id, limit=n):
            if row["role"] not in ("user", "assistant"):
                continue
            content = row["content"]
            meta = row.get("meta") or {}
            if row["role"] == "assistant" and meta.get("actions"):
                acts = "; ".join(f"{a['name']} -> {'ok' if a['ok'] else 'FAILED'}: {a['message']}"
                                 for a in meta["actions"])
                content = f"{content}\n[Actions executed in this turn: {acts}]"
            msgs.append(Message(row["role"], content))
        return msgs

    async def _wait_if_paused(self, run: RunState) -> None:
        if not run.resume.is_set():
            self._orb("idle")
            await run.resume.wait()
            self._orb("executing")

    async def _exec(self, run: RunState, ctx: ExecutionContext, call: ToolCall) -> ActionResult:
        self._orb("executing")
        self._publish("chat.tool", run, call={"id": call.id, "name": call.name, "arguments": call.arguments})
        if "__invalid_json__" in call.arguments:
            res = ActionResult(False, "The tool arguments were not valid JSON.", code="invalid_arguments")
        else:
            res = await self.svc.engine.execute(call.name, call.arguments, ctx)
        entry = {"id": call.id, "name": call.name, "arguments": call.arguments, "ok": res.ok,
                 "message": res.message, "verified": res.verified, "code": res.code}
        run.actions.append(entry)
        self._publish("chat.tool_result", run, result={**entry, "data": _ui_data(res)})
        self._orb("thinking")
        return res

    # ---------------------------------------------------------------- run
    async def _run(self, run: RunState, text: str, images: list[str]) -> None:
        svc = self.svc
        self._publish("run.started", run, mode=run.mode, cloud=svc.ai.is_cloud(),
                      provider=svc.settings.current.ai.provider, model=svc.ai.active_model())
        self._orb("thinking")
        svc.conversations.add_message(run.conversation_id, "user", text,
                                      {"images": len(images), "mode": run.mode, "source": run.source})
        final_text = ""
        warning = None
        try:
            self._learn(text)
            handled = await self._try_local(run, text) if not images else None
            if handled is not None:
                final_text = handled
            elif run.mode == "agent":
                final_text = await self._agent(run, text, images)
            else:
                final_text = await self._chat(run, text, images)
            if claims_action(final_text) and not any(a["ok"] for a in run.actions):
                warning = "no_action_executed"
            run.status = "completed"
        except asyncio.CancelledError:
            run.status = "cancelled"
            final_text = (final_text + "\n\n" if final_text else "") + "⏹ Stopped."
            self._publish("run.cancelled", run)
        except ProviderError as exc:
            run.status = "error"
            final_text = f"⚠️ {exc}"
            self._publish("run.error", run, error=str(exc))
            self._orb("error")
        except Exception as exc:
            log.exception("run failed")
            run.status = "error"
            final_text = f"⚠️ Internal error: {type(exc).__name__}: {exc}"
            self._publish("run.error", run, error=final_text)
            self._orb("error")
        finally:
            meta = {"actions": run.actions, "mode": run.mode, "warning": warning,
                    "provider": svc.settings.current.ai.provider, "model": svc.ai.active_model(),
                    "latency_ms": svc.ai.last_latency_ms, "plan": run.plan}
            mid = svc.conversations.add_message(run.conversation_id, "assistant", final_text, meta)
            self._publish("chat.done", run, message_id=mid, text=final_text, actions=run.actions, warning=warning,
                          status=run.status)
            if run.status != "error":
                self._orb("idle")
            for rid in [r.id for r in self.runs.values() if r.status != "running"][:-20]:
                self.runs.pop(rid, None)
            asyncio.create_task(self._maybe_summarize(run.conversation_id))

    def _learn(self, text: str) -> None:
        st = self.svc.settings.current.memory
        if not (st.enabled and st.auto_learn):
            return
        for cat, key, value in extract_learnable(text):
            try:
                self.svc.memory.upsert(cat, key, value, source="auto")
                self.svc.bus.publish("memory.learned", category=cat, key=key)
            except ActionError:
                pass

    async def _try_local(self, run: RunState, text: str) -> Optional[str]:
        """Custom commands and fast offline intents (no AI round-trip)."""
        if self.svc.automations is not None:
            auto = self.svc.automations.match_phrase(text)
            if auto:
                self._orb("executing")
                res = await self.svc.automations.run(auto["id"], source=run.source)
                run.actions.append({"id": "auto", "name": "run_custom_command", "arguments": {"name": auto["name"]},
                                    "ok": res.ok, "message": res.message, "verified": res.verified, "code": res.code})
                self._publish("chat.tool_result", run, result=run.actions[-1])
                return res.message
        if not self.svc.settings.current.ai.fast_local_commands:
            return None
        quick = match_quick(text)
        if not quick:
            return None
        name, args = quick
        spec = self.svc.registry.get(name)
        if spec is None:
            return None
        try:
            self.svc.engine.validate(name, args)
        except ActionError:
            return None  # let the AI explain (e.g. permission disabled / unsupported)
        if name == "launch_app":
            from ..computer_control.platform.base import match_apps

            try:
                apps = await asyncio.to_thread(self.svc.platform.list_apps)
            except ActionError:
                return None
            matches = match_apps(args["name"], apps, limit=2)
            if not matches or matches[0][0] < 0.8 or (len(matches) > 1 and matches[1][0] == matches[0][0]):
                return None  # not a confident local match: let the AI handle it
        ctx = ExecutionContext(source="voice" if run.source == "voice" else "chat", run_id=run.id)
        res = await self._exec(run, ctx, ToolCall(name=name, arguments=args))
        return res.message

    async def _stream_turn(self, run: RunState, messages: list[Message], tools: list[ToolDef] | None):
        text_parts: list[str] = []
        calls: list[ToolCall] = []
        async for ev in self.svc.ai.stream(messages, tools):
            if ev.kind == "text" and ev.text:
                text_parts.append(ev.text)
                self._publish("chat.delta", run, text=ev.text)
            elif ev.kind == "tool_call" and ev.tool_call:
                calls.append(ev.tool_call)
        return "".join(text_parts), calls

    async def _tool_loop(self, run: RunState, messages: list[Message], ctx: ExecutionContext, max_calls: int,
                         deadline: Optional[float] = None, max_failures: Optional[int] = None) -> str:
        tools = self.tools() if max_calls > 0 else None
        used, failures = 0, 0
        vision = self.svc.ai.supports_vision()
        text = ""
        while True:
            await self._wait_if_paused(run)
            text, calls = await self._stream_turn(run, messages, tools if used < max_calls else None)
            if not calls:
                return text
            if used >= max_calls:
                return text
            messages.append(Message("assistant", text, tool_calls=calls))
            for call in calls:
                if deadline and time.time() > deadline:
                    messages.append(Message("tool", json.dumps({"ok": False, "message": "Time limit reached."}),
                                            tool_call_id=call.id, name=call.name))
                    continue
                if used >= max_calls:
                    messages.append(Message("tool", json.dumps({"ok": False, "message": "Action limit reached; "
                                                                "not executed."}), tool_call_id=call.id, name=call.name))
                    continue
                await self._wait_if_paused(run)
                used += 1
                res = await self._exec(run, ctx, call)
                if not res.ok:
                    failures += 1
                imgs = [res.image_b64] if res.image_b64 and vision else []
                content = result_for_model(res)
                if res.image_b64 and not vision:
                    content += ' (Screenshot captured but the selected model cannot see images; rely on ui_elements.)'
                messages.append(Message("tool", content, images=imgs, tool_call_id=call.id, name=call.name))
                self._publish("agent.step", run, index=used, name=call.name, ok=res.ok, message=res.message,
                              verified=res.verified, limit=max_calls)
            if max_failures is not None and failures > max_failures:
                messages.append(Message("user", "Too many steps failed. Stop now and report to the user what "
                                                "succeeded and what failed."))
                tools = None
            if deadline and time.time() > deadline:
                messages.append(Message("user", "The time limit was reached. Stop and report."))
                tools = None

    async def _chat(self, run: RunState, text: str, images: list[str]) -> str:
        messages = [self._system()] + self._history(run.conversation_id)
        # history already contains the user message we just stored; attach images to it
        if images and messages and messages[-1].role == "user":
            messages[-1].images = images
        ctx = ExecutionContext(source="voice" if run.source == "voice" else "chat", run_id=run.id)
        limit = self.svc.settings.current.agent.chat_max_tool_calls
        return await self._tool_loop(run, messages, ctx, limit)

    # -------------------------------------------------------------- agent
    async def make_plan(self, text: str) -> dict[str, Any]:
        st = self.svc.settings.current
        catalog = "\n".join(f"- {t.name}: {t.description} args={json.dumps(t.parameters.get('properties', {}))}"
                            for t in self.tools())
        prompt = AGENT_PLAN_PROMPT.format(catalog=catalog or "(no actions enabled)", max_steps=st.agent.max_steps)
        mem = self.svc.memory.context_block() if st.memory.enabled else ""
        msgs = [Message("system", prompt + (f"\nUser preferences:\n{mem}" if mem else "") + self._disabled_note()),
                Message("user", text)]
        raw = await self.svc.ai.complete(msgs)
        plan = extract_json(raw)
        if plan is None or not isinstance(plan.get("steps", []), list):
            raise ProviderError("The AI model did not return a valid plan. Try rephrasing, or use a stronger model.")
        steps = []
        for s in plan.get("steps", [])[: st.agent.max_steps]:
            if not isinstance(s, dict):
                continue
            name, args = str(s.get("action", "")), s.get("args") or {}
            entry = {"action": name, "args": args if isinstance(args, dict) else {},
                     "description": str(s.get("description", ""))[:300], "valid": True, "error": None,
                     "risk": None, "needs_confirmation": False}
            try:
                spec, parsed = self.svc.engine.validate(name, entry["args"])
                entry["risk"] = spec.risk.value
                entry["summary"] = spec.summary(parsed)
                entry["needs_confirmation"] = spec.risk.value == "high" or spec.confirm == "always"
            except ActionError as exc:
                entry["valid"], entry["error"] = False, str(exc)
            steps.append(entry)
        return {"summary": str(plan.get("summary", ""))[:1000], "steps": steps}

    async def _agent(self, run: RunState, text: str, images: list[str]) -> str:
        st = self.svc.settings.current.agent
        self._publish("run.status", run, state="planning")
        plan = await self.make_plan(text)
        run.plan = plan
        self._publish("agent.plan", run, plan=plan)
        steps = plan["steps"]
        valid = [s for s in steps if s["valid"]]
        invalid = [s for s in steps if not s["valid"]]
        if not steps:
            return plan["summary"] or "No computer actions are needed for that."
        if not valid:
            return "I can't perform this plan:\n" + "\n".join(f"• {s['action']}: {s['error']}" for s in invalid)
        if st.require_plan_approval:
            approved = await self.svc.confirmations.request(
                action="agent_plan", summary=plan["summary"] or text, risk=max(
                    (s["risk"] for s in valid), key=lambda r: ["low", "medium", "high"].index(r)),
                source="agent", details={"plan": plan, "run_id": run.id})
            self.svc.audit.record("agent.plan", source="agent", status="approved" if approved else "denied",
                                  detail={"summary": plan["summary"], "steps": [s["action"] for s in valid]})
            if not approved:
                return "Plan cancelled - nothing was executed."
        ctx = ExecutionContext(source="agent", run_id=run.id, preapproved={s["action"] for s in valid})
        plan_text = "\n".join(f"{i + 1}. {s['action']} {json.dumps(s['args'], ensure_ascii=False)} - {s['description']}"
                              for i, s in enumerate(valid))
        if invalid:
            plan_text += "\nSkipped (not allowed): " + ", ".join(s["action"] for s in invalid)
        messages = [self._system(), Message("system", AGENT_EXEC_PROMPT.format(plan=plan_text)),
                    Message("user", text, images=images)]
        deadline = time.time() + st.max_duration_seconds
        self._publish("run.status", run, state="executing")
        summary = await self._tool_loop(run, messages, ctx, max_calls=min(st.max_steps + st.max_recovery_attempts, 25),
                                        deadline=deadline, max_failures=st.max_recovery_attempts)
        return self._report(run, summary, invalid)

    @staticmethod
    def _report(run: RunState, model_summary: str, invalid: list[dict]) -> str:
        lines = []
        for a in run.actions:
            icon = "✅" if a["ok"] and a["verified"] is not False else ("⚠️" if a["ok"] else "❌")
            note = "" if a["verified"] or not a["ok"] else " (not verified)"
            lines.append(f"{icon} {a['message']}{note}")
        for s in invalid:
            lines.append(f"⛔ Skipped {s['action']}: {s['error']}")
        report = "\n".join(lines) if lines else "No actions were executed."
        return (model_summary.strip() + "\n\n" if model_summary.strip() else "") + "**Execution report**\n" + report

    async def _maybe_summarize(self, conversation_id: str) -> None:
        st = self.svc.settings.current.memory
        if not (st.enabled and st.summarize_conversations):
            return
        n = self.svc.conversations.count(conversation_id)
        if n < 20 or n % 20 not in (0, 1):
            return
        try:
            rows = self.svc.conversations.messages(conversation_id, limit=60)
            transcript = "\n".join(f"{r['role']}: {r['content'][:800]}" for r in rows)
            summary = await self.svc.ai.complete([Message("system", SUMMARY_PROMPT), Message("user", transcript)])
            summary = redact(summary.strip())[:3000]
            if summary:
                self.svc.conversations.set_summary(conversation_id, summary)
                conv = self.svc.conversations.get(conversation_id)
                self.svc.memory.upsert("conversation_summary", f"{conv['title']} ({conversation_id[:8]})", summary,
                                       source="auto")
        except Exception as exc:
            log.info("summary skipped: %s", exc)


def _ui_data(res: ActionResult) -> dict[str, Any]:
    s = json.dumps(res.data, ensure_ascii=False, default=str)
    if len(s) > 20000:
        return {"truncated": True, "preview": s[:20000]}
    return res.data
