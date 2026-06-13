"""SQLite persistence for inquiry state and bounded conversation memory."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from threading import RLock

from .models import ConversationTurn, Inquiry


class InquiryStore:
    def __init__(self, path: Path, *, memory_window: int = 10):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.memory_window = memory_window
        self._lock = RLock()
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS inquiries (
                    inquiry_id TEXT PRIMARY KEY, session_id TEXT NOT NULL, payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS turns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL, payload TEXT NOT NULL
                );
                """
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def save_inquiry(self, inquiry: Inquiry) -> None:
        payload = json.dumps(inquiry.to_dict(), ensure_ascii=False)
        with self._lock, self._connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO inquiries(inquiry_id, session_id, payload) VALUES (?, ?, ?)",
                (inquiry.inquiry_id, inquiry.session_id, payload),
            )

    def get_inquiry(self, inquiry_id: str) -> Inquiry | None:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM inquiries WHERE inquiry_id = ?", (inquiry_id,)
            ).fetchone()
        return Inquiry.from_dict(json.loads(row[0])) if row else None

    def append_turn(self, session_id: str, turn: ConversationTurn) -> None:
        payload = json.dumps(turn.__dict__, ensure_ascii=False)
        with self._lock, self._connect() as connection:
            connection.execute("INSERT INTO turns(session_id, payload) VALUES (?, ?)", (session_id, payload))
            connection.execute(
                """
                DELETE FROM turns WHERE session_id = ? AND id NOT IN (
                    SELECT id FROM turns WHERE session_id = ? ORDER BY id DESC LIMIT ?
                )
                """,
                (session_id, session_id, self.memory_window),
            )

    def get_turns(self, session_id: str) -> list[ConversationTurn]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM turns WHERE session_id = ? ORDER BY id", (session_id,)
            ).fetchall()
        return [ConversationTurn.from_dict(json.loads(row[0])) for row in rows]

    def reset_session(self, session_id: str) -> None:
        with self._lock, self._connect() as connection:
            connection.execute("DELETE FROM inquiries WHERE session_id = ?", (session_id,))
            connection.execute("DELETE FROM turns WHERE session_id = ?", (session_id,))
