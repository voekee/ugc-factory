from __future__ import annotations

import json
import sqlite3
import threading
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


def connect() -> sqlite3.Connection:
    con = sqlite3.connect(_db_path(), check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con


def init_db() -> None:
    with _LOCK, connect() as con:
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
        con.commit()


def create_job(job: dict[str, Any]) -> None:
    now = utcnow()
    row = {**job, "created_at": now, "updated_at": now}
    with _LOCK, connect() as con:
        con.execute(
            """
            INSERT INTO jobs
            (id,batch_id,owner,renderer,prompt,duration,seed,start_frame,end_frame,
             output_raw,output_clean,status,error,downloaded,created_at,updated_at)
            VALUES
            (:id,:batch_id,:owner,:renderer,:prompt,:duration,:seed,:start_frame,:end_frame,
             NULL,NULL,:status,NULL,0,:created_at,:updated_at)
            """,
            row,
        )
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


def list_jobs(limit: int = 500) -> list[dict[str, Any]]:
    with _LOCK, connect() as con:
        rows = con.execute(
            "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


def next_queued_job() -> dict[str, Any] | None:
    with _LOCK, connect() as con:
        row = con.execute(
            "SELECT * FROM jobs WHERE status='queued' ORDER BY created_at ASC LIMIT 1"
        ).fetchone()
        if not row:
            return None
        con.execute(
            "UPDATE jobs SET status='rendering', updated_at=? WHERE id=? AND status='queued'",
            (utcnow(), row["id"]),
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
