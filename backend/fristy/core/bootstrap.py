"""Builds the service container."""
from __future__ import annotations

import time

from ..config import RuntimeConfig
from ..ai_engine.manager import AIManager
from ..ai_engine.orchestrator import Orchestrator
from ..automations.engine import AutomationEngine
from ..coding.tools import CodingTools
from ..computer_control.actions import build_registry
from ..computer_control.base import ActionRegistry
from ..computer_control.confirm import ConfirmationBroker
from ..computer_control.engine import ActionEngine
from ..computer_control.input_control import InputController
from ..files.ops import FileOps
from ..files.sandbox import FileSandbox
from ..integrations.clients import Integrations, build_integration_actions
from ..integrations.remote import RemoteServer
from ..memory.conversations import ConversationStore
from ..memory.store import MemoryStore
from ..screen_analysis.capture import ScreenCapture
from ..screen_analysis.uia import UIAWorker
from ..security.audit import AuditLog
from ..security.emergency import StopController
from ..security.secrets import SecretStore
from ..voice_engine.engine import VoiceEngine
from .db import Database
from .events import EventBus
from .metrics import MetricsMonitor
from .services import Services
from .settings import SettingsStore


def build_services(config: RuntimeConfig, platform=None, use_keyring: bool = True, db_path=None) -> Services:
    config.ensure_dirs()
    db = Database(db_path or config.db_path)
    bus = EventBus()
    settings = SettingsStore(db)
    audit = AuditLog(db, bus)
    secrets = SecretStore(use_keyring=use_keyring)
    stop = StopController()
    if platform is None:
        from ..computer_control.platform import get_platform

        platform = get_platform()
    confirmations = ConfirmationBroker(bus)
    registry = ActionRegistry()
    engine = ActionEngine(registry, settings, confirmations, audit, stop, bus)
    sandbox = FileSandbox(settings)
    uia = UIAWorker()
    svc = Services(
        config=config, db=db, settings=settings, bus=bus, audit=audit, secrets=secrets, stop=stop,
        platform=platform, confirmations=confirmations, registry=registry, engine=engine, sandbox=sandbox,
        files=FileOps(sandbox), coding=CodingTools(sandbox, config.backups_dir), memory=MemoryStore(db, settings),
        uia=uia, screen=ScreenCapture(platform, settings, bus, uia if uia.available else None),
        input=InputController(platform, settings, stop, uia if uia.available else None),
    )
    svc.ai = AIManager(settings, secrets, bus)
    svc.conversations = ConversationStore(db)
    svc.orchestrator = Orchestrator(svc)
    svc.automations = AutomationEngine(db, engine, confirmations, platform, bus, audit, stop)
    svc.integrations = Integrations(settings, secrets)
    svc.voice = VoiceEngine(settings, secrets, config.models_dir, bus)
    svc.metrics = MetricsMonitor(platform, bus)
    svc.remote = RemoteServer(svc)
    build_registry(svc)
    build_integration_actions(svc)
    stop.on_stop(confirmations.deny_all)
    svc.started_at = time.time()
    return svc
