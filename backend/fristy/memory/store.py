"""Local personal memory (SQLite). Sensitive data is rejected, never stored."""
from __future__ import annotations

import json
import re
from typing import Any

from ..computer_control.base import ActionError
from ..core.db import Database, dumps, now
from ..security.sanitize import find_sensitive

CATEGORIES = ("preference", "favorite_game", "frequent_app", "language", "project", "custom_command",
              "routine", "fact", "conversation_summary")


class MemoryStore:
    def __init__(self, db: Database, settings_store):
        self.db = db
        self.settings = settings_store

    @property
    def enabled(self) -> bool:
        return self.settings.current.memory.enabled

    @staticmethod
    def _check(category: str, key: str, value: str) -> None:
        if category not in CATEGORIES:
            raise ActionError(f"Unknown memory category '{category}'. Use one of: {', '.join(CATEGORIES)}")
        if not key.strip() or not value.strip():
            raise ActionError("Memory key and value must not be empty.")
        if len(value) > 4000 or len(key) > 200:
            raise ActionError("Memory entry too long.")
        hits = find_sensitive(f"{key} {value}")
        if hits:
            raise ActionError(f"Refusing to store sensitive data ({', '.join(hits)}). Passwords and credentials "
                              "are never kept in memory.", "sensitive_data")

    def upsert(self, category: str, key: str, value: str, source: str = "user") -> dict[str, Any]:
        if not self.enabled:
            raise ActionError("Personal memory is disabled in settings.", "memory_disabled")
        key, value = key.strip(), value.strip()
        self._check(category, key, value)
        t = now()
        self.db.execute(
            "INSERT INTO memories(category, key, value, source, created_at, updated_at) VALUES(?,?,?,?,?,?) "
            "ON CONFLICT(category, key) DO UPDATE SET value=excluded.value, source=excluded.source, "
            "updated_at=excluded.updated_at",
            (category, key, value, source, t, t),
        )
        return self.db.query_one("SELECT * FROM memories WHERE category=? AND key=?", (category, key))  # type: ignore

    def update(self, mid: int, value: str | None = None, key: str | None = None,
               category: str | None = None) -> dict[str, Any]:
        row = self.get(mid)
        c, k, v = category or row["category"], key or row["key"], value if value is not None else row["value"]
        self._check(c, k, v)
        self.db.execute("UPDATE memories SET category=?, key=?, value=?, updated_at=? WHERE id=?", (c, k, v, now(), mid))
        return self.get(mid)

    def get(self, mid: int) -> dict[str, Any]:
        row = self.db.query_one("SELECT * FROM memories WHERE id=?", (mid,))
        if not row:
            raise ActionError(f"Memory {mid} not found.", "not_found")
        return row

    def list(self, category: str | None = None, search: str | None = None) -> list[dict[str, Any]]:
        sql, params = "SELECT * FROM memories WHERE 1=1", []
        if category:
            sql += " AND category=?"
            params.append(category)
        if search:
            sql += " AND (key LIKE ? OR value LIKE ?)"
            params += [f"%{search}%", f"%{search}%"]
        return self.db.query(sql + " ORDER BY updated_at DESC", params)

    def delete(self, mid: int) -> None:
        self.db.execute("DELETE FROM memories WHERE id=?", (mid,))

    def delete_by_key(self, key: str) -> int:
        cur = self.db.execute("DELETE FROM memories WHERE key=?", (key,))
        return cur.rowcount

    def clear(self) -> int:
        return self.db.execute("DELETE FROM memories").rowcount

    def export(self) -> dict[str, Any]:
        return {"format": "fristy-memory-v1", "exported_at": now(), "memories": self.list(),
                "usage": self.db.query("SELECT * FROM usage_stats ORDER BY count DESC")}

    def import_(self, data: dict[str, Any]) -> int:
        n = 0
        for m in data.get("memories", []):
            try:
                self.upsert(m["category"], m["key"], m["value"], source="import")
                n += 1
            except (ActionError, KeyError):
                continue
        return n

    # ---------------------------------------------------------------- usage
    def track_usage(self, kind: str, name: str) -> None:
        if not self.enabled or not self.settings.current.memory.auto_learn:
            return
        self.db.execute(
            "INSERT INTO usage_stats(kind, name, count, last_used) VALUES(?,?,1,?) "
            "ON CONFLICT(kind, name) DO UPDATE SET count=count+1, last_used=excluded.last_used",
            (kind, name, now()),
        )

    def top_usage(self, kind: str, limit: int = 5) -> list[dict[str, Any]]:
        return self.db.query("SELECT name, count FROM usage_stats WHERE kind=? ORDER BY count DESC LIMIT ?",
                             (kind, limit))

    def context_block(self, max_items: int = 40) -> str:
        """Compact text injected into the system prompt."""
        if not self.enabled:
            return ""
        rows = self.db.query(
            "SELECT category, key, value FROM memories WHERE category != 'conversation_summary' "
            "ORDER BY updated_at DESC LIMIT ?", (max_items,))
        lines = [f"- [{r['category']}] {r['key']}: {r['value']}" for r in rows]
        apps = self.top_usage("app", 5)
        if apps:
            lines.append("- frequently used apps: " + ", ".join(a["name"] for a in apps))
        games = self.top_usage("game", 5)
        if games:
            lines.append("- frequently played games: " + ", ".join(g["name"] for g in games))
        return "\n".join(lines)


_LEARN_PATTERNS = [
    (re.compile(r"(?i)^\s*my favou?rite game is (.+?)[.!]?$"), "favorite_game", "favorite game"),
    (re.compile(r"^\s*המשחק האהוב עליי (?:הוא )?(.+?)[.!]?$"), "favorite_game", "favorite game"),
    (re.compile(r"(?i)^\s*(?:please )?call me (.+?)[.!]?$"), "preference", "preferred name"),
    (re.compile(r"^\s*תקרא לי (.+?)[.!]?$"), "preference", "preferred name"),
    (re.compile(r"(?i)^\s*i prefer (hebrew|english)\b"), "language", "preferred language"),
    (re.compile(r"(?i)^\s*remember that (.+)$"), "fact", None),
    (re.compile(r"^\s*תזכור ש(.+)$"), "fact", None),
]


def extract_learnable(text: str) -> list[tuple[str, str, str]]:
    """Explicit 'remember'-style statements -> (category, key, value). Conservative by design."""
    out = []
    for pat, cat, key in _LEARN_PATTERNS:
        m = pat.search(text.strip())
        if m:
            value = m.group(1).strip()
            out.append((cat, key or value[:60], value))
    return out
