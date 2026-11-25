"""API key storage in the operating-system credential store.

On Windows, ``keyring`` uses the Windows Credential Manager (DPAPI protected).
If no OS backend is available (e.g. a headless Linux dev box) secrets are kept
only in memory for the lifetime of the process and the UI is told so - we never
fall back to writing plaintext keys to disk.
"""
from __future__ import annotations

import logging
import threading

log = logging.getLogger(__name__)

SERVICE = "FRISTY AI"
KNOWN_SECRETS = (
    "openai_api_key",
    "anthropic_api_key",
    "gemini_api_key",
    "custom_api_key",
    "integration_launcher_token",
    "integration_pc_manager_token",
    "integration_cleaner_token",
)


class SecretStore:
    def __init__(self, use_keyring: bool = True):
        self._mem: dict[str, str] = {}
        self._lock = threading.Lock()
        self._kr = None
        self.backend_name = "memory"
        if use_keyring:
            try:
                import keyring
                from keyring.backends import fail

                backend = keyring.get_keyring()
                if not isinstance(backend, fail.Keyring) and "null" not in type(backend).__name__.lower():
                    # chainer backends with no usable members raise on use; probe once
                    keyring.get_password(SERVICE, "__probe__")
                    self._kr = keyring
                    self.backend_name = type(backend).__name__
            except Exception as exc:  # pragma: no cover - depends on host OS
                log.warning("OS credential store unavailable, secrets kept in memory only: %s", exc)
                self._kr = None

    @property
    def persistent(self) -> bool:
        return self._kr is not None

    def _check(self, name: str) -> None:
        if name not in KNOWN_SECRETS:
            raise KeyError(f"unknown secret: {name}")

    def get(self, name: str) -> str | None:
        self._check(name)
        if self._kr:
            try:
                return self._kr.get_password(SERVICE, name)
            except Exception as exc:  # pragma: no cover
                log.error("keyring read failed: %s", exc)
        with self._lock:
            return self._mem.get(name)

    def set(self, name: str, value: str) -> None:
        self._check(name)
        value = (value or "").strip()
        if not value:
            self.delete(name)
            return
        if self._kr:
            self._kr.set_password(SERVICE, name, value)
            return
        with self._lock:
            self._mem[name] = value

    def delete(self, name: str) -> None:
        self._check(name)
        if self._kr:
            try:
                self._kr.delete_password(SERVICE, name)
            except Exception:
                pass
        with self._lock:
            self._mem.pop(name, None)

    def status(self) -> dict[str, bool]:
        return {n: bool(self.get(n)) for n in KNOWN_SECRETS}
