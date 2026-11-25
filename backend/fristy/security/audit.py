"""Append-only action audit log."""
from __future__ import annotations

from typing import Any

from ..core.db import Database, dumps, now
from .sanitize import redact


class AuditLog:
    def __init__(self, db: Database, bus=None):
        self.db = db
        self.bus = bus

    def record(
        self,
        event: str,
        *,
        action: str | None = None,
        source: str | None = None,
        status: str | None = None,
        detail: Any = None,
    ) -> int:
        detail_s = redact(dumps(detail)) if detail is not None else None
        cur = self.db.execute(
            "INSERT INTO audit_log(ts, event, action, source, status, detail) VALUES(?,?,?,?,?,?)",
            (now(), event, action, source, status, detail_s),
        )
        entry_id = int(cur.lastrowid)
        if self.bus:
            self.bus.publish(
                "audit", id=entry_id, event=event, action=action, source=source, status=status
            )
        return entry_id

    def recent(self, limit: int = 100, offset: int = 0, action: str | None = None) -> list[dict]:
        limit = max(1, min(limit, 1000))
        if action:
            return self.db.query(
                "SELECT * FROM audit_log WHERE action = ? ORDER BY id DESC LIMIT ? OFFSET ?",
                (action, limit, offset),
            )
        return self.db.query("SELECT * FROM audit_log ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset))
