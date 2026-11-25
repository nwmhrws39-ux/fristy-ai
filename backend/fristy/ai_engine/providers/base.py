"""Provider base class with shared HTTP helpers."""
from __future__ import annotations

import json
from typing import Any, AsyncIterator, Optional

import httpx

from ..types import Message, ModelInfo, ProviderError, StreamEvent, ToolDef

TIMEOUT = httpx.Timeout(connect=10.0, read=180.0, write=30.0, pool=10.0)


class Provider:
    id = "base"
    local = False

    def __init__(self, base_url: str, api_key: Optional[str] = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def headers(self) -> dict[str, str]:
        return {"Content-Type": "application/json"}

    async def list_models(self) -> list[ModelInfo]:
        raise NotImplementedError

    def stream_chat(self, model: str, messages: list[Message], tools: list[ToolDef] | None = None,
                    temperature: float = 0.4, max_tokens: int = 2048) -> AsyncIterator[StreamEvent]:
        raise NotImplementedError

    async def health(self) -> dict[str, Any]:
        try:
            models = await self.list_models()
            return {"ok": True, "models": len(models)}
        except ProviderError as exc:
            return {"ok": False, "error": str(exc)}

    # ------------------------------------------------------------ helpers
    @staticmethod
    async def _raise_for(resp: httpx.Response, provider: str) -> None:
        if resp.status_code < 400:
            return
        body = (await resp.aread()).decode("utf-8", "replace")[:800]
        try:
            j = json.loads(body)
            err = j.get("error")
            msg = (err.get("message") if isinstance(err, dict) else err) or j.get("message") or body
        except ValueError:
            msg = body
        hints = {401: "invalid or missing API key", 403: "access denied", 404: "model or endpoint not found",
                 429: "rate limited or quota exceeded"}
        hint = hints.get(resp.status_code)
        raise ProviderError(f"{provider} error {resp.status_code}{f' ({hint})' if hint else ''}: {msg}",
                            status=resp.status_code, retryable=resp.status_code in (429, 500, 502, 503, 529))

    @staticmethod
    async def sse_lines(resp: httpx.Response) -> AsyncIterator[tuple[str, str]]:
        """Yield (event, data) pairs from a server-sent-events stream."""
        event, data_lines = "message", []
        async for line in resp.aiter_lines():
            if line == "":
                if data_lines:
                    yield event, "\n".join(data_lines)
                event, data_lines = "message", []
                continue
            if line.startswith(":"):
                continue
            if line.startswith("event:"):
                event = line[6:].strip()
            elif line.startswith("data:"):
                data_lines.append(line[5:].lstrip())
        if data_lines:
            yield event, "\n".join(data_lines)


def connect_error(provider: str, base_url: str, exc: Exception) -> ProviderError:
    if provider == "Ollama":
        return ProviderError(f"Cannot reach Ollama at {base_url}. Is Ollama installed and running? "
                             f"(https://ollama.com) [{type(exc).__name__}]", retryable=True)
    return ProviderError(f"Cannot reach {provider} at {base_url}: {type(exc).__name__}: {exc}", retryable=True)
