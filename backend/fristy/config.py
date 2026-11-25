"""Runtime configuration resolved from environment variables.

The desktop shell (Electron) launches the backend with:
  FRISTY_PORT       - TCP port on 127.0.0.1
  FRISTY_TOKEN      - per-session random bearer token (required)
  FRISTY_DATA_DIR   - directory for the SQLite database, logs and backups
"""
from __future__ import annotations

import os
import secrets
import sys
from dataclasses import dataclass, field
from pathlib import Path

IS_WINDOWS = sys.platform == "win32"


def default_data_dir() -> Path:
    if IS_WINDOWS:
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "FRISTY AI"
    return Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))) / "fristy-ai"


@dataclass
class RuntimeConfig:
    host: str = "127.0.0.1"
    port: int = 8765
    token: str = field(default_factory=lambda: secrets.token_urlsafe(32))
    data_dir: Path = field(default_factory=default_data_dir)

    @property
    def db_path(self) -> Path:
        return self.data_dir / "fristy.db"

    @property
    def backups_dir(self) -> Path:
        return self.data_dir / "backups"

    @property
    def screenshots_dir(self) -> Path:
        return self.data_dir / "screenshots"

    @property
    def models_dir(self) -> Path:
        return self.data_dir / "models"

    def ensure_dirs(self) -> None:
        for p in (self.data_dir, self.backups_dir, self.screenshots_dir, self.models_dir):
            p.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_env(cls) -> "RuntimeConfig":
        cfg = cls()
        cfg.port = int(os.environ.get("FRISTY_PORT", cfg.port))
        token = os.environ.get("FRISTY_TOKEN")
        if token:
            cfg.token = token
        if os.environ.get("FRISTY_DATA_DIR"):
            cfg.data_dir = Path(os.environ["FRISTY_DATA_DIR"])
        # The backend only ever binds to loopback. Remote access (FRISTY Remote)
        # uses a separate, paired and authenticated listener.
        cfg.host = "127.0.0.1"
        return cfg
