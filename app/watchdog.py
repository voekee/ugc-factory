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
    try:
        import runpod
        runpod.api_key = settings.runpod_api_key
        runpod.terminate_pod(pod_id)
    except Exception:
        return


def start_watchdog() -> None:
    threading.Thread(target=_watch, name="session-watchdog", daemon=True).start()
