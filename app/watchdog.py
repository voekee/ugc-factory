from __future__ import annotations

import threading
import time
from datetime import datetime, timezone

from app.config import settings
from app.runpod import resolve_pod_id


def _watch() -> None:
    if settings.ugc_renderer_mode.lower() == "mock" or not settings.runpod_api_key:
        return
    deadline = settings.session_started.timestamp() + max(0.25, settings.max_session_hours) * 3600
    remaining = deadline - datetime.now(timezone.utc).timestamp()
    if remaining > 0:
        time.sleep(remaining)
    pod_id = resolve_pod_id()
    if not pod_id:
        return
    import runpod
    runpod.api_key = settings.runpod_api_key
    # Transient Runpod API failures must not leave an expired paid Pod running.
    for attempt in range(20):
        try:
            runpod.terminate_pod(pod_id)
            return
        except Exception as exc:
            print(f"[watchdog] Termination attempt {attempt + 1} failed: {type(exc).__name__}", flush=True)
            time.sleep(30)


def start_watchdog() -> None:
    threading.Thread(target=_watch, name="session-watchdog", daemon=True).start()
