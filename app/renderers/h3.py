"""Resident, local SGLang FL2VA adapter. Never falls back to a paid inference API."""
from __future__ import annotations
import time
from urllib.parse import urlparse, quote
import httpx
from app import db
from app.config import settings
from app.h3 import require_h3
from app.renderers.base import RenderRequest, Renderer


def build_payload(req: RenderRequest) -> dict:
    conditions = []
    for frame, index in ((req.start_frame, 0), (req.end_frame, -1)):
        if frame:
            conditions.append({"type": "image", "uri": frame.resolve().as_uri(),
                               "role": "keyframe", "frame_index": index})
    return {
        "model": "MiniMaxAI/MiniMax-H3", "prompt": req.prompt,
        "seconds": req.duration, "task": "fl2va" if conditions else "t2va",
        "conditions": conditions,
        "target": {"short_edge": 768, "aspect_ratio": "auto" if conditions else "9:16",
                   "duration_seconds": float(req.duration)},
        "num_outputs_per_prompt": 1, "num_inference_steps": 50,
        "flow_shift": 12.0, "audio_flow_shift": 3.0, "seed": req.seed,
        "quality": "lossless",
    }


class H3Renderer(Renderer):
    id = "h3-fl2va"

    def render(self, req: RenderRequest) -> None:
        try:
            self._render(req)
        except httpx.HTTPError as exc:
            if not isinstance(exc, httpx.HTTPStatusError) or exc.response.status_code >= 500:
                db.set_kv("worker_blocked", "SGLang connection or server failure; recover the worker before retrying ambiguous requests")
            raise

    def _render(self, req: RenderRequest) -> None:
        require_h3()
        url = urlparse(settings.h3_sglang_url)
        if url.scheme != "http" or url.hostname not in {"127.0.0.1", "localhost"} or url.username or url.password:
            raise ValueError("H3 SGLang must run on this worker's loopback interface")
        # A lost submit response is ambiguous. Never blindly retry POST /v1/videos.
        deadline = time.monotonic() + settings.render_timeout_seconds
        with httpx.Client(base_url=settings.h3_sglang_url, timeout=30, trust_env=False) as client:
            response = client.post("/v1/videos", json=build_payload(req))
            response.raise_for_status()
            remote_id = response.json()["id"]
            db.update_job(req.job_id, engine_job_id=remote_id)
            resource = "/v1/videos/" + quote(str(remote_id), safe="")
            while time.monotonic() < deadline:
                response = client.get(resource)
                response.raise_for_status()
                result = response.json()
                if result["status"] == "completed":
                    break
                if result["status"] in {"failed", "cancelled"}:
                    raise RuntimeError(f"H3 generation failed: {result.get('error') or result['status']}")
                time.sleep(1)
            else:
                # Stop further submissions; the timed-out request may still run remotely.
                db.set_kv("worker_blocked", "H3 request timed out; restart the worker before submitting more jobs")
                raise TimeoutError("H3 generation timed out; engine state requires recovery")
            req.output_path.parent.mkdir(parents=True, exist_ok=True)
            with client.stream("GET", resource + "/content") as response:
                response.raise_for_status()
                with req.output_path.open("wb") as out:
                    for chunk in response.iter_bytes():
                        out.write(chunk)
            if req.output_path.stat().st_size < 1024:
                raise RuntimeError("H3 returned an empty or invalid video")
