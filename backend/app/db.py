"""SQLite storage: projects, migration jobs and the LLM response cache."""

import json
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from app.config import ROOT

DB_PATH = Path(os.environ.get("MIGRATOR_DB", ROOT / "backend" / "data" / "migrator.sqlite3"))
_lock = threading.Lock()
_conn: sqlite3.Connection | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, language TEXT NOT NULL, files TEXT NOT NULL,
  assessment TEXT NOT NULL, mappings TEXT NOT NULL, created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  status TEXT NOT NULL, events TEXT NOT NULL, result TEXT, created REAL NOT NULL);
CREATE INDEX IF NOT EXISTS jobs_project ON jobs(project_id);
CREATE TABLE IF NOT EXISTS llm_cache (key TEXT PRIMARY KEY, text TEXT NOT NULL, created REAL NOT NULL);
"""


def connect(path=None) -> sqlite3.Connection:
    global _conn
    if _conn is None or path is not None:
        p = path or DB_PATH
        if str(p) != ":memory:":
            Path(p).parent.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(p, check_same_thread=False)
        _conn.execute("PRAGMA foreign_keys = ON")
        _conn.execute("PRAGMA journal_mode = WAL") if str(p) != ":memory:" else None
        _conn.executescript(SCHEMA)
    return _conn


def _q(sql: str, args: tuple = ()) -> list[tuple]:
    with _lock:
        c = connect()
        rows = c.execute(sql, args).fetchall()
        c.commit()
    return rows


# ---- projects


def insert_project(pid: str, name: str, language: str, files: dict, assessment: dict, mappings: dict) -> None:
    _q(
        "INSERT INTO projects VALUES (?, ?, ?, ?, ?, ?, ?)",
        (pid, name, language, json.dumps(files), json.dumps(assessment), json.dumps(mappings), time.time()),
    )


def update_mappings(pid: str, mappings: dict) -> None:
    _q("UPDATE projects SET mappings = ? WHERE id = ?", (json.dumps(mappings), pid))


def get_project(pid: str) -> dict | None:
    rows = _q("SELECT id, name, language, files, assessment, mappings, created FROM projects WHERE id = ?", (pid,))
    if not rows:
        return None
    r = rows[0]
    return {
        "id": r[0],
        "name": r[1],
        "language": r[2],
        "files": json.loads(r[3]),
        "assessment": json.loads(r[4]),
        "mappings": json.loads(r[5]),
        "created": r[6],
    }


def list_projects() -> list[dict]:
    rows = _q(
        "SELECT p.id, p.name, p.language, p.created, json_extract(p.assessment, '$.summary.loc'), "
        "(SELECT status FROM jobs j WHERE j.project_id = p.id ORDER BY created DESC LIMIT 1) "
        "FROM projects p ORDER BY p.created DESC"
    )
    return [{"id": r[0], "name": r[1], "language": r[2], "created": r[3], "loc": r[4], "status": r[5] or "new"} for r in rows]


def delete_project(pid: str) -> None:
    _q("DELETE FROM jobs WHERE project_id = ?", (pid,))
    _q("DELETE FROM projects WHERE id = ?", (pid,))


# ---- jobs


def save_job(jid: str, project_id: str, status: str, events: list[dict], result: Any) -> None:
    _q(
        "INSERT INTO jobs (id, project_id, status, events, result, created) VALUES (?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(id) DO UPDATE SET status = excluded.status, events = excluded.events, result = excluded.result",
        (jid, project_id, status, json.dumps(events), json.dumps(result) if result is not None else None, time.time()),
    )


def get_job(jid: str) -> dict | None:
    rows = _q("SELECT id, project_id, status, events, result, created FROM jobs WHERE id = ?", (jid,))
    if not rows:
        return None
    r = rows[0]
    return {
        "id": r[0],
        "project_id": r[1],
        "status": r[2],
        "events": json.loads(r[3]),
        "result": json.loads(r[4]) if r[4] else None,
        "created": r[5],
    }


def project_jobs(pid: str) -> list[dict]:
    rows = _q("SELECT id, status, created FROM jobs WHERE project_id = ? ORDER BY created DESC", (pid,))
    return [{"id": r[0], "status": r[1], "created": r[2]} for r in rows]


def mark_interrupted() -> None:
    """Jobs that were running when the server stopped cannot resume mid-step."""
    _q("UPDATE jobs SET status = 'interrupted' WHERE status = 'running'")


# ---- LLM cache


def cache_get(key: str) -> str | None:
    rows = _q("SELECT text FROM llm_cache WHERE key = ?", (key,))
    return rows[0][0] if rows else None


def cache_put(key: str, text: str) -> None:
    _q("INSERT OR REPLACE INTO llm_cache VALUES (?, ?, ?)", (key, text, time.time()))
