"""Provider-neutral chat types."""
from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal, Optional

Role = Literal["system", "user", "assistant", "tool"]


@dataclass
class ToolCall:
    name: str
    arguments: dict[str, Any]
    id: str = field(default_factory=lambda: "call_" + uuid.uuid4().hex[:16])
    # Provider-specific data that must be echoed back (e.g. Gemini thought signatures).
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class Message:
    role: Role
    content: str = ""
    images: list[str] = field(default_factory=list)  # base64 JPEG/PNG
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_call_id: Optional[str] = None
    name: Optional[str] = None  # tool name for role=tool


@dataclass
class ToolDef:
    name: str
    description: str
    parameters: dict[str, Any]


@dataclass
class StreamEvent:
    kind: Literal["text", "tool_call", "done", "error"]
    text: str = ""
    tool_call: Optional[ToolCall] = None
    stop_reason: Optional[str] = None
    usage: dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelInfo:
    id: str
    provider: str
    name: str = ""
    supports_tools: Optional[bool] = None
    supports_vision: Optional[bool] = None
    local: bool = False
    size_gb: Optional[float] = None

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "provider": self.provider, "name": self.name or self.id,
                "supports_tools": self.supports_tools, "supports_vision": self.supports_vision,
                "local": self.local, "size_gb": self.size_gb}


class ProviderError(Exception):
    def __init__(self, message: str, status: int | None = None, retryable: bool = False):
        super().__init__(message)
        self.status = status
        self.retryable = retryable


def image_mime(b64: str) -> str:
    return "image/png" if b64.startswith("iVBOR") else "image/jpeg"


_KEEP = {"type", "description", "enum", "properties", "required", "items", "minimum", "maximum",
         "minLength", "maxLength", "minItems", "maxItems", "format", "nullable"}


def simplify_schema(schema: dict[str, Any], allow_additional: bool = True) -> dict[str, Any]:
    """Normalise a pydantic JSON schema to the portable subset all providers accept."""
    defs = schema.get("$defs", {})

    def walk(node: Any) -> Any:
        if not isinstance(node, dict):
            return node
        if "$ref" in node:
            ref = node["$ref"].split("/")[-1]
            return walk(defs.get(ref, {}))
        if "anyOf" in node:
            variants = [v for v in node["anyOf"] if v.get("type") != "null"]
            nullable = len(variants) != len(node["anyOf"])
            base = walk(variants[0]) if variants else {"type": "string"}
            if nullable:
                base["nullable"] = True
            if "description" in node:
                base["description"] = node["description"]
            return base
        if "const" in node:
            node = {**node, "enum": [node["const"]]}
        out: dict[str, Any] = {}
        for k, v in node.items():
            if k == "properties":
                out[k] = {pk: walk(pv) for pk, pv in v.items()}
            elif k == "items":
                out[k] = walk(v)
            elif k == "additionalProperties" and allow_additional and isinstance(v, dict):
                out[k] = walk(v)
            elif k in _KEEP:
                out[k] = v
        if "enum" in out and "type" not in out:
            out["type"] = "string"
        if out.get("type") == "object" and "properties" not in out and not allow_additional:
            out["properties"] = {}
        return out

    result = walk(schema)
    result.setdefault("type", "object")
    result.setdefault("properties", {})
    return result


_ACTION_TAG = re.compile(r"<action>\s*(\{.*?\})\s*</action>", re.DOTALL)
_FENCE = re.compile(r"```(?:json|action)?\s*(\{[^`]*?\"name\"[^`]*?\})\s*```", re.DOTALL)


def parse_text_tool_calls(text: str, known: set[str]) -> tuple[str, list[ToolCall]]:
    """Fallback protocol for models without native tool calling.

    The model is asked to emit ``<action>{"name": ..., "arguments": {...}}</action>``.
    Returns the text with action blocks removed and the parsed calls. Unknown
    tool names are ignored (the engine would reject them anyway).
    """
    calls: list[ToolCall] = []
    spans = []
    for pat in (_ACTION_TAG, _FENCE):
        for m in pat.finditer(text):
            try:
                obj = json.loads(m.group(1))
            except ValueError:
                continue
            name = obj.get("name") or obj.get("tool")
            args = obj.get("arguments") or obj.get("args") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except ValueError:
                    args = {}
            if name in known and isinstance(args, dict):
                calls.append(ToolCall(name=name, arguments=args))
                spans.append(m.span())
        if calls:
            break
    cleaned = text
    for start, end in sorted(spans, reverse=True):
        cleaned = cleaned[:start] + cleaned[end:]
    return cleaned.strip(), calls
