"""Conversation (chat history) repository backed by SQLite.

Threads survive restarts; the two-table shape (conversations 1-* messages)
mirrors what a Postgres migration would look like. Message extras (citations,
model, cost, tokens) ride in a JSON `data` column so the schema stays stable
while the payload evolves."""
from __future__ import annotations

import json
import os
import sqlite3
import time
from threading import Lock

from app.utils.hashing import new_id

_SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id         TEXT PRIMARY KEY,
    title      TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    seq             INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            TEXT NOT NULL,
    content         TEXT NOT NULL,
    data            TEXT NOT NULL DEFAULT '{}',
    ts              TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id, seq);
"""


class ConversationRepository:
    def __init__(self, db_path: str | None = None, max_messages: int = 500):
        self.max_messages = max_messages
        self._lock = Lock()
        if db_path:
            os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
            self.db_path = db_path
            with self._conn() as conn:
                conn.executescript(_SCHEMA)
            self._migrate_legacy_json()

    def _migrate_legacy_json(self) -> None:
        """One-time import from the earlier JSON-file store, if present."""
        legacy_path = os.path.join(os.path.dirname(self.db_path), "conversations.json")
        if not os.path.exists(legacy_path):
            return
        with self._lock, self._conn() as conn:
            if conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0] > 0:
                return  # already has data — never overwrite
            try:
                data = json.load(open(legacy_path, encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return
            for c in data.get("conversations", []):
                conn.execute(
                    "INSERT OR IGNORE INTO conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                    (c["conversation_id"], c.get("title", "New chat"),
                     c.get("created_at"), c.get("updated_at")),
                )
                for m in c.get("messages", []):
                    extras = {k: v for k, v in m.items() if k not in ("role", "content")}
                    conn.execute(
                        "INSERT INTO messages (conversation_id, role, content, data, ts) VALUES (?, ?, ?, ?, ?)",
                        (c["conversation_id"], m.get("role", "user"), m.get("content", ""),
                         json.dumps(extras, ensure_ascii=False), m.get("ts")),
                    )
        os.rename(legacy_path, legacy_path + ".imported")

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _touch(self, conn: sqlite3.Connection, conversation_id: str) -> None:
        conn.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?",
            (time.strftime("%Y-%m-%d %H:%M:%S"), conversation_id),
        )

    def create(self, title: str) -> dict:
        conv = {
            "conversation_id": new_id("conv"),
            "title": (title or "").strip()[:80] or "New chat",
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "messages": [],
        }
        with self._lock, self._conn() as conn:
            conn.execute(
                "INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (conv["conversation_id"], conv["title"], conv["created_at"], conv["updated_at"]),
            )
        return conv

    def get(self, conversation_id: str) -> dict | None:
        with self._lock, self._conn() as conn:
            row = conn.execute(
                "SELECT id, title, created_at, updated_at FROM conversations WHERE id = ?",
                (conversation_id,),
            ).fetchone()
            if not row:
                return None
            msgs = conn.execute(
                "SELECT role, content, data, ts FROM messages WHERE conversation_id = ? ORDER BY seq",
                (conversation_id,),
            ).fetchall()
        messages = []
        for role, content, data, ts in msgs:
            m = {"role": role, "content": content, "ts": ts}
            try:
                m.update(json.loads(data))
            except json.JSONDecodeError:
                pass
            messages.append(m)
        return {
            "conversation_id": row[0], "title": row[1],
            "created_at": row[2], "updated_at": row[3], "messages": messages,
        }

    def list_all(self) -> list[dict]:
        with self._lock, self._conn() as conn:
            rows = conn.execute(
                """SELECT c.id, c.title, c.updated_at,
                          (SELECT content FROM messages WHERE conversation_id = c.id AND role='user' ORDER BY seq LIMIT 1),
                          (SELECT COUNT(*) FROM messages WHERE conversation_id = c.id)
                   FROM conversations c ORDER BY c.updated_at DESC"""
            ).fetchall()
        return [
            {
                "conversation_id": r[0], "title": r[1], "updated_at": r[2],
                "preview": (r[3] or "")[:90], "message_count": r[4],
            }
            for r in rows
        ]

    def append_message(self, conversation_id: str, message: dict) -> bool:
        with self._lock, self._conn() as conn:
            row = conn.execute("SELECT title FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
            if not row:
                return False
            ts = time.strftime("%Y-%m-%d %H:%M:%S")
            extras = {k: v for k, v in message.items() if k not in ("role", "content")}
            conn.execute(
                "INSERT INTO messages (conversation_id, role, content, data, ts) VALUES (?, ?, ?, ?, ?)",
                (conversation_id, message.get("role", "user"), message.get("content", ""),
                 json.dumps(extras, ensure_ascii=False), ts),
            )
            title = row[0]
            if title in ("New chat", "") and message.get("role") == "user":
                title = message.get("content", "")[:60]
            conn.execute(
                "UPDATE conversations SET updated_at = ?, title = ? WHERE id = ?",
                (ts, title, conversation_id),
            )
        return True

    def rename(self, conversation_id: str, title: str) -> bool:
        with self._lock, self._conn() as conn:
            cur = conn.execute(
                "UPDATE conversations SET title = ? WHERE id = ?",
                (title.strip()[:80] or "New chat", conversation_id),
            )
            return cur.rowcount > 0

    def delete(self, conversation_id: str) -> bool:
        with self._lock, self._conn() as conn:
            cur = conn.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
            return cur.rowcount > 0


_singleton: ConversationRepository | None = None


def get_conversation_repository() -> ConversationRepository:
    global _singleton
    if _singleton is None:
        from app.config import get_settings
        settings = get_settings()
        path = os.path.normpath(os.path.join(
            settings.chroma_persist_dir, "..", "store", "conversations.db"
        ))
        _singleton = ConversationRepository(path)
    return _singleton
