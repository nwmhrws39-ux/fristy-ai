"""Application settings persisted in SQLite (secrets are NOT stored here)."""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from .db import Database, now

PERMISSION_NAMES = (
    "screen_view",
    "mouse_control",
    "keyboard_control",
    "file_access",
    "app_launch",
    "system_control",
    "terminal_exec",
    "power_management",
    "network_access",
)


class ProviderConfig(BaseModel):
    enabled: bool = False
    base_url: str = ""
    default_model: str = ""


class AISettings(BaseModel):
    provider: str = "ollama"  # ollama | openai | anthropic | gemini | custom
    model: str = ""
    temperature: float = Field(0.4, ge=0.0, le=2.0)
    max_tokens: int = Field(2048, ge=64, le=32000)
    history_messages: int = Field(30, ge=2, le=200)
    providers: dict[str, ProviderConfig] = Field(
        default_factory=lambda: {
            "ollama": ProviderConfig(enabled=True, base_url="http://127.0.0.1:11434"),
            "openai": ProviderConfig(base_url="https://api.openai.com/v1", default_model="gpt-4o-mini"),
            "anthropic": ProviderConfig(base_url="https://api.anthropic.com", default_model="claude-sonnet-5-5"),
            "gemini": ProviderConfig(
                base_url="https://generativelanguage.googleapis.com", default_model="gemini-2.0-flash"
            ),
            "custom": ProviderConfig(base_url="http://127.0.0.1:1234/v1"),
        }
    )
    fast_local_commands: bool = True


class VoiceSettings(BaseModel):
    enabled: bool = True
    wake_word_enabled: bool = False
    wake_phrases: list[str] = Field(default_factory=lambda: ["hey fristy", "היי פריסטי"])
    push_to_talk_shortcut: str = "CommandOrControl+Shift+Space"
    stt_engine: Literal["local", "openai"] = "local"
    whisper_model: Literal["tiny", "base", "small", "medium", "large-v3"] = "small"
    wake_model: Literal["tiny", "base"] = "tiny"
    language: Literal["auto", "he", "en"] = "auto"
    tts_engine: Literal["system", "openai", "off"] = "system"
    voice_name: str = ""
    openai_voice: str = "alloy"
    rate: float = Field(1.0, ge=0.5, le=2.0)
    continuous_conversation: bool = False
    microphone_id: str = ""
    speak_responses: bool = True


class UISettings(BaseModel):
    language: Literal["en", "he"] = "en"
    accent_color: str = "#a855f7"
    reduce_motion: bool = False

    @field_validator("accent_color")
    @classmethod
    def _hex(cls, v: str) -> str:
        v = v.strip()
        if not (len(v) == 7 and v.startswith("#") and all(c in "0123456789abcdefABCDEF" for c in v[1:])):
            raise ValueError("accent_color must be #RRGGBB")
        return v


class AgentSettings(BaseModel):
    max_steps: int = Field(12, ge=1, le=25)
    max_duration_seconds: int = Field(300, ge=10, le=1800)
    max_recovery_attempts: int = Field(2, ge=0, le=5)
    require_plan_approval: bool = True
    chat_max_tool_calls: int = Field(5, ge=0, le=10)


class StartupSettings(BaseModel):
    start_with_windows: bool = False
    tray_mode: bool = True
    start_minimized: bool = False


class ShortcutSettings(BaseModel):
    toggle_window: str = "CommandOrControl+Shift+F"
    emergency_stop: str = "CommandOrControl+Shift+Escape"
    compact_mode: str = "CommandOrControl+Shift+C"


class MemorySettings(BaseModel):
    enabled: bool = True
    auto_learn: bool = True
    summarize_conversations: bool = True


class IntegrationConfig(BaseModel):
    enabled: bool = False
    base_url: str = ""


class IntegrationSettings(BaseModel):
    launcher: IntegrationConfig = Field(default_factory=lambda: IntegrationConfig(base_url="http://127.0.0.1:47801"))
    pc_manager: IntegrationConfig = Field(default_factory=lambda: IntegrationConfig(base_url="http://127.0.0.1:47802"))
    cleaner: IntegrationConfig = Field(default_factory=lambda: IntegrationConfig(base_url="http://127.0.0.1:47803"))


class RemoteSettings(BaseModel):
    enabled: bool = False
    port: int = Field(47810, ge=1024, le=65535)
    allow_lan: bool = False


class Settings(BaseModel):
    ai: AISettings = Field(default_factory=AISettings)
    voice: VoiceSettings = Field(default_factory=VoiceSettings)
    ui: UISettings = Field(default_factory=UISettings)
    agent: AgentSettings = Field(default_factory=AgentSettings)
    startup: StartupSettings = Field(default_factory=StartupSettings)
    shortcuts: ShortcutSettings = Field(default_factory=ShortcutSettings)
    memory: MemorySettings = Field(default_factory=MemorySettings)
    integrations: IntegrationSettings = Field(default_factory=IntegrationSettings)
    remote: RemoteSettings = Field(default_factory=RemoteSettings)
    # Every permission is OFF by default except non-destructive application launching
    # and system information/volume. The user enables the rest explicitly.
    permissions: dict[str, bool] = Field(
        default_factory=lambda: {
            p: p in ("app_launch", "system_control") for p in PERMISSION_NAMES
        }
    )
    approved_dirs: list[str] = Field(default_factory=list)
    closable_apps: list[str] = Field(default_factory=lambda: ["notepad.exe", "calc.exe"])
    onboarding_done: bool = False

    @field_validator("permissions")
    @classmethod
    def _perms(cls, v: dict[str, bool]) -> dict[str, bool]:
        out = {p: bool(v.get(p, False)) for p in PERMISSION_NAMES}
        return out

    @field_validator("approved_dirs")
    @classmethod
    def _dirs(cls, v: list[str]) -> list[str]:
        out: list[str] = []
        for d in v:
            d = str(d).strip()
            if not d:
                continue
            p = Path(d).expanduser()
            if not p.is_absolute():
                raise ValueError(f"approved directory must be absolute: {d}")
            if str(p) not in out:
                out.append(str(p))
        return out


def deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


class SettingsStore:
    KEY = "app_settings"

    def __init__(self, db: Database):
        self.db = db
        self._lock = threading.RLock()
        self._listeners: list = []
        self._settings = self._load()

    def _load(self) -> Settings:
        row = self.db.query_one("SELECT value FROM settings WHERE key = ?", (self.KEY,))
        if not row:
            return Settings()
        try:
            data = json.loads(row["value"])
            return Settings.model_validate(deep_merge(Settings().model_dump(), data))
        except Exception:
            return Settings()

    @property
    def current(self) -> Settings:
        with self._lock:
            return self._settings

    def update(self, patch: dict[str, Any]) -> Settings:
        with self._lock:
            merged = deep_merge(self._settings.model_dump(), patch)
            new = Settings.model_validate(merged)
            self.db.execute(
                "INSERT INTO settings(key, value, updated_at) VALUES(?,?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
                (self.KEY, new.model_dump_json(), now()),
            )
            old = self._settings
            self._settings = new
        for fn in list(self._listeners):
            try:
                fn(old, new)
            except Exception:
                pass
        return new

    def on_change(self, fn) -> None:
        self._listeners.append(fn)
