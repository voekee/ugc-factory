from __future__ import annotations

import threading
import time
from pathlib import Path

from app import db
from app.config import settings
from app.metadata import strip_metadata, validate_video
from app.renderers import get_renderer
from app.renderers.base import RenderRequest

_STOP = threading.Event()
_THREAD: threading.Thread | None = None


def _worker() -> None:
    raw_dir = settings.data_dir / "outputs" / "raw"
    clean_dir = settings.data_dir / "outputs" / "clean"
    raw_dir.mkdir(parents=True, exist_ok=True)
    clean_dir.mkdir(parents=True, exist_ok=True)

    while not _STOP.is_set():
        job = db.next_queued_job()
        if not job:
            time.sleep(0.6)
            continue
        try:
            raw = raw_dir / f"{job['id']}.mp4"
            clean = clean_dir / f"{job['id']}.mp4"
            renderer = get_renderer(job["renderer"])
            renderer.render(RenderRequest(
                job_id=job["id"], prompt=job["prompt"], duration=int(job["duration"]),
                seed=int(job["seed"]),
                start_frame=Path(job["start_frame"]) if job["start_frame"] else None,
                end_frame=Path(job["end_frame"]) if job["end_frame"] else None,
                output_path=raw,
            ))
            db.update_job(job["id"], status="cleaning", output_raw=str(raw))
            strip_metadata(raw, clean, expected_duration=float(job["duration"]))
            validate_video(clean, expected_duration=float(job["duration"]))
            raw.unlink(missing_ok=True)
            db.update_job(job["id"], status="complete", output_raw=None, output_clean=str(clean), error=None)
        except Exception as exc:
            try:
                raw.unlink(missing_ok=True)
                clean.unlink(missing_ok=True)
            except Exception:
                pass
            db.update_job(job["id"], status="failed", output_raw=None, output_clean=None, error=str(exc)[:2000])


def start_worker() -> None:
    global _THREAD
    if _THREAD and _THREAD.is_alive():
        return
    _STOP.clear()
    _THREAD = threading.Thread(target=_worker, name="ugc-worker", daemon=True)
    _THREAD.start()


def stop_worker() -> None:
    _STOP.set()
    if _THREAD:
        _THREAD.join(timeout=2)
