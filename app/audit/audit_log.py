from __future__ import annotations
import json
import sqlite3
from datetime import datetime
from typing import Optional


class AuditStore:
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
                CREATE TABLE IF NOT EXISTS audit_log (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp    TEXT    NOT NULL,
                    email_id     INTEGER,
                    draft_id     INTEGER,
                    sender       TEXT    NOT NULL,
                    subject      TEXT    NOT NULL,
                    question     TEXT    NOT NULL,
                    answer       TEXT,
                    final_answer TEXT,
                    sources      TEXT,
                    validation   TEXT,
                    status       TEXT    NOT NULL,
                    reviewer     TEXT,
                    error        TEXT
                )
            """)

    def log(self, entry: dict) -> int:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO audit_log
                    (timestamp, email_id, draft_id, sender, subject, question,
                     answer, final_answer, sources, validation, status, reviewer, error)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    datetime.utcnow().isoformat(),
                    entry.get("email_id"),
                    entry.get("draft_id"),
                    entry["sender"],
                    entry["subject"],
                    entry["question"],
                    entry.get("answer"),
                    entry.get("final_answer"),
                    json.dumps(entry.get("sources", [])),
                    json.dumps(entry.get("validation", {})),
                    entry["status"],
                    entry.get("reviewer"),
                    entry.get("error"),
                ),
            )
            return cursor.lastrowid

    def update(self, audit_id: int, updates: dict) -> None:
        allowed = {"status", "final_answer", "reviewer", "draft_id"}
        fields = {k: v for k, v in updates.items() if k in allowed}
        if not fields:
            return
        clauses = ", ".join(f"{k}=?" for k in fields)
        values = list(fields.values()) + [audit_id]
        with self._connect() as conn:
            conn.execute(f"UPDATE audit_log SET {clauses} WHERE id=?", values)

    def get_all(
        self,
        status: Optional[str] = None,
        sender: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        conditions, params = [], []
        if status:
            conditions.append("status=?")
            params.append(status)
        if sender:
            conditions.append("sender=?")
            params.append(sender)
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params += [limit, offset]
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM audit_log {where} ORDER BY timestamp DESC LIMIT ? OFFSET ?",
                params,
            ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def get_by_id(self, audit_id: int) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM audit_log WHERE id=?", (audit_id,)
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def count(self, status: Optional[str] = None, sender: Optional[str] = None) -> int:
        conditions, params = [], []
        if status:
            conditions.append("status=?")
            params.append(status)
        if sender:
            conditions.append("sender=?")
            params.append(sender)
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        with self._connect() as conn:
            return conn.execute(
                f"SELECT COUNT(*) FROM audit_log {where}", params
            ).fetchone()[0]

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict:
        d = dict(row)
        d["sources"] = json.loads(d["sources"] or "[]")
        d["validation"] = json.loads(d["validation"] or "{}")
        return d
