from __future__ import annotations
import sqlite3
from typing import Optional


def _strip_suffix(filename: str) -> str:
    lower = filename.lower()
    for ext in (".pdf", ".docx", ".doc"):
        if lower.endswith(ext):
            return filename[: len(filename) - len(ext)]
    return filename


class VersionStore:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS document_versions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    doc_id TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    version_num INTEGER NOT NULL,
                    chunks INTEGER NOT NULL,
                    change_note TEXT NOT NULL DEFAULT '',
                    uploaded_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
            """)

    def record_upload(self, doc_id: str, filename: str, chunks: int, change_note: str = "") -> int:
        base = _strip_suffix(filename)
        with self._conn() as conn:
            row = conn.execute(
                """SELECT MAX(version_num) AS max_v
                   FROM document_versions
                   WHERE filename LIKE ?""",
                (base + "%",),
            ).fetchone()
            next_version = (row["max_v"] or 0) + 1
            conn.execute(
                """INSERT INTO document_versions
                   (doc_id, filename, version_num, chunks, change_note)
                   VALUES (?, ?, ?, ?, ?)""",
                (doc_id, filename, next_version, chunks, change_note),
            )
            return next_version

    def get_versions(self, doc_id: str) -> list[dict]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT filename FROM document_versions WHERE doc_id = ? LIMIT 1",
                (doc_id,),
            ).fetchone()
            if not row:
                return []
            base = _strip_suffix(row["filename"])
            rows = conn.execute(
                """SELECT * FROM document_versions
                   WHERE filename LIKE ?
                   ORDER BY version_num DESC""",
                (base + "%",),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_latest_version(self, doc_id: str) -> Optional[int]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT version_num FROM document_versions WHERE doc_id = ?",
                (doc_id,),
            ).fetchone()
            return row["version_num"] if row else None

    def get_all_latest(self) -> dict[str, int]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT doc_id, version_num FROM document_versions"
            ).fetchall()
            return {r["doc_id"]: r["version_num"] for r in rows}

    def remove_by_doc_id(self, doc_id: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "DELETE FROM document_versions WHERE doc_id = ?",
                (doc_id,),
            )
