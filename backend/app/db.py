import json
import sqlite3
import threading
from dataclasses import asdict
from typing import Any

from app.config import ROOT

DB_PATH = ROOT / "backend" / "data" / "jobs.sqlite3"
_lock = threading.Lock()
_conn: sqlite3.Connection | None = None


def _db() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.execute(
            "CREATE TABLE IF NOT EXISTS jobs ("
            "id TEXT PRIMARY KEY, language TEXT, code TEXT, events TEXT, result TEXT, "
            "created REAL DEFAULT (julianday('now')))"
        )
    return _conn


def save_job(job_id: str, language: str, code: str, events: list[dict], result: Any) -> None:
    payload = asdict(result)
    payload["providers"] = sorted(payload["providers"])
    with _lock:
        c = _db()
        c.execute(
            "INSERT OR REPLACE INTO jobs (id, language, code, events, result) VALUES (?, ?, ?, ?, ?)",
            (job_id, language, code, json.dumps(events), json.dumps(payload)),
        )
        c.commit()


def load_jobs() -> list[dict]:
    with _lock:
        rows = _db().execute("SELECT id, language, code, events, result FROM jobs ORDER BY created").fetchall()
    return [
        {"id": r[0], "language": r[1], "code": r[2], "events": json.loads(r[3]), "result": json.loads(r[4])}
        for r in rows
    ]
