from __future__ import annotations
import sqlite3
from typing import Optional


class OnboardingStore:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS onboarding_sequences (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS sequence_steps (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sequence_id INTEGER NOT NULL REFERENCES onboarding_sequences(id),
                    doc_id TEXT NOT NULL,
                    doc_name TEXT NOT NULL,
                    day_offset INTEGER NOT NULL DEFAULT 0,
                    subject TEXT NOT NULL,
                    body TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS onboarding_enrollments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sequence_id INTEGER NOT NULL REFERENCES onboarding_sequences(id),
                    employee_name TEXT NOT NULL,
                    employee_email TEXT NOT NULL,
                    start_date TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS enrollment_deliveries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    enrollment_id INTEGER NOT NULL REFERENCES onboarding_enrollments(id),
                    step_id INTEGER NOT NULL REFERENCES sequence_steps(id),
                    scheduled_date TEXT NOT NULL,
                    sent_at TEXT,
                    status TEXT NOT NULL DEFAULT 'pending'
                );
            """)

    def create_sequence(self, name: str, description: str) -> int:
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO onboarding_sequences (name, description) VALUES (?, ?)",
                (name, description),
            )
            return cur.lastrowid

    def list_sequences(self) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT s.id, s.name, s.description, s.created_at,
                       COUNT(st.id) AS step_count
                FROM onboarding_sequences s
                LEFT JOIN sequence_steps st ON st.sequence_id = s.id
                GROUP BY s.id
                ORDER BY s.id
            """).fetchall()
            return [dict(r) for r in rows]

    def get_sequence(self, sequence_id: int) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM onboarding_sequences WHERE id = ?",
                (sequence_id,),
            ).fetchone()
            return dict(row) if row else None

    def delete_sequence(self, sequence_id: int) -> None:
        with self._conn() as conn:
            conn.execute("DELETE FROM sequence_steps WHERE sequence_id = ?", (sequence_id,))
            conn.execute("DELETE FROM onboarding_sequences WHERE id = ?", (sequence_id,))

    def add_step(
        self,
        sequence_id: int,
        doc_id: str,
        doc_name: str,
        day_offset: int,
        subject: str,
        body: str,
    ) -> int:
        with self._conn() as conn:
            cur = conn.execute(
                """INSERT INTO sequence_steps
                   (sequence_id, doc_id, doc_name, day_offset, subject, body)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (sequence_id, doc_id, doc_name, day_offset, subject, body),
            )
            return cur.lastrowid

    def list_steps(self, sequence_id: int) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM sequence_steps WHERE sequence_id = ? ORDER BY day_offset",
                (sequence_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def delete_step(self, step_id: int) -> None:
        with self._conn() as conn:
            conn.execute("DELETE FROM sequence_steps WHERE id = ?", (step_id,))

    def enroll(
        self,
        sequence_id: int,
        employee_name: str,
        employee_email: str,
        start_date: str,
    ) -> int:
        from datetime import date, timedelta
        base = date.fromisoformat(start_date)
        with self._conn() as conn:
            cur = conn.execute(
                """INSERT INTO onboarding_enrollments
                   (sequence_id, employee_name, employee_email, start_date)
                   VALUES (?, ?, ?, ?)""",
                (sequence_id, employee_name, employee_email, start_date),
            )
            enrollment_id = cur.lastrowid
            steps = conn.execute(
                "SELECT id, day_offset FROM sequence_steps WHERE sequence_id = ?",
                (sequence_id,),
            ).fetchall()
            for step in steps:
                scheduled = (base + timedelta(days=step["day_offset"])).isoformat()
                conn.execute(
                    """INSERT INTO enrollment_deliveries
                       (enrollment_id, step_id, scheduled_date)
                       VALUES (?, ?, ?)""",
                    (enrollment_id, step["id"], scheduled),
                )
            return enrollment_id

    def list_enrollments(self) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT e.id, e.sequence_id, s.name AS sequence_name,
                       e.employee_name, e.employee_email, e.start_date,
                       e.status, e.created_at,
                       COUNT(d.id) AS total_steps,
                       SUM(CASE WHEN d.status = 'sent' THEN 1 ELSE 0 END) AS sent_steps
                FROM onboarding_enrollments e
                JOIN onboarding_sequences s ON s.id = e.sequence_id
                LEFT JOIN enrollment_deliveries d ON d.enrollment_id = e.id
                GROUP BY e.id
                ORDER BY e.id
            """).fetchall()
            return [dict(r) for r in rows]

    def cancel_enrollment(self, enrollment_id: int) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE onboarding_enrollments SET status = 'cancelled' WHERE id = ?",
                (enrollment_id,),
            )

    def get_due_deliveries(self, today: str) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT d.id AS delivery_id,
                       e.employee_name, e.employee_email,
                       st.subject, st.body, st.doc_name, st.doc_id
                FROM enrollment_deliveries d
                JOIN onboarding_enrollments e ON e.id = d.enrollment_id
                JOIN sequence_steps st ON st.id = d.step_id
                WHERE d.status = 'pending'
                  AND d.scheduled_date <= ?
                  AND e.status = 'active'
            """, (today,)).fetchall()
            return [dict(r) for r in rows]

    def mark_delivery_sent(self, delivery_id: int) -> None:
        with self._conn() as conn:
            conn.execute(
                """UPDATE enrollment_deliveries
                   SET status = 'sent', sent_at = datetime('now')
                   WHERE id = ?""",
                (delivery_id,),
            )

    def mark_delivery_failed(self, delivery_id: int) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE enrollment_deliveries SET status = 'failed' WHERE id = ?",
                (delivery_id,),
            )
