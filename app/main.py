from __future__ import annotations

from contextlib import asynccontextmanager
import base64
import binascii
import io
import random
import re
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

from app import db
from app.config import settings
from app.models import JobStatus, RENDERERS
from app.queue_worker import start_worker, stop_worker
from app.runpod import resolve_pod_id, session_status, terminate_pod_delayed
from app.watchdog import start_watchdog

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"

@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    (settings.data_dir / "inputs").mkdir(parents=True, exist_ok=True)
    db.init_db()
    start_worker()
    start_watchdog()
    try:
        yield
    finally:
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

    try:
        payload = base64.b64decode(match.group(2), validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(400, f"Invalid base64 data for {name} image") from exc

    max_bytes = settings.max_upload_mb * 1024 * 1024
    if len(payload) > max_bytes:
        raise HTTPException(413, f"{name} image exceeds {settings.max_upload_mb} MB")

    path = settings.data_dir / "inputs" / f"{batch_id}_{name}{suffix}"
    path.write_bytes(payload)
    return str(path)


def _create_job_records(
    *,
    owner: str,
    renderer: str,
    prompt: str,
    duration: int,
    variations: int,
    start_path: str | None,
    end_path: str | None,
) -> dict:
    owner = owner.strip()[:40]
    prompt = prompt.strip()

    if not owner:
        raise HTTPException(400, "Creator name is required")
    if not prompt:
        raise HTTPException(400, "Prompt is required")
    if renderer not in RENDERERS:
        raise HTTPException(400, "Unknown renderer")

    caps = RENDERERS[renderer]
    if duration not in caps.supported_durations:
        raise HTTPException(400, f"{caps.name} does not support {duration}s in this adapter")
    if not 1 <= variations <= 100:
        raise HTTPException(400, "Variations must be between 1 and 100")
    if caps.supports_start_frame and not start_path:
        raise HTTPException(400, "Start/reference frame is required for this model")
    if end_path and not caps.supports_end_frame:
        raise HTTPException(400, f"{caps.name} does not support a native end frame in V1")

    batch_id = Path(start_path).name.split("_", 1)[0] if start_path else uuid.uuid4().hex[:12]
    ids: list[str] = []

    for _ in range(variations):
        job_id = uuid.uuid4().hex
        ids.append(job_id)
        db.create_job({
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
        })

    return {"batch_id": batch_id, "job_ids": ids}


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return (STATIC / "index.html").read_text()


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "mode": settings.ugc_renderer_mode}


@app.get("/api/renderers", dependencies=[])
def renderers(x_access_token: str | None = Header(default=None)) -> dict:
    _check_auth(x_access_token)
    return {"renderers": [r.dict() for r in RENDERERS.values()]}


def _read_job_log(job_id: str, max_chars: int = 5000) -> str:
    path = settings.data_dir / "logs" / f"{job_id}.log"
    if not path.exists():
        return ""
    try:
        with path.open("rb") as log:
            log.seek(0, 2)
            log.seek(max(0, log.tell() - max_chars * 4))
            data = log.read().decode("utf-8", errors="replace")
    except OSError:
        return ""
    return data[-max_chars:]


def _job_phase(job: dict) -> tuple[str, str]:
    if job["status"] == "queued":
        return "Queued", "Waiting for the worker"
    if job["status"] == "cleaning":
        return "Finalizing MP4", "Encoding, removing metadata, and validating the output"
    if job["status"] == "complete":
        return "Ready", "Finished"
    if job["status"] == "failed":
        return "Failed", "Open the renderer error for details"
    if job["status"] != "rendering":
        return job["status"].title(), ""

    log = _read_job_log(job["id"])
    lower = log.lower()
    if "converting model output" in lower or "encoding mp4" in lower:
        return "Encoding MP4", "Preparing the social-ready file"
    if "decoding video" in lower or "video decoder" in lower:
        return "Decoding video", "Turning generated frames into video"
    if "denoising" in lower or "diffusion stage" in lower or "sampling" in lower:
        return "GPU inference", "Generating video frames on the GPU"
    if "building transformer" in lower or "loading transformer" in lower:
        return "Loading transformer", "Warming the video model"
    if "text encoder" in lower:
        return "Loading text encoder", "Preparing the prompt"
    if "[LTX] Loading model and starting render:" in log:
        return "Loading model", "Warming model weights"
    if "[LTX] Downloading LTX-2.5 model weights..." in log:
        return "Downloading LTX-2.5", "First-run model weights are downloading to this temporary Pod"
    if "fetching" in lower or "downloading" in lower:
        return "Downloading model weights", "First use downloads weights to the temporary Pod"
    if "[LTX] Runtime baked into container." in log:
        return "Checking GPU runtime", "LTX code and Python dependencies are already installed in the container"
    return "Preparing renderer", "Checking the model runtime"


def _enrich_job(job: dict, queue_position: int | None = None) -> dict:
    phase, phase_detail = _job_phase(job)
    live_log = _read_job_log(job["id"], max_chars=3000) if job["status"] == "rendering" else ""
    try:
        updated = datetime.fromisoformat(job["updated_at"])
        elapsed = max(0, int((datetime.now(timezone.utc) - updated).total_seconds())) if job["status"] in {"rendering", "cleaning"} else 0
    except (TypeError, ValueError):
        elapsed = 0
    return {
        **job,
        "phase": phase,
        "phase_detail": phase_detail,
        "live_log": live_log,
        "queue_position": queue_position,
        "elapsed_seconds": elapsed,
    }


@app.get("/api/jobs")
def jobs(x_access_token: str | None = Header(default=None)) -> dict:
    _check_auth(x_access_token)
    records = db.list_jobs()
    queued = sorted((job for job in records if job["status"] == "queued"), key=lambda job: (job["created_at"], job["id"]))
    positions = {job["id"]: index for index, job in enumerate(queued, 1)}
    return {"jobs": [_enrich_job(job, positions.get(job["id"])) for job in records]}


@app.get("/api/jobs/{job_id}/log")
def job_log(job_id: str, x_access_token: str | None = Header(default=None)) -> dict:
    _check_auth(x_access_token)
    if not db.get_job(job_id):
        raise HTTPException(404, "Job not found")
    return {"log": _read_job_log(job_id, max_chars=100_000)}


async def _save_upload(upload: UploadFile | None, batch_id: str, name: str) -> str | None:
    if upload is None or not upload.filename:
        return None
    suffix = Path(upload.filename).suffix.lower()
    if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise HTTPException(400, f"Unsupported image type: {suffix}")
    path = settings.data_dir / "inputs" / f"{batch_id}_{name}{suffix}"
    total = 0
    with path.open("wb") as out:
        while chunk := await upload.read(1024 * 1024):
            total += len(chunk)
            if total > settings.max_upload_mb * 1024 * 1024:
                out.close(); path.unlink(missing_ok=True)
                raise HTTPException(413, "Upload too large")
            out.write(chunk)
    return str(path)


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
    )


@app.post("/api/jobs")
async def create_jobs(
    owner: str = Form(...),
    renderer: str = Form(...),
    prompt: str = Form(...),
    duration: int = Form(...),
    variations: int = Form(...),
    start_frame: UploadFile | None = File(default=None),
    end_frame: UploadFile | None = File(default=None),
    x_access_token: str | None = Header(default=None),
) -> dict:
    _check_auth(x_access_token)
    owner = owner.strip()[:40]
    prompt = prompt.strip()
    if not owner or not prompt:
        raise HTTPException(400, "Owner and prompt are required")
    if renderer not in RENDERERS:
        raise HTTPException(400, "Unknown renderer")
    caps = RENDERERS[renderer]
    if duration not in caps.supported_durations:
        raise HTTPException(400, f"{caps.name} does not support {duration}s in this adapter")
    if not 1 <= variations <= 100:
        raise HTTPException(400, "Variations must be between 1 and 100")
    if caps.supports_start_frame and start_frame is None:
        raise HTTPException(400, "This renderer requires a start/reference frame in V1")
    if end_frame is not None and not caps.supports_end_frame:
        raise HTTPException(400, f"{caps.name} does not support a native end frame in V1")

    batch_id = uuid.uuid4().hex[:12]
    start_path = await _save_upload(start_frame, batch_id, "start")
    end_path = await _save_upload(end_frame, batch_id, "end")

    ids = []
    for _ in range(variations):
        job_id = uuid.uuid4().hex
        ids.append(job_id)
        db.create_job({
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
        })
    return {"batch_id": batch_id, "job_ids": ids}


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
def video(job_id: str, token: str | None = Query(default=None), x_access_token: str | None = Header(default=None)):
    _check_auth(x_access_token or token)
    job = db.get_job(job_id)
    if not job or job["status"] != JobStatus.COMPLETE.value or not job["output_clean"]:
        raise HTTPException(404, "Video not ready")
    return FileResponse(job["output_clean"], media_type="video/mp4")


@app.get("/api/jobs/{job_id}/download")
def download(job_id: str, token: str | None = Query(default=None), x_access_token: str | None = Header(default=None)):
    _check_auth(x_access_token or token)
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
def download_zip(ids: str = Query(...), token: str | None = Query(default=None), x_access_token: str | None = Header(default=None)):
    _check_auth(x_access_token or token)
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
    return {**session_status(), "active_jobs": outstanding, "undownloaded_outputs": undownloaded}


@app.post("/api/session/terminate")
async def terminate(background_tasks: BackgroundTasks, force: bool = Query(False), x_access_token: str | None = Header(default=None)) -> dict:
    _check_auth(x_access_token)
    jobs = db.list_jobs()
    active = [j for j in jobs if j["status"] in {"queued", "rendering", "cleaning"}]
    undownloaded = [j for j in jobs if j["status"] == "complete" and not j["downloaded"]]
    if not force and (active or undownloaded):
        raise HTTPException(409, detail={"active_jobs": len(active), "undownloaded_outputs": len(undownloaded)})
    if settings.ugc_renderer_mode == "mock":
        return {"ok": True, "mock": True, "message": "Mock mode does not own a Runpod Pod"}
    pod_id = resolve_pod_id()
    if not pod_id:
        raise HTTPException(503, "Could not resolve the current Runpod Pod; refusing to fake termination")
    background_tasks.add_task(terminate_pod_delayed)
    return {"ok": True, "terminating": True}
