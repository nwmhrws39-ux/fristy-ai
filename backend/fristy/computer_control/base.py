"""Core types for the restricted action system."""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Literal, Optional, Type

from pydantic import BaseModel


class Risk(str, enum.Enum):
    LOW = "low"  # read-only or trivially reversible (volume, list windows)
    MEDIUM = "medium"  # changes state but is reversible (move a file, click a button)
    HIGH = "high"  # destructive, sensitive or hard to undo (delete, shutdown, terminal)


Source = Literal["ui", "chat", "agent", "automation", "voice", "remote", "test"]


class ActionError(Exception):
    """Expected failure with a user-facing message."""

    def __init__(self, message: str, code: str = "action_failed"):
        super().__init__(message)
        self.code = code


class UnsupportedPlatform(ActionError):
    def __init__(self, what: str):
        super().__init__(f"{what} is only supported on Windows 10/11.", code="unsupported_platform")


@dataclass
class ActionResult:
    ok: bool
    message: str
    data: dict[str, Any] = field(default_factory=dict)
    # True: outcome was checked and confirmed. False: check ran and failed.
    # None: the outcome could not be verified automatically.
    verified: Optional[bool] = None
    code: str = "ok"
    # Content that originated outside the user (files, screen, web).
    untrusted: bool = False
    image_b64: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "message": self.message,
            "data": self.data,
            "verified": self.verified,
            "code": self.code,
            "untrusted": self.untrusted,
            "has_image": self.image_b64 is not None,
        }


@dataclass
class ExecutionContext:
    source: Source = "ui"
    run_id: Optional[str] = None
    # Set once the conversation/agent has ingested untrusted content; from then
    # on every state-changing action needs explicit confirmation.
    untrusted_seen: bool = False
    # Actions the user pre-approved as part of an agent plan / automation.
    preapproved: set[str] = field(default_factory=set)
    dry_run: bool = False


ConfirmPolicy = Literal["auto", "always", "never"]
Handler = Callable[[ExecutionContext, Any], Awaitable[ActionResult]]
ConfirmCheck = Callable[[Any], bool]
Describer = Callable[[Any], str]


@dataclass
class ActionSpec:
    name: str
    description: str
    params: Type[BaseModel]
    permission: Optional[str]
    risk: Risk
    handler: Handler
    confirm: ConfirmPolicy = "auto"
    # Extra dynamic rule, e.g. "copy with overwrite=True needs confirmation".
    confirm_if: Optional[ConfirmCheck] = None
    describe: Optional[Describer] = None
    # Extra information shown in the confirmation dialog (e.g. a code diff).
    preview: Optional[Callable[[Any], dict[str, Any]]] = None
    windows_only: bool = False
    category: str = "system"
    # Hidden actions can be executed by the UI but are not offered to the AI.
    ai_visible: bool = True

    def tool_schema(self) -> dict[str, Any]:
        schema = self.params.model_json_schema()
        schema.pop("title", None)
        return schema

    def summary(self, args: BaseModel) -> str:
        if self.describe:
            try:
                return self.describe(args)
            except Exception:
                pass
        parts = ", ".join(f"{k}={v!r}" for k, v in args.model_dump().items())
        return f"{self.name}({parts})"


class ActionRegistry:
    def __init__(self) -> None:
        self._specs: dict[str, ActionSpec] = {}

    def register(self, spec: ActionSpec) -> ActionSpec:
        if spec.name in self._specs:
            raise ValueError(f"duplicate action {spec.name}")
        if not spec.name.replace("_", "").isalnum():
            raise ValueError(f"invalid action name {spec.name}")
        self._specs[spec.name] = spec
        return spec

    def get(self, name: str) -> ActionSpec | None:
        return self._specs.get(name)

    def all(self) -> list[ActionSpec]:
        return list(self._specs.values())

    def __contains__(self, name: str) -> bool:
        return name in self._specs


class EmptyParams(BaseModel):
    pass
