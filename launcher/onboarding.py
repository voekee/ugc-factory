#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import secrets
import stat
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from runpod_launcher import launch_pod

ROOT = Path(__file__).resolve().parents[1]
UI_PATH = Path(__file__).with_name("onboarding.html")
CONFIG_DIR = Path.home() / ".ugc-factory"
CONFIG_PATH = CONFIG_DIR / "config.json"

DEFAULTS = {
    "image": "ghcr.io/voekee/ugc-factory:latest",
    "gpu": "AUTO",
    "cloud": "ALL",
    "hours": 5.0,
    "disk": 180,
    "rate": 0.99,
}

LOCAL_TOKEN = secrets.token_urlsafe(24)
STATE: dict[str, Any] = {
    "launching": False,
    "pod_id": "",
    "dashboard_url": "",
    "workspace_url": "",
    "selected_gpu": "",
    "selected_cloud": "",
    "error": "",
}


def _read_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(CONFIG_PATH.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def _write_config(config: dict[str, Any]) -> None:
    config = {**config, "config_version": 2}
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(CONFIG_DIR, 0o700)
    except OSError:
        pass

    tmp = CONFIG_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(config, indent=2) + "\n")
    try:
        os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass
    tmp.replace(CONFIG_PATH)
    try:
        os.chmod(CONFIG_PATH, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass


def _mask(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "••••••••"
    return "••••••••" + value[-4:]


def _public_config() -> dict[str, Any]:
    saved = _read_config()
    legacy = int(saved.get("config_version", 1)) < 2
    return {
        "config_path": str(CONFIG_PATH),
        "runpod_saved": bool(saved.get("runpod_api_key")),
        "runpod_masked": _mask(str(saved.get("runpod_api_key", ""))),
        "hf_saved": bool(saved.get("hf_token")),
        "hf_masked": _mask(str(saved.get("hf_token", ""))),
        "image": saved.get("image", DEFAULTS["image"]),
        "gpu": DEFAULTS["gpu"] if legacy else saved.get("gpu", DEFAULTS["gpu"]),
        "cloud": DEFAULTS["cloud"] if legacy else saved.get("cloud", DEFAULTS["cloud"]),
        "hours": saved.get("hours", DEFAULTS["hours"]),
        "disk": DEFAULTS["disk"] if legacy else saved.get("disk", DEFAULTS["disk"]),
        "rate": saved.get("rate", DEFAULTS["rate"]),
    }


def _merge_payload(payload: dict[str, Any]) -> dict[str, Any]:
    saved = _read_config()

    runpod_key = str(payload.get("runpod_api_key") or "").strip()
    hf_token = str(payload.get("hf_token") or "").strip()

    if not runpod_key:
        runpod_key = str(saved.get("runpod_api_key") or "").strip()
    if not hf_token:
        hf_token = str(saved.get("hf_token") or "").strip()

    config = {
        "runpod_api_key": runpod_key,
        "hf_token": hf_token,
        "image": str(payload.get("image") or saved.get("image") or DEFAULTS["image"]).strip(),
        "gpu": str(payload.get("gpu") or saved.get("gpu") or DEFAULTS["gpu"]).strip(),
        "cloud": str(payload.get("cloud") or saved.get("cloud") or DEFAULTS["cloud"]).strip().upper(),
        "hours": float(payload.get("hours") or saved.get("hours") or DEFAULTS["hours"]),
        "disk": int(payload.get("disk") or saved.get("disk") or DEFAULTS["disk"]),
        "rate": float(payload.get("rate") if payload.get("rate") not in ("", None) else saved.get("rate", DEFAULTS["rate"])),
    }

    if not config["runpod_api_key"]:
        raise ValueError("Runpod API key is required.")
    if not config["image"]:
        raise ValueError("Container image is required.")
    if config["cloud"] not in {"ALL", "SECURE", "COMMUNITY"}:
        raise ValueError("Cloud must be ALL, SECURE or COMMUNITY.")
    if not 0.25 <= config["hours"] <= 24:
        raise ValueError("Session length must be between 0.25 and 24 hours.")
    if not 100 <= config["disk"] <= 1000:
        raise ValueError("Ephemeral disk must be between 100 and 1000 GB.")
    if config["rate"] < 0:
        raise ValueError("Hourly display rate cannot be negative.")

    return config


def _probe_workspace(url: str) -> bool:
    if not url:
        return False
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/api/health", timeout=4) as response:
            return response.status == 200
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


class Handler(BaseHTTPRequestHandler):
    server_version = "UGCFactoryLauncher/1.0"

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _authorized(self) -> bool:
        query = parse_qs(urlparse(self.path).query)
        query_token = (query.get("t") or [""])[0]
        header_token = self.headers.get("X-Launcher-Token", "")
        return secrets.compare_digest(query_token or header_token, LOCAL_TOKEN)

    def _json(self, payload: Any, status: int = 200) -> None:
        raw = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", f"http://127.0.0.1:{self.server.server_port}")
        self.send_header("Vary", "Origin")
        self.end_headers()
        self.wfile.write(raw)

    def _read_json(self) -> dict[str, Any]:
        size = int(self.headers.get("Content-Length", "0"))
        if size <= 0 or size > 64 * 1024:
            return {}
        return json.loads(self.rfile.read(size).decode())

    def do_GET(self) -> None:
        parsed = urlparse(self.path)

        if parsed.path == "/":
            if not self._authorized():
                self.send_error(HTTPStatus.FORBIDDEN)
                return
            html = UI_PATH.read_text().replace("__LAUNCHER_TOKEN__", LOCAL_TOKEN)
            raw = html.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(raw)
            return

        if not self._authorized():
            self._json({"error": "Unauthorized local launcher request."}, 403)
            return

        if parsed.path == "/api/bootstrap":
            self._json(_public_config())
            return

        if parsed.path == "/api/status":
            ready = _probe_workspace(STATE["dashboard_url"]) if STATE["dashboard_url"] else False
            self._json({
                **STATE,
                "ready": ready,
                "config_path": str(CONFIG_PATH),
            })
            return

        self.send_error(404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)

        if not self._authorized():
            self._json({"error": "Unauthorized local launcher request."}, 403)
            return

        if parsed.path == "/api/forget":
            try:
                CONFIG_PATH.unlink(missing_ok=True)
                self._json({"ok": True})
            except OSError as exc:
                self._json({"error": str(exc)}, 500)
            return

        if parsed.path != "/api/launch":
            self.send_error(404)
            return

        if STATE["launching"]:
            self._json({"error": "A Pod is already being created."}, 409)
            return

        try:
            payload = self._read_json()
            config = _merge_payload(payload)
            remember = bool(payload.get("remember", True))

            if remember:
                _write_config(config)

            STATE.update({
                "launching": True,
                "pod_id": "",
                "dashboard_url": "",
                "workspace_url": "",
                "selected_gpu": "",
                "selected_cloud": "",
                "error": "",
            })

            result = launch_pod(
                api_key=config["runpod_api_key"],
                image=config["image"],
                gpu=config["gpu"],
                cloud=config["cloud"],
                hours=config["hours"],
                disk=config["disk"],
                hf_token=config["hf_token"],
                rate=config["rate"],
            )

            STATE.update({
                "launching": False,
                "pod_id": result["pod_id"],
                "dashboard_url": result["dashboard_url"],
                "workspace_url": result["workspace_url"],
                "selected_gpu": result.get("selected_gpu", ""),
                "selected_cloud": result.get("selected_cloud", ""),
                "error": "",
            })
            self._json({
                "ok": True,
                **STATE,
                "config_path": str(CONFIG_PATH),
            })
        except Exception as exc:
            STATE.update({"launching": False, "error": str(exc)})
            self._json({"error": str(exc)}, 400)


def main() -> None:
    parser = argparse.ArgumentParser(description="Open the local UGC Factory onboarding launcher")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args()

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    port = server.server_port
    url = f"http://127.0.0.1:{port}/?t={LOCAL_TOKEN}"

    print("UGC Factory local launcher")
    print(f"Open: {url}")
    print(f"Local config: {CONFIG_PATH}")
    print("Secrets stay on this computer and are never written to the repository.")

    if not args.no_browser:
        threading.Timer(0.35, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
