import json
import sqlite3
import time
from contextlib import closing

from app.config import get_settings


def _db_path() -> str:
    url = get_settings().database_url
    prefix = "sqlite:///"
    return url[len(prefix):] if url.startswith(prefix) else "auditor.db"


def _connect():
    return sqlite3.connect(_db_path())


def init_db():
    with closing(_connect()) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS audits (
                job_id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                created_at REAL NOT NULL,
                violation_count INTEGER NOT NULL,
                result_json TEXT NOT NULL
            )
            """
        )
        conn.commit()


def save_audit(job_id: str, filename: str, result: dict):
    with closing(_connect()) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO audits VALUES (?, ?, ?, ?, ?)",
            (
                job_id,
                filename,
                time.time(),
                len(result.get("violations", [])),
                json.dumps(result),
            ),
        )
        conn.commit()


def list_audits(limit: int = 50) -> list:
    with closing(_connect()) as conn:
        rows = conn.execute(
            "SELECT job_id, filename, created_at, violation_count FROM audits "
            "ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [
        {"job_id": r[0], "filename": r[1], "created_at": r[2], "violation_count": r[3]}
        for r in rows
    ]


def get_audit(job_id: str):
    with closing(_connect()) as conn:
        row = conn.execute(
            "SELECT result_json FROM audits WHERE job_id = ?", (job_id,)
        ).fetchone()
    return json.loads(row[0]) if row else None