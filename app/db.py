from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import settings

_LOCK = threading.RLock()


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _db_path() -> Path:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    return settings.data_dir / "ugc_factory.sqlite3"


@contextmanager
def connect():
    con = sqlite3.connect(_db_path(), check_same_thread=False)
    con.execute("PRAGMA busy_timeout=10000")
    con.row_factory = sqlite3.Row
    try:
        with con:
            yield con
    finally:
        con.close()


def init_db() -> None:
    with _LOCK, connect() as con:
        con.execute("PRAGMA journal_mode=WAL")
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS jobs (
              id TEXT PRIMARY KEY,
              batch_id TEXT NOT NULL,
              owner TEXT NOT NULL,
              renderer TEXT NOT NULL,
              prompt TEXT NOT NULL,
              duration INTEGER NOT NULL,
              seed INTEGER NOT NULL,
              start_frame TEXT,
              end_frame TEXT,
              output_raw TEXT,
              output_clean TEXT,
              status TEXT NOT NULL,
              error TEXT,
              downloaded INTEGER NOT NULL DEFAULT 0,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS kv (
              key TEXT PRIMARY KEY,
              value TEXT NOT NULL
            );
            """
        )
        columns = {r[1] for r in con.execute("PRAGMA table_info(jobs)")}
        for name, kind in {
            "started_at": "TEXT", "finished_at": "TEXT", "render_seconds": "REAL",
            "encode_seconds": "REAL", "original_prompt": "TEXT", "retry_count": "INTEGER DEFAULT 0",
            "audio": "INTEGER DEFAULT 1", "profile": "TEXT", "engine_job_id": "TEXT",
            "reference_frames": "TEXT DEFAULT '[]'",
        }.items():
            if name not in columns:
                con.execute(f"ALTER TABLE jobs ADD COLUMN {name} {kind}")
        con.execute("CREATE INDEX IF NOT EXISTS jobs_status_created ON jobs(status, created_at)")
        con.commit()


def create_job(job: dict[str, Any]) -> None:
    create_jobs([job])


def create_jobs(jobs: list[dict[str, Any]]) -> None:
    now = utcnow()
    with _LOCK, connect() as con:
        con.execute("BEGIN IMMEDIATE")
        state = con.execute("SELECT value FROM kv WHERE key='session_state'").fetchone()
        if state and json.loads(state[0]) in {"ending", "terminated"}:
            raise ValueError("Session is ending; new jobs are disabled")
        for job in jobs:
            row = {**job, "created_at": now, "updated_at": now,
                   "original_prompt": job.get("original_prompt", job["prompt"]),
                   "audio": int(job.get("audio", True)), "profile": job.get("profile"),
                   "reference_frames": json.dumps(job.get("reference_frames", []))}
            con.execute("""INSERT INTO jobs
                (id,batch_id,owner,renderer,prompt,duration,seed,start_frame,end_frame,
                 status,created_at,updated_at,original_prompt,audio,profile,reference_frames)
                VALUES (:id,:batch_id,:owner,:renderer,:prompt,:duration,:seed,:start_frame,:end_frame,
                        :status,:created_at,:updated_at,:original_prompt,:audio,:profile,:reference_frames)""", row)
        con.execute("INSERT INTO kv(key,value) VALUES('idle_since', 'null') ON CONFLICT(key) DO UPDATE SET value='null'")
        con.commit()


def update_job(job_id: str, **fields: Any) -> None:
    if not fields:
        return
    fields["updated_at"] = utcnow()
    cols = ", ".join(f"{k} = ?" for k in fields)
    vals = list(fields.values()) + [job_id]
    with _LOCK, connect() as con:
        con.execute(f"UPDATE jobs SET {cols} WHERE id = ?", vals)
        con.commit()


def get_job(job_id: str) -> dict[str, Any] | None:
    with _LOCK, connect() as con:
        row = con.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return dict(row) if row else None


def list_jobs(limit: int = 500, offset: int = 0) -> list[dict[str, Any]]:
    with _LOCK, connect() as con:
        rows = con.execute(
            "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ? OFFSET ?", (limit, offset)
        ).fetchall()
    return [dict(r) for r in rows]


def next_queued_job() -> dict[str, Any] | None:
    with _LOCK, connect() as con:
        con.execute("BEGIN IMMEDIATE")
        row = con.execute(
            "SELECT * FROM jobs WHERE status='queued' ORDER BY created_at ASC LIMIT 1"
        ).fetchone()
        if not row:
            return None
        con.execute(
            "UPDATE jobs SET status='rendering', started_at=?, updated_at=? WHERE id=? AND status='queued'",
            (utcnow(), utcnow(), row["id"]),
        )
        con.commit()
        latest = con.execute("SELECT * FROM jobs WHERE id=?", (row["id"],)).fetchone()
    return dict(latest)


def set_kv(key: str, value: Any) -> None:
    payload = json.dumps(value)
    with _LOCK, connect() as con:
        con.execute(
            "INSERT INTO kv(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, payload),
        )
        con.commit()


def get_kv(key: str, default: Any = None) -> Any:
    with _LOCK, connect() as con:
        row = con.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
    return json.loads(row["value"]) if row else default


def job_counts() -> dict[str, int]:
    with _LOCK, connect() as con:
        return {r[0]: r[1] for r in con.execute("SELECT status, COUNT(*) FROM jobs GROUP BY status")}


def begin_shutdown(force: bool = False) -> None:
    with _LOCK, connect() as con:
        con.execute("BEGIN IMMEDIATE")
        con.execute("INSERT INTO kv(key,value) VALUES('session_state', '\"ending\"') "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value")
        if force:
            con.execute("UPDATE jobs SET status='cancelled', updated_at=? WHERE status='queued'", (utcnow(),))
        con.commit()


def recover_interrupted_jobs() -> None:
    # No automatic replay: an interrupted request may already have consumed GPU time.
    with _LOCK, connect() as con:
        con.execute("UPDATE jobs SET status='failed', error=?, finished_at=?, updated_at=? "
                    "WHERE status IN ('rendering','cleaning')",
                    ("Worker restarted during generation; inspect the result before explicitly retrying", utcnow(), utcnow()))
        con.commit()


def retry_job(job_id: str) -> bool:
    with _LOCK, connect() as con:
        con.execute("BEGIN IMMEDIATE")
        state = con.execute("SELECT value FROM kv WHERE key='session_state'").fetchone()
        if state and json.loads(state[0]) in {"ending", "terminated"}:
            return False
        result = con.execute("UPDATE jobs SET status='queued', error=NULL, retry_count=retry_count+1, "
                             "started_at=NULL, finished_at=NULL, engine_job_id=NULL, updated_at=? "
                             "WHERE id=? AND status='failed'", (utcnow(), job_id))
        con.commit()
        return result.rowcount == 1


def cancel_queued_job(job_id: str) -> bool:
    with _LOCK, connect() as con:
        result = con.execute("UPDATE jobs SET status='cancelled', updated_at=? WHERE id=? AND status='queued'",
                             (utcnow(), job_id))
        con.commit()
        return result.rowcount == 1
