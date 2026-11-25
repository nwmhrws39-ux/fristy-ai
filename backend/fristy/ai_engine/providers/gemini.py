"""Google Gemini API (generativelanguage.googleapis.com, v1beta)."""
from __future__ import annotations

import json
from typing import AsyncIterator

import httpx

from ..types import Message, ModelInfo, ProviderError, StreamEvent, ToolCall, ToolDef, image_mime
from .base import TIMEOUT, Provider, connect_error


class GeminiProvider(Provider):
    id = "gemini"

    def headers(self) -> dict[str, str]:
        return {"Content-Type": "application/json", "x-goog-api-key": self.api_key or ""}

    def _need_key(self) -> None:
        if not self.api_key:
            raise ProviderError("Gemini API key is not set (Settings > AI).", status=401)

    async def list_models(self) -> list[ModelInfo]:
        self._need_key()
        out: list[ModelInfo] = []
        page = None
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
                for _ in range(5):
                    params = {"pageSize": 100}
                    if page:
                        params["pageToken"] = page
                    r = await client.get(f"{self.base_url}/v1beta/models", headers=self.headers(), params=params)
                    await self._raise_for(r, "Gemini")
                    j = r.json()
                    for m in j.get("models", []):
                        if "generateContent" not in m.get("supportedGenerationMethods", []):
                            continue
                        mid = m["name"].split("/", 1)[-1]
                        if "embedding" in mid or "aqa" in mid or "imagen" in mid:
                            continue
                        out.append(ModelInfo(id=mid, provider=self.id, name=m.get("displayName") or mid,
                                             supports_tools=True, supports_vision=True))
                    page = j.get("nextPageToken")
                    if not page:
                        break
        except httpx.HTTPError as exc:
            raise connect_error("Gemini", self.base_url, exc) from exc
        return out

    @staticmethod
    def _convert(messages: list[Message]) -> tuple[str, list[dict]]:
        system = "\n\n".join(m.content for m in messages if m.role == "system")
        contents: list[dict] = []

        def push(role: str, parts: list[dict]) -> None:
            if contents and contents[-1]["role"] == role:
                contents[-1]["parts"].extend(parts)
            else:
                contents.append({"role": role, "parts": parts})

        for m in messages:
            if m.role == "system":
                continue
            if m.role == "tool":
                try:
                    resp = json.loads(m.content)
                    if not isinstance(resp, dict):
                        resp = {"result": resp}
                except ValueError:
                    resp = {"result": m.content}
                parts: list[dict] = [{"functionResponse": {"name": m.name or "tool", "response": resp}}]
                parts += [{"inline_data": {"mime_type": image_mime(i), "data": i}} for i in m.images]
                push("user", parts)
                continue
            parts = [{"inline_data": {"mime_type": image_mime(i), "data": i}} for i in m.images]
            if m.content:
                parts.append({"text": m.content})
            for c in m.tool_calls:
                p: dict = {"functionCall": {"name": c.name, "args": c.arguments}}
                if c.extra.get("thoughtSignature"):
                    p["thoughtSignature"] = c.extra["thoughtSignature"]
                parts.append(p)
            if not parts:
                parts = [{"text": "(empty)"}]
            push("model" if m.role == "assistant" else "user", parts)
        return system, contents

    async def stream_chat(self, model: str, messages: list[Message], tools: list[ToolDef] | None = None,
                          temperature: float = 0.4, max_tokens: int = 2048) -> AsyncIterator[StreamEvent]:
        self._need_key()
        system, contents = self._convert(messages)
        body: dict = {"contents": contents,
                      "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens}}
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        if tools:
            body["tools"] = [{"functionDeclarations": [
                {"name": t.name, "description": t.description, "parameters": t.parameters} for t in tools]}]
        finish = None
        usage: dict = {}
        url = f"{self.base_url}/v1beta/models/{model}:streamGenerateContent"
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                async with client.stream("POST", url, params={"alt": "sse"}, json=body,
                                         headers=self.headers()) as resp:
                    await self._raise_for(resp, "Gemini")
                    async for _e, data in self.sse_lines(resp):
                        try:
                            chunk = json.loads(data)
                        except ValueError:
                            continue
                        if chunk.get("error"):
                            raise ProviderError(f"Gemini: {chunk['error'].get('message')}")
                        if chunk.get("usageMetadata"):
                            um = chunk["usageMetadata"]
                            usage = {"input_tokens": um.get("promptTokenCount"),
                                     "output_tokens": um.get("candidatesTokenCount")}
                        for cand in chunk.get("candidates") or []:
                            for part in (cand.get("content") or {}).get("parts") or []:
                                if part.get("thought"):
                                    continue
                                if "text" in part and part["text"]:
                                    yield StreamEvent("text", text=part["text"])
                                if "functionCall" in part:
                                    fc = part["functionCall"]
                                    extra = {"thoughtSignature": part["thoughtSignature"]} if part.get(
                                        "thoughtSignature") else {}
                                    yield StreamEvent("tool_call", tool_call=ToolCall(
                                        name=fc.get("name", ""), arguments=fc.get("args") or {}, extra=extra))
                            if cand.get("finishReason"):
                                finish = cand["finishReason"]
                                if finish == "SAFETY":
                                    yield StreamEvent("text", text="\n[Response blocked by Gemini safety filters]")
        except httpx.HTTPError as exc:
            raise connect_error("Gemini", self.base_url, exc) from exc
        yield StreamEvent("done", stop_reason=finish, usage=usage)
