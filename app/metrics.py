from __future__ import annotations
from app import db
from app.config import settings
from app.runpod import session_status


def snapshot() -> dict:
    session = session_status()
    counts = db.job_counts()
    successful = counts.get("complete", 0)
    failed = counts.get("failed", 0)
    hours = session["elapsed_seconds"] / 3600
    cost = session["estimated_cost_usd"]
    with db.connect() as con:
        timing = con.execute("SELECT AVG(render_seconds), AVG(encode_seconds) FROM jobs WHERE status='complete'").fetchone()
    return {
        "measurement": "session wall time; not device-level CUDA profiling",
        "completed": successful, "failed": failed,
        "gpu_hours": hours * settings.runpod_gpu_count,
        "successful_clips_per_hour": successful / hours if hours > 0 else None,
        "successful_clips_per_gpu_hour": successful / (hours * settings.runpod_gpu_count) if hours > 0 else None,
        "failure_rate": failed / (successful + failed) if successful + failed else None,
        "average_render_wall_seconds": timing[0], "average_encode_seconds": timing[1],
        "estimated_session_cost_usd": cost,
        "estimated_cost_per_completed_clip_usd": cost / successful if cost is not None and successful else None,
        "human_quality_rating": None, "mode": settings.ugc_renderer_mode,
    }
