from __future__ import annotations
import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from app.email_ingestion.models import Email


@dataclass
class Draft:
    email_id: int
    sender: str
    subject: str
    question: str
    proposed_answer: str
    sources: list[str]
    validation: dict
    status: str = "pending"
    final_answer: Optional[str] = None
    reviewer_note: Optional[str] = None
    id: Optional[int] = None
    created_at: Optional[datetime] = None
    reviewed_at: Optional[datetime] = None


class DraftStore:
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
                CREATE TABLE IF NOT EXISTS drafts (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    email_id        INTEGER NOT NULL,
                    sender          TEXT    NOT NULL,
                    subject         TEXT    NOT NULL,
                    question        TEXT    NOT NULL,
                    proposed_answer TEXT    NOT NULL,
                    sources         TEXT    NOT NULL,
                    validation      TEXT    NOT NULL,
                    status          TEXT    NOT NULL DEFAULT 'pending',
                    final_answer    TEXT,
                    reviewer_note   TEXT,
                    created_at      TEXT    NOT NULL,
                    reviewed_at     TEXT
                )
            """)

    def save_draft(self, email: Email, pipeline_result: dict) -> int:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO drafts
                    (email_id, sender, subject, question, proposed_answer, sources, validation, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    email.id,
                    email.sender,
                    email.subject,
                    pipeline_result["question"],
                    pipeline_result["answer"],
                    json.dumps(pipeline_result["sources"]),
                    json.dumps(pipeline_result["validation"]),
                    datetime.utcnow().isoformat(),
                ),
            )
            return cursor.lastrowid

    def get_pending(self) -> list[Draft]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM drafts WHERE status = 'pending' ORDER BY created_at"
            ).fetchall()
        return [self._row_to_draft(row) for row in rows]

    def get_all(self) -> list[Draft]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM drafts ORDER BY created_at"
            ).fetchall()
        return [self._row_to_draft(row) for row in rows]

    def approve(self, draft_id: int, final_answer: str | None = None) -> None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT proposed_answer FROM drafts WHERE id=?", (draft_id,)
            ).fetchone()
            answer = final_answer if final_answer is not None else row["proposed_answer"]
            status = "edited" if final_answer is not None else "approved"
            conn.execute(
                "UPDATE drafts SET status=?, final_answer=?, reviewed_at=? WHERE id=?",
                (status, answer, datetime.utcnow().isoformat(), draft_id),
            )

    def reject(self, draft_id: int, note: str = "") -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE drafts SET status='rejected', reviewer_note=?, reviewed_at=? WHERE id=?",
                (note, datetime.utcnow().isoformat(), draft_id),
            )

    def count(self, status: str | None = None) -> int:
        with self._connect() as conn:
            if status:
                return conn.execute(
                    "SELECT COUNT(*) FROM drafts WHERE status=?", (status,)
                ).fetchone()[0]
            return conn.execute("SELECT COUNT(*) FROM drafts").fetchone()[0]

    @staticmethod
    def _row_to_draft(row: sqlite3.Row) -> Draft:
        return Draft(
            id=row["id"],
            email_id=row["email_id"],
            sender=row["sender"],
            subject=row["subject"],
            question=row["question"],
            proposed_answer=row["proposed_answer"],
            sources=json.loads(row["sources"]),
            validation=json.loads(row["validation"]),
            status=row["status"],
            final_answer=row["final_answer"],
            reviewer_note=row["reviewer_note"],
            created_at=datetime.fromisoformat(row["created_at"]),
            reviewed_at=datetime.fromisoformat(row["reviewed_at"]) if row["reviewed_at"] else None,
        )
