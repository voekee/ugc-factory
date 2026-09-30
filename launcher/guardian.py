"""CPU-side session guardian. Runs independently of browser polling.

The local launcher must remain running. The worker watchdog is a second defense;
for unattended operation while this Mac is off, deploy this controller on an
always-on CPU host. No successful termination is reported without a fresh listing.
"""
from __future__ import annotations
import json
import logging
import re
import threading
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import runpod

log = logging.getLogger(__name__)


def terminate_verified(api_key: str, pod_id: str, attempts: int = 3, pause: float = 2) -> None:
    runpod.api_key = api_key
    last = None
    for attempt in range(attempts):
        try:
            pods = runpod.get_pods(api_key=api_key)
            if not any(str(p.get("id")) == pod_id for p in pods):
                return
            try:
                runpod.terminate_pod(pod_id)
            except Exception as exc:
                last = exc
            pods = runpod.get_pods(api_key=api_key)
            if not any(str(p.get("id")) == pod_id for p in pods):
                return
        except Exception as exc:
            last = exc
        if attempt + 1 < attempts:
            time.sleep(pause)
    raise RuntimeError("Pod termination is not verified; the session remains tracked and termination will be retried") from last


def token_for(session: dict) -> str:
    token = session.get("session_token") or session.get("access_token")
    if token:
        return token
    url = urlparse(session.get("workspace_url", ""))
    return (parse_qs(url.query).get("session_token") or parse_qs(url.fragment).get("token") or [""])[0]


def worker_request(session: dict, path: str, method: str = "GET"):
    pod = str(session["pod_id"])
    if not re.fullmatch(r"[a-zA-Z0-9]+", pod):
        raise ValueError("Invalid Pod ID")
    return urllib.request.Request(f"https://{pod}-8000.proxy.runpod.net" + path,
        headers={"X-Access-Token": token_for(session), "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Version/26.0 Safari/605.1.15"}, method=method)


def worker_json(session: dict, path: str, method: str = "GET") -> dict:
    with urllib.request.urlopen(worker_request(session, path, method), timeout=15) as response:
        return json.load(response)


def archive_outputs(session: dict, root: Path) -> dict:
    """Fetch complete outputs once, atomically, before shutdown. Never mark a partial file archived."""
    began = time.monotonic()
    jobs = []
    while True:
        page = worker_json(session, f"/api/jobs?offset={len(jobs)}")["jobs"]
        jobs.extend(page)
        if len(page) < 500:
            break
    folder = root / str(session["pod_id"])
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    for job in jobs:
        job_id = str(job["id"])
        if not re.fullmatch(r"[a-f0-9]{32}", job_id):
            raise ValueError("Invalid job ID in worker response")
        if job["status"] != "complete":
            continue
        dest = folder / f"{job_id}.mp4"
        marker = folder / f"{job_id}.archived"
        if dest.exists() and marker.exists():
            continue
        if time.monotonic() - began > 30:
            raise TimeoutError("Archive pass time budget reached; continuing next pass")
        if not dest.exists():
            partial = dest.with_suffix(".part")
            try:
                with urllib.request.urlopen(worker_request(session, f"/api/jobs/{job_id}/archive"), timeout=30) as response, partial.open("wb") as out:
                    while chunk := response.read(1024 * 1024):
                        if time.monotonic() - began > 60:
                            raise TimeoutError("Output backup timed out")
                        out.write(chunk)
                    out.flush()
                    import os
                    os.fsync(out.fileno())
                if partial.stat().st_size < 1024:
                    raise ValueError("Worker returned an invalid video")
                partial.replace(dest)
            finally:
                partial.unlink(missing_ok=True)
        metadata = folder / f"{job_id}.json"
        temp = metadata.with_suffix(".tmp")
        temp.write_text(json.dumps(job, indent=2))
        temp.replace(metadata)
        # Only acknowledge persistence after file and metadata are durable locally.
        worker_json(session, f"/api/jobs/{job_id}/archived", "POST")
        marker.touch()
    manifest = folder / "jobs.json"
    temp = manifest.with_suffix(".tmp")
    temp.write_text(json.dumps(jobs, indent=2))
    temp.replace(manifest)
    return {"jobs": len(jobs), "complete": sum(j["status"] == "complete" for j in jobs)}


class Guardian:
    def __init__(self, read_config, write_config, archive_root: Path, lock=None):
        self.read = read_config
        self.write = write_config
        self.archive_root = archive_root
        self.lock = lock or threading.RLock()
        self.stop = threading.Event()

    def tick(self):
        with self.lock:
            config = self.read()
            session = config.get("active_session")
            key = config.get("runpod_api_key")
            if not key:
                return
            pods = runpod.get_pods(api_key=key)
            pending = config.get("pending_creation")
            if pending:
                matches = [p for p in pods if p.get("name") == pending["session_name"]]
                for pod in matches:
                    terminate_verified(key, str(pod["id"]))
                # Keep an ambiguous creation journal until an operator explicitly resolves it.
                # A delayed RunPod allocation can appear after an initially empty list.
                if matches:
                    config.setdefault("session_history", []).extend({**pending, "pod_id": p["id"],
                        "state": "terminated", "termination_verified": True} for p in matches)
                    config.pop("pending_creation", None)
            tracked = {str(s["pod_id"]) for s in config.get("session_history", []) if s.get("state") == "terminated"}
            for pod in pods:
                if str(pod["id"]) in tracked:
                    terminate_verified(key, str(pod["id"]))
            known = tracked | ({str(session["pod_id"])} if session else set())
            config["orphan_pods"] = [{"pod_id": p["id"], "name": p.get("name"), "status": p.get("desiredStatus")}
                                     for p in pods if str(p.get("name", "")).startswith("ugc-factory-") and str(p["id"]) not in known]
            self.write(config)
            if not session:
                return
            pod_id = str(session["pod_id"])
            pods = runpod.get_pods(api_key=key)
            if not any(str(p.get("id")) == pod_id for p in pods):
                self._closed(config, session)
                return
            actual = next(p for p in pods if str(p.get("id")) == pod_id)
            if actual.get("costPerHr") is not None:
                session["actual_hourly_rate_usd"] = float(actual["costPerHr"])
            now = datetime.now(timezone.utc)
            started = datetime.fromisoformat(session["started_at"].replace("Z", "+00:00"))
            expired = (now - started).total_seconds() >= float(session.get("hours", 6)) * 3600
            status = {}
            try:
                archive_outputs(session, self.archive_root)
                status = worker_json(session, "/api/session")
                session.pop("archive_error", None)
            except Exception:
                session["archive_error"] = "Output backup or worker status is unavailable; retrying"
            terminate = expired or session.get("state") == "ending_now"
            if status:
                terminate = terminate or bool(status.get("end_now"))
                busy = status.get("active_jobs", 0) > 0
                if busy:
                    session["idle_since"] = None
                elif not session.get("idle_since"):
                    session["idle_since"] = now.isoformat()
                idle = session.get("idle_since")
                idle_expired = idle and (now - datetime.fromisoformat(idle)).total_seconds() >= int(session.get("idle_timeout_seconds", 600))
                if not busy and (idle_expired or session.get("state") == "ending" or status.get("state") == "ending"):
                    # Prevent a race with new submissions and drain anything accepted before the barrier.
                    drained = worker_json(session, "/api/session/end", "POST")
                    if not drained.get("active_jobs") and not session.get("archive_error"):
                        # Capture outputs that completed between the first archive pass and the drain barrier.
                        archive_outputs(session, self.archive_root)
                        terminate = True
            config["active_session"] = session
            self.write(config)
            if terminate:
                session["state"] = "ending_now"
                self.write(config)
                terminate_verified(key, pod_id)
                self._closed(config, session)

    def _closed(self, config, session):
        closed = {**session, "state": "terminated", "terminated_at": datetime.now(timezone.utc).isoformat(), "termination_verified": True}
        config.setdefault("session_history", []).append(closed)
        config.pop("active_session", None)
        self.write(config)

    def run(self):
        while not self.stop.is_set():
            try:
                self.tick()
            except Exception:
                log.warning("Session guardian check failed; will retry", exc_info=False)
            self.stop.wait(15)
