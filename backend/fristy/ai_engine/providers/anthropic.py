"""Anthropic Messages API - https://docs.anthropic.com/en/api/messages"""
from __future__ import annotations

import json
from typing import AsyncIterator

import httpx

from ..types import Message, ModelInfo, ProviderError, StreamEvent, ToolCall, ToolDef, image_mime
from .base import TIMEOUT, Provider, connect_error

API_VERSION = "2023-06-01"


class AnthropicProvider(Provider):
    id = "anthropic"

    def headers(self) -> dict[str, str]:
        return {"Content-Type": "application/json", "x-api-key": self.api_key or "",
                "anthropic-version": API_VERSION}

    def _need_key(self) -> None:
        if not self.api_key:
            raise ProviderError("Anthropic API key is not set (Settings > AI).", status=401)

    async def list_models(self) -> list[ModelInfo]:
        self._need_key()
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
                r = await client.get(f"{self.base_url}/v1/models", headers=self.headers(), params={"limit": 100})
                await self._raise_for(r, "Anthropic")
                data = r.json().get("data", [])
        except httpx.HTTPError as exc:
            raise connect_error("Anthropic", self.base_url, exc) from exc
        return [ModelInfo(id=m["id"], provider=self.id, name=m.get("display_name") or m["id"], supports_tools=True,
                          supports_vision=True) for m in data]

    @staticmethod
    def _convert(messages: list[Message]) -> tuple[str, list[dict]]:
        system = "\n\n".join(m.content for m in messages if m.role == "system")
        out: list[dict] = []

        def push(role: str, blocks: list[dict]) -> None:
            if out and out[-1]["role"] == role:
                out[-1]["content"].extend(blocks)
            else:
                out.append({"role": role, "content": blocks})

        for m in messages:
            if m.role == "system":
                continue
            if m.role == "tool":
                content: list[dict] = [{"type": "text", "text": m.content or "(empty)"}]
                content += [{"type": "image", "source": {"type": "base64", "media_type": image_mime(i), "data": i}}
                            for i in m.images]
                push("user", [{"type": "tool_result", "tool_use_id": m.tool_call_id, "content": content}])
                continue
            blocks: list[dict] = []
            for i in m.images:
                blocks.append({"type": "image", "source": {"type": "base64", "media_type": image_mime(i), "data": i}})
            if m.content:
                blocks.append({"type": "text", "text": m.content})
            for c in m.tool_calls:
                blocks.append({"type": "tool_use", "id": c.id, "name": c.name, "input": c.arguments})
            if not blocks:
                blocks = [{"type": "text", "text": "(empty)"}]
            push("assistant" if m.role == "assistant" else "user", blocks)
        if out and out[0]["role"] != "user":
            out.insert(0, {"role": "user", "content": [{"type": "text", "text": "(conversation start)"}]})
        return system, out

    async def stream_chat(self, model: str, messages: list[Message], tools: list[ToolDef] | None = None,
                          temperature: float = 0.4, max_tokens: int = 2048) -> AsyncIterator[StreamEvent]:
        self._need_key()
        system, msgs = self._convert(messages)
        include_temp = True
        for attempt in range(2):
            body: dict = {"model": model, "max_tokens": max_tokens, "messages": msgs, "stream": True}
            if include_temp:
                body["temperature"] = min(temperature, 1.0)
            if system:
                body["system"] = system
            if tools:
                body["tools"] = [{"name": t.name, "description": t.description, "input_schema": t.parameters}
                                 for t in tools]
            try:
                async for ev in self._stream(body):
                    yield ev
                return
            except ProviderError as exc:
                if attempt == 0 and exc.status == 400 and "temperature" in str(exc).lower():
                    include_temp = False
                    continue
                raise

    async def _stream(self, body: dict) -> AsyncIterator[StreamEvent]:
        blocks: dict[int, dict] = {}
        stop_reason = None
        usage: dict = {}
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                async with client.stream("POST", f"{self.base_url}/v1/messages", json=body,
                                         headers=self.headers()) as resp:
                    await self._raise_for(resp, "Anthropic")
                    async for event, data in self.sse_lines(resp):
                        try:
                            ev = json.loads(data)
                        except ValueError:
                            continue
                        t = ev.get("type", event)
                        if t == "error":
                            err = ev.get("error", {})
                            raise ProviderError(f"Anthropic: {err.get('message', err)}",
                                                retryable=err.get("type") == "overloaded_error")
                        if t == "message_start":
                            u = ev.get("message", {}).get("usage", {})
                            usage["input_tokens"] = u.get("input_tokens")
                        elif t == "content_block_start":
                            cb = ev.get("content_block", {})
                            blocks[ev["index"]] = {"type": cb.get("type"), "id": cb.get("id"), "name": cb.get("name"),
                                                   "json": ""}
                        elif t == "content_block_delta":
                            d = ev.get("delta", {})
                            if d.get("type") == "text_delta":
                                yield StreamEvent("text", text=d.get("text", ""))
                            elif d.get("type") == "input_json_delta":
                                blocks.setdefault(ev["index"], {"type": "tool_use", "json": ""})["json"] += \
                                    d.get("partial_json", "")
                        elif t == "content_block_stop":
                            b = blocks.get(ev["index"])
                            if b and b["type"] == "tool_use":
                                try:
                                    args = json.loads(b["json"]) if b["json"].strip() else {}
                                except ValueError:
                                    args = {}
                                yield StreamEvent("tool_call", tool_call=ToolCall(name=b["name"], arguments=args,
                                                                                  id=b["id"]))
                        elif t == "message_delta":
                            stop_reason = ev.get("delta", {}).get("stop_reason") or stop_reason
                            usage["output_tokens"] = ev.get("usage", {}).get("output_tokens")
        except httpx.HTTPError as exc:
            raise connect_error("Anthropic", self.base_url, exc) from exc
        yield StreamEvent("done", stop_reason=stop_reason, usage=usage)
