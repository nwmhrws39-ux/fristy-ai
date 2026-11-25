"""Ollama (local models) - https://github.com/ollama/ollama/blob/main/docs/api.md"""
from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator

import httpx

from ..types import Message, ModelInfo, ProviderError, StreamEvent, ToolCall, ToolDef
from .base import TIMEOUT, Provider, connect_error

VISION_HINTS = ("llava", "vision", "bakllava", "moondream", "minicpm-v", "qwen2.5vl", "qwen2-vl", "gemma3", "llama4",
                "qwen3-vl", "granite3.2-vision", "mistral-small3")
TOOL_HINTS = ("llama3.1", "llama3.2", "llama3.3", "llama4", "qwen2.5", "qwen3", "mistral", "mixtral", "command-r",
              "firefunction", "hermes3", "granite3", "smollm2", "nemotron", "gpt-oss", "deepseek-r1", "phi4")


class OllamaProvider(Provider):
    id = "ollama"
    local = True

    async def _show(self, client: httpx.AsyncClient, name: str) -> dict:
        try:
            r = await client.post(f"{self.base_url}/api/show", json={"model": name})
            return r.json() if r.status_code == 200 else {}
        except (httpx.HTTPError, ValueError):
            return {}

    async def list_models(self) -> list[ModelInfo]:
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(10.0), trust_env=False) as client:
                r = await client.get(f"{self.base_url}/api/tags")
                await self._raise_for(r, "Ollama")
                models = r.json().get("models", [])
                shows = await asyncio.gather(*(self._show(client, m["name"]) for m in models))
        except httpx.HTTPError as exc:
            raise connect_error("Ollama", self.base_url, exc) from exc
        out = []
        for m, show in zip(models, shows):
            name = m["name"]
            caps = show.get("capabilities")
            lname = name.lower()
            if caps is not None:
                tools, vision = "tools" in caps, "vision" in caps
            else:
                tools = any(h in lname for h in TOOL_HINTS)
                vision = any(h in lname for h in VISION_HINTS)
            if "embed" in lname or (caps is not None and "completion" not in caps):
                continue
            out.append(ModelInfo(id=name, provider=self.id, supports_tools=tools, supports_vision=vision,
                                 local=True, size_gb=round(m.get("size", 0) / 1e9, 1) or None))
        return out

    @staticmethod
    def _convert(messages: list[Message]) -> list[dict]:
        out = []
        for m in messages:
            d: dict = {"role": m.role, "content": m.content or ""}
            if m.images and m.role != "tool":
                d["images"] = m.images
            if m.tool_calls:
                d["tool_calls"] = [{"function": {"name": c.name, "arguments": c.arguments}} for c in m.tool_calls]
            if m.role == "tool":
                d["tool_name"] = m.name or ""
            out.append(d)
            if m.role == "tool" and m.images:
                out.append({"role": "user", "content": f"(Image returned by {m.name})", "images": m.images})
        return out

    async def stream_chat(self, model: str, messages: list[Message], tools: list[ToolDef] | None = None,
                          temperature: float = 0.4, max_tokens: int = 2048) -> AsyncIterator[StreamEvent]:
        body: dict = {"model": model, "messages": self._convert(messages), "stream": True,
                      "options": {"temperature": temperature, "num_predict": max_tokens}}
        if tools:
            body["tools"] = [{"type": "function", "function": {"name": t.name, "description": t.description,
                                                               "parameters": t.parameters}} for t in tools]
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT, trust_env=False) as client:
                async with client.stream("POST", f"{self.base_url}/api/chat", json=body) as resp:
                    await self._raise_for(resp, "Ollama")
                    usage = {}
                    async for line in resp.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            chunk = json.loads(line)
                        except ValueError:
                            continue
                        if chunk.get("error"):
                            raise ProviderError(f"Ollama: {chunk['error']}")
                        msg = chunk.get("message") or {}
                        if msg.get("content"):
                            yield StreamEvent("text", text=msg["content"])
                        for tc in msg.get("tool_calls") or []:
                            fn = tc.get("function", {})
                            args = fn.get("arguments") or {}
                            if isinstance(args, str):
                                try:
                                    args = json.loads(args)
                                except ValueError:
                                    args = {}
                            yield StreamEvent("tool_call", tool_call=ToolCall(name=fn.get("name", ""), arguments=args))
                        if chunk.get("done"):
                            usage = {"input_tokens": chunk.get("prompt_eval_count"),
                                     "output_tokens": chunk.get("eval_count")}
                            yield StreamEvent("done", stop_reason=chunk.get("done_reason"), usage=usage)
                            return
        except httpx.HTTPError as exc:
            raise connect_error("Ollama", self.base_url, exc) from exc
