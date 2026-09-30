"""Boot one FL2VA family, warm it, then keep SGLang resident for the session."""
from __future__ import annotations
import json
import os
from pathlib import Path
import signal
import subprocess
import time
import httpx
from app.config import settings
from app.h3 import PROFILES, require_h3


def main():
    require_h3()
    ready = settings.h3_model_ready_file
    ready.unlink(missing_ok=True)
    model_root = Path(os.environ.get("H3_MODEL_PATH", "/runpod-volume/models/MiniMax-H3"))
    if not (model_root / "FL2VA").is_dir():
        raise RuntimeError("Pre-stage FL2VA weights on the persistent volume; startup will not download a checkpoint")
    profile = PROFILES[settings.h3_profile]
    started = time.monotonic()
    command = ["sglang", "serve", "--model-path", str(model_root), "--model-variant", "fl2va",
               "--num-gpus", str(profile["count"]), "--encoder-parallel", "auto",
               *profile["flags"], "--host", "127.0.0.1", "--port", "30010"]
    process = subprocess.Popen(command)
    api = None
    def stop(*_):
        if api:
            api.terminate()
        process.terminate()
        raise SystemExit(0)
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    # Start health and job APIs while the model loads; readiness stays false.
    api = subprocess.Popen(["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"])
    deadline = started + 1800
    try:
        with httpx.Client(base_url=settings.h3_sglang_url, timeout=10, trust_env=False) as client:
            while time.monotonic() < deadline:
                if process.poll() is not None or api.poll() is not None:
                    raise RuntimeError("H3 runtime exited during startup")
                try:
                    response = client.get("/health")
                    if response.is_success:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(2)
            else:
                raise TimeoutError("H3 startup exceeded 30 minutes")
            loaded = time.monotonic()
            ready.write_text(json.dumps({"model": "h3-fl2va", "state": "model_warming"}))
            # A successful full request validates encode/mux as well as CUDA startup.
            warm = {"model": "MiniMaxAI/MiniMax-H3", "prompt": "A closed cardboard package rests on a table in natural window light. Quiet room tone.",
                    "seconds": 4, "task": "t2va", "conditions": [],
                    "target": {"short_edge": 768, "aspect_ratio": "9:16", "duration_seconds": 4.0},
                    "num_inference_steps": 50, "num_outputs_per_prompt": 1, "seed": 1,
                    "flow_shift": 12.0, "audio_flow_shift": 3.0, "quality": "lossless"}
            response = client.post("/v1/videos", json=warm)
            response.raise_for_status()
            remote_id = response.json()["id"]
            deadline = time.monotonic() + settings.render_timeout_seconds
            while time.monotonic() < deadline:
                if process.poll() is not None or api.poll() is not None:
                    raise RuntimeError("H3 runtime exited during warm-up")
                response = client.get(f"/v1/videos/{remote_id}")
                response.raise_for_status()
                result = response.json()
                if result["status"] == "completed":
                    break
                if result["status"] == "failed":
                    raise RuntimeError("H3 warm-up failed")
                time.sleep(2)
            else:
                raise TimeoutError("H3 warm-up timed out")
            snapshot = {"model": "h3-fl2va", "state": "ready", "profile": settings.h3_profile,
                        "model_load_seconds": loaded-started, "warmup_seconds": time.monotonic()-loaded}
            tmp = ready.with_suffix(".tmp")
            tmp.write_text(json.dumps(snapshot))
            tmp.replace(ready)
        while process.poll() is None and api.poll() is None:
            time.sleep(1)
        raise RuntimeError("H3 runtime exited")
    finally:
        ready.unlink(missing_ok=True)
        for child in (api, process):
            if child and child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()


if __name__ == "__main__":
    main()
