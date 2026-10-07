"""SQLite storage in the local data folder."""

from __future__ import annotations

import sqlite3
import threading
from datetime import UTC, date, datetime
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY,
    message_id TEXT,
    raw_hash TEXT NOT NULL UNIQUE,
    source_path TEXT,
    subject TEXT,
    sender TEXT,
    recipients TEXT,
    sent_at TEXT,
    body_text TEXT,
    in_reply_to TEXT,
    references_header TEXT,
    gmail_id TEXT,
    ingested_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS attachments (
    id INTEGER PRIMARY KEY,
    message_row_id INTEGER NOT NULL REFERENCES messages(id),
    filename TEXT,
    content_type TEXT
);
CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY,
    kid_name TEXT,
    suggested_kid TEXT,
    title TEXT NOT NULL,
    form_type TEXT NOT NULL,
    form_label TEXT NOT NULL,
    due_date TEXT,
    event_date TEXT,
    fee_amount TEXT,
    status TEXT NOT NULL DEFAULT 'todo',
    cancelled INTEGER NOT NULL DEFAULT 0,
    confidence REAL NOT NULL,
    needs_review INTEGER NOT NULL DEFAULT 0,
    review_reason TEXT,
    snippet TEXT,
    fingerprint TEXT,
    normalized_subject TEXT,
    primary_message_id INTEGER REFERENCES messages(id),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS item_messages (
    item_id INTEGER NOT NULL,
    message_row_id INTEGER NOT NULL,
    PRIMARY KEY (item_id, message_row_id)
);
CREATE INDEX IF NOT EXISTS idx_messages_msgid ON messages(message_id);
CREATE INDEX IF NOT EXISTS idx_items_fingerprint ON items(fingerprint);
"""

STATUSES = {"todo", "signed", "returned"}


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


class Database:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def has_raw_hash(self, raw_hash: str) -> bool:
        return self._one("SELECT 1 FROM messages WHERE raw_hash = ?", (raw_hash,)) is not None

    def has_message_id(self, message_id: str | None) -> bool:
        if not message_id:
            return False
        return (
            self._one(
                "SELECT 1 FROM messages WHERE message_id = ?",
                (message_id,),
            )
            is not None
        )

    def insert_message(self, message, gmail_id: str | None = None) -> int:
        with self._lock:
            cursor = self._conn.execute(
                """
                INSERT INTO messages (
                    message_id, raw_hash, source_path, subject, sender, recipients,
                    sent_at, body_text, in_reply_to, references_header, gmail_id, ingested_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message.message_id,
                    message.raw_hash,
                    message.source_path,
                    message.subject,
                    message.sender,
                    message.recipients,
                    message.sent_at.isoformat() if message.sent_at else None,
                    message.body_text,
                    message.in_reply_to,
                    message.references,
                    gmail_id or message.gmail_id,
                    utc_now(),
                ),
            )
            message_row_id = int(cursor.lastrowid)
            for attachment in message.attachments:
                self._conn.execute(
                    """
                    INSERT INTO attachments (message_row_id, filename, content_type)
                    VALUES (?, ?, ?)
                    """,
                    (message_row_id, attachment.filename, attachment.content_type),
                )
            self._conn.commit()
            return message_row_id

    def insert_item(self, item, message_row_id: int, fingerprint: str) -> int:
        now = utc_now()
        with self._lock:
            cursor = self._conn.execute(
                """
                INSERT INTO items (
                    kid_name, suggested_kid, title, form_type, form_label, due_date,
                    event_date, fee_amount, status, cancelled, confidence, needs_review,
                    review_reason, snippet, fingerprint, normalized_subject,
                    primary_message_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'todo', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.kid_name,
                    item.suggested_kid,
                    item.title,
                    item.form_type,
                    item.form_label,
                    _iso(item.due_date),
                    _iso(item.event_date),
                    item.fee_amount,
                    1 if item.cancelled else 0,
                    item.confidence,
                    1 if item.needs_review else 0,
                    item.review_reason,
                    item.snippet,
                    fingerprint,
                    item.normalized_subject,
                    message_row_id,
                    now,
                    now,
                ),
            )
            item_id = int(cursor.lastrowid)
            self._conn.execute(
                "INSERT OR IGNORE INTO item_messages (item_id, message_row_id) VALUES (?, ?)",
                (item_id, message_row_id),
            )
            self._conn.commit()
            return item_id

    def link_message(self, item_id: int, message_row_id: int) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR IGNORE INTO item_messages (item_id, message_row_id) VALUES (?, ?)",
                (item_id, message_row_id),
            )
            self._conn.commit()

    def find_fingerprint(self, fingerprint: str) -> dict | None:
        row = self._one("SELECT * FROM items WHERE fingerprint = ?", (fingerprint,))
        return dict(row) if row else None

    def find_loose(self, normalized_subject: str, kid_name: str | None, form_type: str, due_date) -> dict | None:
        row = self._one(
            """
            SELECT * FROM items
            WHERE normalized_subject = ? AND form_type = ?
              AND ifnull(kid_name, '') = ? AND ifnull(due_date, '') = ?
            """,
            (normalized_subject, form_type, kid_name or "", _iso(due_date) or ""),
        )
        return dict(row) if row else None

    def items_for_references(self, message) -> list[dict]:
        ids = reference_ids(message)
        if not ids:
            return []
        placeholders = ",".join("?" for _ in ids)
        rows = self._all(
            f"""
            SELECT DISTINCT i.* FROM items i
            JOIN item_messages im ON im.item_id = i.id
            JOIN messages m ON m.id = im.message_row_id
            WHERE lower(replace(replace(ifnull(m.message_id, ''), '<', ''), '>', '')) IN ({placeholders})
            """,
            tuple(ids),
        )
        return [dict(row) for row in rows]

    def update_due(self, item_id: int, due_date, fingerprint: str) -> None:
        with self._lock:
            self._conn.execute(
                """
                UPDATE items SET due_date = ?, fingerprint = ?, updated_at = ?
                WHERE id = ?
                """,
                (_iso(due_date), fingerprint, utc_now(), item_id),
            )
            self._conn.commit()

    def set_cancelled(self, item_id: int) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE items SET cancelled = 1, updated_at = ? WHERE id = ?",
                (utc_now(), item_id),
            )
            self._conn.commit()

    def set_status(self, item_id: int, status: str) -> dict | None:
        if status not in STATUSES:
            raise ValueError(f"status must be one of {sorted(STATUSES)}")
        with self._lock:
            self._conn.execute(
                "UPDATE items SET status = ?, updated_at = ? WHERE id = ?",
                (status, utc_now(), item_id),
            )
            self._conn.commit()
        return self.get_item(item_id)

    def assign_kid(self, item_id: int, kid_name: str, fingerprint: str) -> dict | None:
        with self._lock:
            self._conn.execute(
                """
                UPDATE items
                SET kid_name = ?, suggested_kid = NULL, needs_review = 0,
                    review_reason = NULL, fingerprint = ?, updated_at = ?
                WHERE id = ?
                """,
                (kid_name, fingerprint, utc_now(), item_id),
            )
            self._conn.commit()
        return self.get_item(item_id)

    def get_item(self, item_id: int) -> dict | None:
        row = self._one("SELECT * FROM items WHERE id = ?", (item_id,))
        return dict(row) if row else None

    def list_items(self) -> list[dict]:
        return [dict(row) for row in self._all("SELECT * FROM items ORDER BY id")]

    def message_for(self, message_row_id: int | None) -> dict | None:
        if not message_row_id:
            return None
        row = self._one("SELECT * FROM messages WHERE id = ?", (message_row_id,))
        return dict(row) if row else None

    def attachments_for(self, message_row_id: int | None) -> list[dict]:
        if not message_row_id:
            return []
        rows = self._all(
            "SELECT filename, content_type FROM attachments WHERE message_row_id = ? ORDER BY id",
            (message_row_id,),
        )
        return [dict(row) for row in rows]

    def _one(self, sql: str, params: tuple):
        with self._lock:
            return self._conn.execute(sql, params).fetchone()

    def _all(self, sql: str, params: tuple = ()):
        with self._lock:
            return self._conn.execute(sql, params).fetchall()


def reference_ids(message) -> set[str]:
    raw = " ".join(part for part in (message.in_reply_to, message.references) if part)
    found = set()
    for token in raw.replace(",", " ").split():
        cleaned = token.strip("<>").strip().casefold()
        if cleaned:
            found.add(cleaned)
    return found


def _iso(value) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value.isoformat()
    return str(value)
