"""OpenAI Chat Completions API and compatible servers (LM Studio, vLLM, llama.cpp, OpenRouter...)."""
from __future__ import annotations

import json
import re
from typing import AsyncIterator

import httpx

from ..types import Message, ModelInfo, ProviderError, StreamEvent, ToolCall, ToolDef, image_mime
from .base import TIMEOUT, Provider, connect_error

NON_CHAT = re.compile(r"(embedding|whisper|tts|dall-e|davinci|babbage|moderation|image|audio|realtime|transcribe|search)")
REASONING = re.compile(r"^(o\d|gpt-5)")


class OpenAICompatProvider(Provider):
    id = "openai"

    def __init__(self, base_url: str, api_key: str | None = None, provider_id: str = "openai"):
        super().__init__(base_url, api_key)
        self.id = provider_id
        self.local = provider_id == "custom" and ("127.0.0.1" in base_url or "localhost" in base_url)

    def headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    @property
    def official(self) -> bool:
        return "api.openai.com" in self.base_url

    async def list_models(self) -> list[ModelInfo]:
        if self.official and not self.api_key:
            raise ProviderError("OpenAI API key is not set (Settings > AI).", status=401)
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(15.0), trust_env=not self.local) as client:
                r = await client.get(f"{self.base_url}/models", headers=self.headers())
                await self._raise_for(r, self.id)
                data = r.json().get("data", [])
        except httpx.HTTPError as exc:
            raise connect_error(self.id, self.base_url, exc) from exc
        out = []
        for m in data:
            mid = m.get("id", "")
            if self.official and (NON_CHAT.search(mid) or not re.match(r"^(gpt|o\d|chatgpt)", mid)):
                continue
            vision = True if self.official and re.match(r"^(gpt-4o|gpt-4\.1|gpt-5|o\d|chatgpt-4o)", mid) else None
            out.append(ModelInfo(id=mid, provider=self.id, supports_tools=True if self.official else None,
                                 supports_vision=vision, local=self.local))
        out.sort(key=lambda x: x.id)
        return out

    @staticmethod
    def _convert(messages: list[Message]) -> list[dict]:
        out: list[dict] = []
        for m in messages:
            if m.role == "tool":
                out.append({"role": "tool", "tool_call_id": m.tool_call_id, "content": m.content})
                if m.images:
                    out.append({"role": "user", "content": [{"type": "text", "text": f"(Image returned by {m.name})"}] +
                                [{"type": "image_url", "image_url": {"url": f"data:{image_mime(i)};base64,{i}"}}
                                 for i in m.images]})
                continue
            if m.images:
                content = [{"type": "text", "text": m.content or ""}] + [
                    {"type": "image_url", "image_url": {"url": f"data:{image_mime(i)};base64,{i}"}} for i in m.images]
            else:
                content = m.content or ""
            d: dict = {"role": m.role, "content": content}
            if m.tool_calls:
                d["content"] = m.content or None
                d["tool_calls"] = [{"id": c.id, "type": "function",
                                    "function": {"name": c.name, "arguments": json.dumps(c.arguments)}}
                                   for c in m.tool_calls]
            out.append(d)
        return out

    def _body(self, model, messages, tools, temperature, max_tokens, include_temperature=True) -> dict:
        body: dict = {"model": model, "messages": self._convert(messages), "stream": True}
        if self.official:
            body["max_completion_tokens"] = max_tokens
            body["stream_options"] = {"include_usage": True}
            if include_temperature and not REASONING.match(model):
                body["temperature"] = temperature
        else:
            body["max_tokens"] = max_tokens
            if include_temperature:
                body["temperature"] = temperature
        if tools:
            body["tools"] = [{"type": "function", "function": {"name": t.name, "description": t.description,
                                                               "parameters": t.parameters}} for t in tools]
        return body

    async def stream_chat(self, model: str, messages: list[Message], tools: list[ToolDef] | None = None,
                          temperature: float = 0.4, max_tokens: int = 2048) -> AsyncIterator[StreamEvent]:
        if self.official and not self.api_key:
            raise ProviderError("OpenAI API key is not set (Settings > AI).", status=401)
        include_temp = True
        for attempt in range(2):
            body = self._body(model, messages, tools, temperature, max_tokens, include_temp)
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
        calls: dict[int, dict] = {}
        finish = None
        usage: dict = {}
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT, trust_env=not self.local) as client:
                async with client.stream("POST", f"{self.base_url}/chat/completions", json=body,
                                         headers=self.headers()) as resp:
                    await self._raise_for(resp, self.id)
                    async for _event, data in self.sse_lines(resp):
                        if data.strip() == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                        except ValueError:
                            continue
                        if chunk.get("error"):
                            raise ProviderError(f"{self.id}: {chunk['error'].get('message', chunk['error'])}")
                        if chunk.get("usage"):
                            usage = {"input_tokens": chunk["usage"].get("prompt_tokens"),
                                     "output_tokens": chunk["usage"].get("completion_tokens")}
                        for choice in chunk.get("choices") or []:
                            delta = choice.get("delta") or {}
                            if delta.get("content"):
                                yield StreamEvent("text", text=delta["content"])
                            for tc in delta.get("tool_calls") or []:
                                slot = calls.setdefault(tc.get("index", 0), {"id": None, "name": "", "args": ""})
                                if tc.get("id"):
                                    slot["id"] = tc["id"]
                                fn = tc.get("function") or {}
                                if fn.get("name"):
                                    slot["name"] += fn["name"]
                                if fn.get("arguments"):
                                    slot["args"] += fn["arguments"]
                            if choice.get("finish_reason"):
                                finish = choice["finish_reason"]
        except httpx.HTTPError as exc:
            raise connect_error(self.id, self.base_url, exc) from exc
        for idx in sorted(calls):
            c = calls[idx]
            try:
                args = json.loads(c["args"]) if c["args"].strip() else {}
            except ValueError:
                args = {"__invalid_json__": c["args"][:500]}
            tc = ToolCall(name=c["name"], arguments=args if isinstance(args, dict) else {})
            if c["id"]:
                tc.id = c["id"]
            yield StreamEvent("tool_call", tool_call=tc)
        yield StreamEvent("done", stop_reason=finish, usage=usage)
