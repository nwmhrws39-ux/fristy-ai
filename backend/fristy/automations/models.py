"""Automation (custom command) definitions."""
from __future__ import annotations

import re
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator

_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class Trigger(BaseModel):
    type: Literal["phrase", "schedule", "manual", "startup"] = "phrase"
    phrases: list[str] = Field(default_factory=list, max_length=10)
    time: Optional[str] = None  # HH:MM for schedule
    days: list[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4, 5, 6])  # Monday=0

    @field_validator("time")
    @classmethod
    def _time(cls, v):
        if v is not None and not _HHMM.match(v):
            raise ValueError("time must be HH:MM (24h)")
        return v

    @field_validator("days")
    @classmethod
    def _days(cls, v):
        if any(d < 0 or d > 6 for d in v):
            raise ValueError("days must be 0..6 (Monday=0)")
        return sorted(set(v))


class Condition(BaseModel):
    type: Literal["time_between", "weekday", "process_running", "process_not_running"]
    start: Optional[str] = None
    end: Optional[str] = None
    days: list[int] = Field(default_factory=list)
    process: Optional[str] = None


class Step(BaseModel):
    action: str = Field(..., min_length=1)
    args: dict[str, Any] = Field(default_factory=dict)
    delay_seconds: float = Field(0, ge=0, le=600)
    continue_on_error: bool = False
    description: str = ""


class Automation(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str = ""
    enabled: bool = True
    trigger: Trigger = Field(default_factory=Trigger)
    conditions: list[Condition] = Field(default_factory=list, max_length=10)
    confirmation: Literal["none", "once"] = "once"
    steps: list[Step] = Field(..., min_length=1, max_length=25)


TEMPLATES: list[dict[str, Any]] = [
    {
        "name": "Gaming Mode", "description": "Open Discord, launch a game and set the volume.",
        "trigger": {"type": "phrase", "phrases": ["gaming mode", "מצב גיימינג", "מצב משחק"]},
        "confirmation": "once",
        "steps": [
            {"action": "launch_app", "args": {"name": "Discord"}, "continue_on_error": True},
            {"action": "launch_game", "args": {"name": ""}, "delay_seconds": 2,
             "description": "Choose your game"},
            {"action": "set_volume", "args": {"level": 50}},
        ],
    },
    {
        "name": "Development Mode", "description": "Open VS Code with a project and the browser.",
        "trigger": {"type": "phrase", "phrases": ["development mode", "מצב פיתוח"]},
        "confirmation": "once",
        "steps": [
            {"action": "open_vscode", "args": {"path": ""}, "description": "Choose your project folder"},
            {"action": "open_website", "args": {"url": "https://github.com"}},
        ],
    },
    {
        "name": "Good Night", "description": "Close approved apps and schedule shutdown.",
        "trigger": {"type": "phrase", "phrases": ["good night", "לילה טוב"]},
        "confirmation": "once",
        "steps": [
            {"action": "close_app", "args": {"process": "discord.exe"}, "continue_on_error": True},
            {"action": "set_volume", "args": {"level": 10}, "continue_on_error": True},
            {"action": "shutdown_computer", "args": {"delay_seconds": 600}},
        ],
    },
]
