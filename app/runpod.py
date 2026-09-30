from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone

from app.config import settings


def session_status() -> dict:
    start = settings.session_started
    elapsed_h = max(0.0, (datetime.now(timezone.utc) - start).total_seconds() / 3600)
    rate = settings.session_hourly_rate_usd
    return {
        "pod_id": settings.runpod_pod_id,
        "session_name": settings.runpod_session_name,
        "started_at": start.isoformat(),
        "elapsed_seconds": round(elapsed_h * 3600),
        "hourly_rate_usd": rate if rate > 0 else None,
        "gpu_type": os.environ.get("UGC_GPU_TYPE", "Unavailable"),
        "estimated_cost_usd": round(elapsed_h * rate, 4) if rate > 0 else None,
        "ephemeral": True,
    }


def resolve_pod_id() -> str:
    if settings.runpod_pod_id:
        return settings.runpod_pod_id
    if not settings.runpod_api_key or not settings.runpod_session_name:
        return ""
    import runpod
    runpod.api_key = settings.runpod_api_key
    for pod in runpod.get_pods(api_key=settings.runpod_api_key):
        if pod.get("name") == settings.runpod_session_name:
            return str(pod.get("id") or "")
    return ""


async def terminate_pod_delayed(delay_seconds: int = 2) -> None:
    await asyncio.sleep(delay_seconds)
    pod_id = resolve_pod_id()
    if not pod_id:
        return
    import runpod
    runpod.api_key = settings.runpod_api_key
    from app import db
    db.set_kv("termination_requested_at", datetime.now(timezone.utc).isoformat())
    # The watchdog and external guardian retry if this first request fails.
    await asyncio.to_thread(runpod.terminate_pod, pod_id)
