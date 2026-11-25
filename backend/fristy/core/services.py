"""Service container wiring every subsystem together."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from ..config import RuntimeConfig


@dataclass
class Services:
    config: RuntimeConfig
    db: Any
    settings: Any
    bus: Any
    audit: Any
    secrets: Any
    stop: Any
    platform: Any
    confirmations: Any
    registry: Any
    engine: Any
    sandbox: Any
    files: Any
    coding: Any
    memory: Any
    uia: Any
    screen: Any
    input: Any
    ai: Any = None
    conversations: Any = None
    orchestrator: Any = None
    automations: Any = None
    integrations: Any = None
    voice: Any = None
    remote: Any = None
    metrics: Any = None
    state: dict[str, Any] = field(default_factory=dict)
    started_at: Optional[float] = None
