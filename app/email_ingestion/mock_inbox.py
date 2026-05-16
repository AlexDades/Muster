from __future__ import annotations
import sqlite3
from datetime import datetime
from app.email_ingestion.models import Email


class MockInbox:
    def __init__(self, db_path: str):
        self._db_path = db_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS emails (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id  TEXT    UNIQUE NOT NULL,
                    sender      TEXT    NOT NULL,
                    subject     TEXT    NOT NULL,
                    body        TEXT    NOT NULL,
                    received_at TEXT    NOT NULL,
                    status      TEXT    NOT NULL DEFAULT 'unread',
                    reply_body  TEXT,
                    replied_at  TEXT
                )
            """)

    def add_email(self, email: Email) -> int:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO emails
                    (message_id, sender, subject, body, received_at, status)
                VALUES (?, ?, ?, ?, ?, 'unread')
                """,
                (
                    email.message_id,
                    email.sender,
                    email.subject,
                    email.body,
                    email.received_at.isoformat(),
                ),
            )
            return cursor.lastrowid

    def get_unread(self) -> list[Email]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM emails WHERE status = 'unread' ORDER BY received_at"
            ).fetchall()
        return [self._row_to_email(row) for row in rows]

    def get_all(self) -> list[Email]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM emails ORDER BY received_at"
            ).fetchall()
        return [self._row_to_email(row) for row in rows]

    def mark_replied(self, email_id: int, reply_body: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE emails SET status='replied', reply_body=?, replied_at=? WHERE id=?",
                (reply_body, datetime.utcnow().isoformat(), email_id),
            )

    def mark_failed(self, email_id: int) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE emails SET status='failed' WHERE id=?",
                (email_id,),
            )

    def count(self, status: str | None = None) -> int:
        with self._connect() as conn:
            if status:
                return conn.execute(
                    "SELECT COUNT(*) FROM emails WHERE status=?", (status,)
                ).fetchone()[0]
            return conn.execute("SELECT COUNT(*) FROM emails").fetchone()[0]

    @staticmethod
    def _row_to_email(row: sqlite3.Row) -> Email:
        return Email(
            id=row["id"],
            message_id=row["message_id"],
            sender=row["sender"],
            subject=row["subject"],
            body=row["body"],
            received_at=datetime.fromisoformat(row["received_at"]),
            status=row["status"],
            reply_body=row["reply_body"],
            replied_at=datetime.fromisoformat(row["replied_at"]) if row["replied_at"] else None,
        )
