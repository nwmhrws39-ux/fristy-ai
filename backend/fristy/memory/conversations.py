"""Conversation history storage."""
from __future__ import annotations

import json
import uuid
from typing import Any, Optional

from ..core.db import Database, dumps, now


class ConversationStore:
    def __init__(self, db: Database):
        self.db = db

    def create(self, title: str = "New conversation") -> dict[str, Any]:
        cid = uuid.uuid4().hex
        t = now()
        self.db.execute("INSERT INTO conversations(id, title, created_at, updated_at) VALUES(?,?,?,?)",
                        (cid, title[:120], t, t))
        return self.get(cid)  # type: ignore

    def get(self, cid: str) -> Optional[dict[str, Any]]:
        return self.db.query_one("SELECT * FROM conversations WHERE id=?", (cid,))

    def ensure(self, cid: Optional[str], first_text: str = "") -> dict[str, Any]:
        if cid:
            c = self.get(cid)
            if c:
                return c
        title = (first_text.strip().splitlines() or ["New conversation"])[0][:60] or "New conversation"
        return self.create(title)

    def list(self, limit: int = 50, search: str | None = None) -> list[dict[str, Any]]:
        if search:
            return self.db.query(
                "SELECT DISTINCT c.* FROM conversations c LEFT JOIN messages m ON m.conversation_id = c.id "
                "WHERE c.title LIKE ? OR m.content LIKE ? ORDER BY c.updated_at DESC LIMIT ?",
                (f"%{search}%", f"%{search}%", limit))
        return self.db.query("SELECT * FROM conversations ORDER BY updated_at DESC LIMIT ?", (limit,))

    def add_message(self, cid: str, role: str, content: str, meta: dict | None = None) -> int:
        cur = self.db.execute(
            "INSERT INTO messages(conversation_id, role, content, meta, created_at) VALUES(?,?,?,?,?)",
            (cid, role, content, dumps(meta) if meta else None, now()))
        self.db.execute("UPDATE conversations SET updated_at=? WHERE id=?", (now(), cid))
        return int(cur.lastrowid)

    def messages(self, cid: str, limit: int = 200) -> list[dict[str, Any]]:
        rows = self.db.query(
            "SELECT * FROM (SELECT * FROM messages WHERE conversation_id=? ORDER BY id DESC LIMIT ?) ORDER BY id",
            (cid, limit))
        for r in rows:
            r["meta"] = json.loads(r["meta"]) if r.get("meta") else None
        return rows

    def count(self, cid: str) -> int:
        row = self.db.query_one("SELECT COUNT(*) AS n FROM messages WHERE conversation_id=?", (cid,))
        return int(row["n"]) if row else 0

    def rename(self, cid: str, title: str) -> None:
        self.db.execute("UPDATE conversations SET title=? WHERE id=?", (title[:120], cid))

    def set_summary(self, cid: str, summary: str) -> None:
        self.db.execute("UPDATE conversations SET summary=? WHERE id=?", (summary, cid))

    def delete(self, cid: str) -> None:
        self.db.execute("DELETE FROM messages WHERE conversation_id=?", (cid,))
        self.db.execute("DELETE FROM conversations WHERE id=?", (cid,))

    def clear(self) -> None:
        self.db.execute("DELETE FROM messages")
        self.db.execute("DELETE FROM conversations")
