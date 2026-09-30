from __future__ import annotations

from contextlib import asynccontextmanager
import base64
import binascii
import io
import random
import re
import uuid
import zipfile
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

from app import db
from app.assets import store_image, validate_pair
from app.h3 import gate_reason, require_h3
from app.config import settings
from app.models import JobStatus, RENDERERS
from app.queue_worker import start_worker, stop_worker
from app.runpod import resolve_pod_id, session_status, terminate_pod_delayed
from app.watchdog import start_watchdog, stop_watchdog

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"

@asynccontextmanager
async def lifespan(_: FastAPI):
    if (settings.ugc_renderer_mode.lower() != "mock" or settings.runpod_session_name) and settings.app_access_token in {"", "change-me"}:
        raise RuntimeError("Set a private APP_ACCESS_TOKEN before starting a real worker")
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    (settings.data_dir / "inputs").mkdir(parents=True, exist_ok=True)
    db.init_db()
    db.recover_interrupted_jobs()
    start_worker()
    start_watchdog()
    try:
        yield
    finally:
        stop_watchdog()
        stop_worker()


app = FastAPI(title="UGC Factory", version="1.0.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


def _check_auth(supplied: str | None) -> None:
    if settings.app_access_token and supplied != settings.app_access_token:
        raise HTTPException(status_code=401, detail="Invalid access token")


def _safe_filename_part(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip())
    return value.strip(".-")[:40] or "creator"


def _mark_downloaded(job_id: str) -> None:
    db.update_job(job_id, downloaded=1)


def _mark_many_downloaded(job_ids: list[str]) -> None:
    for job_id in job_ids:
        db.update_job(job_id, downloaded=1)


class JsonJobRequest(BaseModel):
    owner: str
    renderer: str
    prompt: str
    duration: int
    variations: int = Field(ge=1, le=100)
    start_frame_data_url: str | None = None
    end_frame_data_url: str | None = None
    audio: bool = True


def _save_data_url(data_url: str | None, batch_id: str, name: str) -> str | None:
    if not data_url:
        return None

    match = re.match(
        r"^data:(image/(?:png|jpeg|webp));base64,(.+)$",
        data_url,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        raise HTTPException(400, f"Unsupported or invalid {name} image")

    mime = match.group(1).lower()
    suffix = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/webp": ".webp",
    }[mime]

    if len(match.group(2)) > (settings.max_upload_mb * 1024 * 1024 * 4 // 3 + 8):
        raise HTTPException(413, "Image exceeds upload size limit")
    try:
        payload = base64.b64decode(match.group(2), validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(400, f"Invalid base64 data for {name} image") from exc

    max_bytes = settings.max_upload_mb * 1024 * 1024
    if len(payload) > max_bytes:
        raise HTTPException(413, f"{name} image exceeds {settings.max_upload_mb} MB")

    try:
        return store_image(payload)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc



def _create_job_records(
    *,
    owner: str,
    renderer: str,
    prompt: str,
    duration: int,
    variations: int,
    start_path: str | None,
    end_path: str | None,
    audio: bool = True,
) -> dict:
    if db.get_kv("session_state") in {"ending", "terminated"}:
        raise HTTPException(409, "Session is ending; new jobs are disabled")
    if settings.session_model == "h3-fl2va" and renderer != "h3-fl2va":
        raise HTTPException(409, "This session has only the H3 FL2VA family loaded")
    if settings.session_model == "wan22" and renderer != "wan22":
        raise HTTPException(409, "This session is configured for Wan quality")
    if renderer == "h3-fl2va":
        if gate_reason():
            raise HTTPException(403, gate_reason())
        if model_status().get("state") != "ready":
            raise HTTPException(503, "H3 model has not completed warm-up")
    owner = owner.strip()[:40]
    prompt = prompt.strip()

    if not owner:
        raise HTTPException(400, "Creator name is required")
    if not prompt or len(prompt) > 16000:
        raise HTTPException(400, "Prompt must contain 1–16000 characters")
    if renderer not in RENDERERS:
        raise HTTPException(400, "Unknown renderer")

    caps = RENDERERS[renderer]
    if duration not in caps.supported_durations:
        raise HTTPException(400, f"{caps.name} does not support {duration}s in this adapter")
    if not 1 <= variations <= 100:
        raise HTTPException(400, "Variations must be between 1 and 100")
    if caps.requires_start_frame and not start_path:
        raise HTTPException(400, "Start/reference frame is required for this model")
    if end_path and not caps.supports_end_frame:
        raise HTTPException(400, f"{caps.name} does not support a native end frame in V1")

    try:
        validate_pair(start_path, end_path)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    batch_id = uuid.uuid4().hex[:12]
    ids: list[str] = []
    records = []

    for _ in range(variations):
        job_id = uuid.uuid4().hex
        ids.append(job_id)
        records.append({
            "id": job_id,
            "batch_id": batch_id,
            "owner": owner,
            "renderer": renderer,
            "prompt": prompt,
            "duration": duration,
            "seed": random.randint(0, 2_147_483_647),
            "start_frame": start_path,
            "end_frame": end_path,
            "status": JobStatus.QUEUED.value,
            "audio": audio,
            "profile": settings.h3_profile if renderer == "h3-fl2va" else None,
        })

    try:
        db.create_jobs(records)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"batch_id": batch_id, "job_ids": ids}


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return (STATIC / "index.html").read_text()


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "mode": settings.ugc_renderer_mode, "model": model_status()}


@app.get("/api/renderers", dependencies=[])
def renderers(x_access_token: str | None = Header(default=None)) -> dict:
    _check_auth(x_access_token)
    return {"renderers": [{**r.dict(), "available": not gate_reason() if r.id == "h3-fl2va" else (settings.session_model == "legacy" or settings.session_model == r.id),
                           "unavailable_reason": gate_reason() if r.id == "h3-fl2va" else ("This model is not selected for this session" if settings.session_model not in {"legacy", r.id} else None)}
                          for r in RENDERERS.values()]}


def _read_job_log(job_id: str, max_chars: int = 5000) -> str:
    path = settings.data_dir / "logs" / f"{job_id}.log"
    if not path.exists():
        return ""
    try:
        data = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return data[-max_chars:]


def _job_phase(job: dict) -> tuple[str, str]:
    if job["status"] == "queued":
        return "Queued", "Waiting for the worker"
    if job["status"] == "cleaning":
        return "Cleaning video", "Removing metadata and finalizing MP4"
    if job["status"] == "complete":
        return "Ready", "Finished"
    if job["status"] == "failed":
        return "Failed", "Open the renderer error for details"
    if job["status"] != "rendering":
        return job["status"].title(), ""

    if job["renderer"] == "h3-fl2va":
        return "Generating", "The resident H3 pipeline is processing this video and audio request"
    log = _read_job_log(job["id"])
    if job["renderer"] == "wan22":
        if "[WAN] Encoding video" in log:
            return "Encoding video", "Saving the generated frames as MP4"
        if "[WAN] Generating" in log or "%|" in log and "it/s" in log and "Fetching" not in log:
            return "Generating", "Wan is rendering the video on the GPU"
        if "[WAN] Loading" in log:
            return "Loading model", "Moving model weights into memory"
        return "Downloading / checking model", "First use downloads the full Wan model; later jobs reuse it in this session"
    if "[LTX] Loading model and starting render:" in log:
        return "Loading model / rendering", "The LTX weights are loading into RAM/VRAM and GPU inference is starting"
    if "[LTX] Downloading LTX-2.5 model weights..." in log:
        return "Downloading LTX-2.5", "First-run model weights are downloading to this temporary Pod"
    if "[LTX] Runtime baked into container." in log:
        return "Checking GPU runtime", "LTX code and Python dependencies are already installed in the container"
    return "Starting renderer", "Preparing the selected model"


def _enrich_job(job: dict) -> dict:
    phase, phase_detail = _job_phase(job)
    live_log = _read_job_log(job["id"], max_chars=1800) if job["status"] == "rendering" else ""
    return {
        **job,
        "phase": phase,
        "phase_detail": phase_detail,
        "live_log": live_log,
    }


@app.get("/api/jobs")
def jobs(x_access_token: str | None = Header(default=None), offset: int = Query(0, ge=0)) -> dict:
    _check_auth(x_access_token)
    return {"jobs": [_enrich_job(job) for job in db.list_jobs(offset=offset)]}


async def _save_upload(upload: UploadFile | None, batch_id: str, name: str) -> str | None:
    if upload is None or not upload.filename:
        return None
    payload = await upload.read(settings.max_upload_mb * 1024 * 1024 + 1)
    try:
        return store_image(payload)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc



@app.post("/api/jobs-json")
def create_jobs_json(
    payload: JsonJobRequest,
    x_access_token: str | None = Header(default=None),
) -> dict:
    _check_auth(x_access_token)

    batch_id = uuid.uuid4().hex[:12]
    start_path = _save_data_url(payload.start_frame_data_url, batch_id, "start")
    end_path = _save_data_url(payload.end_frame_data_url, batch_id, "end")

    return _create_job_records(
        owner=payload.owner,
        renderer=payload.renderer,
        prompt=payload.prompt,
        duration=payload.duration,
        variations=payload.variations,
        start_path=start_path,
        end_path=end_path,
        audio=payload.audio,
    )


@app.post("/api/jobs")
async def create_jobs(
    owner: str = Form(...),
    renderer: str = Form(...),
    prompt: str = Form(...),
    duration: int = Form(...),
    variations: int = Form(...),
    audio: bool = Form(True),
    start_frame: UploadFile | None = File(default=None),
    end_frame: UploadFile | None = File(default=None),
    x_access_token: str | None = Header(default=None),
) -> dict:
    _check_auth(x_access_token)
    batch_id = uuid.uuid4().hex[:12]
    start_path = await _save_upload(start_frame, batch_id, "start")
    end_path = await _save_upload(end_frame, batch_id, "end")
    return _create_job_records(owner=owner, renderer=renderer, prompt=prompt, duration=duration,
        variations=variations, start_path=start_path, end_path=end_path, audio=audio)



@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: str, x_access_token: str | None = Header(default=None)) -> dict:
    _check_auth(x_access_token)
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    if not db.cancel_queued_job(job_id):
        raise HTTPException(409, "Only queued jobs can be cancelled")
    return {"ok": True}


@app.get("/api/jobs/{job_id}/video")
def video(job_id: str, token: str = Query(...)):
    _check_auth(token)
    job = db.get_job(job_id)
    if not job or job["status"] != JobStatus.COMPLETE.value or not job["output_clean"]:
        raise HTTPException(404, "Video not ready")
    return FileResponse(job["output_clean"], media_type="video/mp4")


@app.get("/api/jobs/{job_id}/download")
def download(job_id: str, token: str = Query(...)):
    _check_auth(token)
    job = db.get_job(job_id)
    if not job or job["status"] != JobStatus.COMPLETE.value or not job["output_clean"]:
        raise HTTPException(404, "Video not ready")
    filename = f"{_safe_filename_part(job['owner'])}-{job['renderer']}-{job['duration']}s-{job_id[:8]}.mp4"
    return FileResponse(
        job["output_clean"],
        media_type="video/mp4",
        filename=filename,
        background=BackgroundTask(_mark_downloaded, job_id),
    )


@app.get("/api/download.zip")
def download_zip(ids: str = Query(...), token: str = Query(...)):
    _check_auth(token)
    wanted = [i for i in ids.split(",") if i][:100]
    mem = io.BytesIO()
    included = []
    with zipfile.ZipFile(mem, "w", zipfile.ZIP_STORED) as zf:
        for job_id in wanted:
            job = db.get_job(job_id)
            if not job or job["status"] != "complete" or not job["output_clean"]:
                continue
            path = Path(job["output_clean"])
            if path.exists():
                name = f"{_safe_filename_part(job['owner'])}-{job['renderer']}-{job['duration']}s-{job_id[:8]}.mp4"
                zf.write(path, name)
                included.append(job_id)
    mem.seek(0)
    return StreamingResponse(
        mem,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=ugc-videos.zip"},
        background=BackgroundTask(_mark_many_downloaded, included),
    )


@app.get("/api/session")
def session(x_access_token: str | None = Header(default=None)) -> dict:
    _check_auth(x_access_token)
    jobs = db.list_jobs()
    outstanding = sum(1 for j in jobs if j["status"] in {"queued", "rendering", "cleaning"})
    undownloaded = sum(1 for j in jobs if j["status"] == "complete" and not j["downloaded"])
    counts = db.job_counts()
    outstanding = sum(counts.get(s, 0) for s in ("queued", "rendering", "cleaning"))
    return {**session_status(), "mode": settings.ugc_renderer_mode, "active_jobs": outstanding, "undownloaded_outputs": undownloaded,
            "state": db.get_kv("session_state", "generating" if outstanding else "idle"),
            "worker_blocked": db.get_kv("worker_blocked"), "end_now": db.get_kv("end_now", False), "counts": counts}


@app.post("/api/session/terminate")
async def terminate(background_tasks: BackgroundTasks, force: bool = Query(False), x_access_token: str | None = Header(default=None)) -> dict:
    _check_auth(x_access_token)
    jobs = db.list_jobs()
    active = [j for j in jobs if j["status"] in {"queued", "rendering", "cleaning"}]
    undownloaded = [j for j in jobs if j["status"] == "complete" and not j["downloaded"]]
    if not force and (active or undownloaded):
        raise HTTPException(409, detail={"active_jobs": len(active), "undownloaded_outputs": len(undownloaded)})
    if settings.ugc_renderer_mode == "mock" and not settings.runpod_session_name:
        return {"ok": True, "mock": True, "message": "Mock mode does not own a Runpod Pod"}
    pod_id = resolve_pod_id()
    if not pod_id:
        raise HTTPException(503, "Could not resolve the current Runpod Pod; refusing to fake termination")
    db.begin_shutdown(force=force)
    if settings.external_guardian:
        db.set_kv("end_now", force)
        return {"ok": True, "terminating": True, "verification": "pending_external_guardian"}
    background_tasks.add_task(terminate_pod_delayed)
    return {"ok": True, "terminating": True}


@app.get("/liveness")
@app.get("/health")
def liveness():
    return {"alive": True}


@app.get("/model-status")
def model_status():
    import json
    if gate_reason():
        return {"model": "h3-fl2va", "state": "disabled", "reason": gate_reason()}
    try:
        return json.loads(settings.h3_model_ready_file.read_text())
    except (OSError, ValueError):
        return {"model": "h3-fl2va", "state": "model_loading"}


@app.get("/readiness")
def readiness():
    status = model_status()
    if status.get("state") != "ready" or db.get_kv("worker_blocked"):
        raise HTTPException(503, status)
    return status


@app.post("/api/session/end")
def end_session(x_access_token: str | None = Header(default=None)):
    _check_auth(x_access_token)
    db.begin_shutdown()
    return session(x_access_token)


@app.get("/api/jobs/{job_id}/archive")
def archive_video(job_id: str, x_access_token: str | None = Header(default=None)):
    _check_auth(x_access_token)
    db.set_kv("external_guardian", True)
    job = db.get_job(job_id)
    if not job or job["status"] != "complete":
        raise HTTPException(404, "Video not ready")
    return FileResponse(job["output_clean"], media_type="video/mp4")


@app.post("/api/jobs/{job_id}/archived")
def archive_ack(job_id: str, x_access_token: str | None = Header(default=None)):
    _check_auth(x_access_token)
    job = db.get_job(job_id)
    if not job or job["status"] != "complete":
        raise HTTPException(404, "Video not ready")
    db.set_kv("archived:" + job_id, True)
    return {"ok": True}


@app.post("/api/jobs/{job_id}/retry")
def retry(job_id: str, x_access_token: str | None = Header(default=None)):
    _check_auth(x_access_token)
    job = db.get_job(job_id)
    if job and job["renderer"] == "h3-fl2va" and gate_reason():
        raise HTTPException(403, gate_reason())
    if db.get_kv("worker_blocked"):
        raise HTTPException(409, db.get_kv("worker_blocked"))
    if not db.retry_job(job_id):
        raise HTTPException(409, "Only failed jobs in an open session can be retried")
    return {"ok": True}


@app.get("/api/metrics")
def metrics(x_access_token: str | None = Header(default=None)):
    _check_auth(x_access_token)
    from app.metrics import snapshot
    return snapshot()
