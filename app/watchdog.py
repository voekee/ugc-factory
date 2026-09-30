from __future__ import annotations
import logging
import threading
from datetime import datetime, timezone
from app import db
from app.config import settings
from app.runpod import resolve_pod_id

_STOP = threading.Event()
_THREAD = None
log = logging.getLogger(__name__)


def watchdog_tick() -> None:
    if not settings.runpod_api_key:
        return
    now = datetime.now(timezone.utc)
    hard_expired = (now - settings.session_started).total_seconds() >= max(0.25, settings.max_session_hours) * 3600
    counts = db.job_counts()
    busy = any(counts.get(s, 0) for s in ("queued", "rendering", "cleaning"))
    idle_since = db.get_kv("idle_since")
    if busy:
        db.set_kv("idle_since", None)
        idle_expired = False
    else:
        if not idle_since:
            idle_since = now.isoformat()
            db.set_kv("idle_since", idle_since)
        idle_expired = (now - datetime.fromisoformat(idle_since)).total_seconds() >= settings.idle_timeout_seconds
    ending = db.get_kv("session_state") == "ending"
    if not hard_expired and not idle_expired and not (ending and not busy):
        return
    db.begin_shutdown(force=hard_expired)
    # Hard cap intentionally takes priority over a broken archive connection.
    # Graceful closure waits for CPU-side persistence acknowledgment.
    if not hard_expired:
        if settings.external_guardian or db.get_kv("external_guardian", False):
            return
        with db.connect() as con:
            unsaved = con.execute("SELECT COUNT(*) FROM jobs WHERE status='complete' AND downloaded=0").fetchone()[0]
        if unsaved:
            return
    pod_id = resolve_pod_id()
    if not pod_id:
        raise RuntimeError("Cannot resolve Pod for shutdown; will retry")
    import runpod
    runpod.api_key = settings.runpod_api_key
    runpod.terminate_pod(pod_id)
    # This process may disappear here. The CPU guardian verifies independently.
    db.set_kv("termination_requested_at", now.isoformat())


def _watch():
    while not _STOP.is_set():
        try:
            watchdog_tick()
        except Exception:
            log.exception("Pod shutdown failed; retrying")
        _STOP.wait(15)


def start_watchdog():
    global _THREAD
    if _THREAD and _THREAD.is_alive():
        return
    _STOP.clear()
    _THREAD = threading.Thread(target=_watch, name="session-watchdog", daemon=True)
    _THREAD.start()


def stop_watchdog():
    _STOP.set()
    if _THREAD:
        _THREAD.join(timeout=3)
