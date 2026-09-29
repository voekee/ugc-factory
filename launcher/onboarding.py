#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import secrets
import stat
import threading
import urllib.error
import urllib.request
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import runpod
from runpod.api.graphql import run_graphql_query

from runpod_launcher import launch_pod

UI_PATH = Path(__file__).with_name("onboarding.html")
CONFIG_DIR = Path.home() / ".ugc-factory"
CONFIG_PATH = CONFIG_DIR / "config.json"

DEFAULTS = {
    "image": "ghcr.io/voekee/ugc-factory:latest",
    "hours": 1.0,
    "disk": 180,
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

GPU_QUERY = """
query {
  gpuTypes {
    id
    displayName
    memoryInGb
    secure: lowestPrice(input: { gpuCount: 1, secureCloud: true }) {
      stockStatus
      uninterruptablePrice
      availableGpuCounts
    }
    community: lowestPrice(input: { gpuCount: 1, secureCloud: false }) {
      stockStatus
      uninterruptablePrice
      availableGpuCounts
    }
  }
}
"""


def _read_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        return {}
    try:
        value = json.loads(CONFIG_PATH.read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _write_config(config: dict[str, Any]) -> None:
    payload = {**config, "config_version": 4}
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(CONFIG_DIR, 0o700)
    except OSError:
        pass

    tmp = CONFIG_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n")
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
    return {
        "config_path": str(CONFIG_PATH),
        "runpod_saved": bool(saved.get("runpod_api_key")),
        "runpod_masked": _mask(str(saved.get("runpod_api_key", ""))),
        "hf_saved": bool(saved.get("hf_token")),
        "hf_masked": _mask(str(saved.get("hf_token", ""))),
        "image": saved.get("image", DEFAULTS["image"]),
        "hours": float(saved.get("hours", DEFAULTS["hours"])),
        "disk": int(saved.get("disk", DEFAULTS["disk"])),
        "selected_gpu": saved.get("selected_gpu", ""),
        "selected_cloud": saved.get("selected_cloud", ""),
        "selected_price": saved.get("selected_price"),
        "selected_vram": saved.get("selected_vram"),
    }


def _validate_runpod_key(api_key: str) -> None:
    if not api_key:
        raise ValueError("Runpod API key is required.")
    run_graphql_query("query { myself { id } }", api_key=api_key)


def _validate_hf_token(token: str) -> None:
    if not token:
        return

    request = urllib.request.Request(
        "https://huggingface.co/api/whoami-v2",
        headers={
            "Authorization": f"Bearer {token}",
            "User-Agent": "UGC-Factory-Launcher/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            if response.status != 200:
                raise ValueError("Hugging Face token could not be validated.")
    except urllib.error.HTTPError as exc:
        if exc.code in {401, 403}:
            raise ValueError("Hugging Face token is invalid or does not have access.") from exc
        raise ValueError(f"Hugging Face validation failed: HTTP {exc.code}.") from exc
    except urllib.error.URLError as exc:
        raise ValueError("Could not reach Hugging Face to validate the token.") from exc


def _credentials_from_payload(payload: dict[str, Any]) -> tuple[str, str]:
    saved = _read_config()

    runpod_key = str(payload.get("runpod_api_key") or "").strip()
    hf_token = str(payload.get("hf_token") or "").strip()

    if not runpod_key:
        runpod_key = str(saved.get("runpod_api_key") or "").strip()
    if not hf_token:
        hf_token = str(saved.get("hf_token") or "").strip()

    return runpod_key, hf_token


def _save_credentials(runpod_key: str, hf_token: str) -> dict[str, Any]:
    current = _read_config()
    updated = {
        **current,
        "runpod_api_key": runpod_key,
        "hf_token": hf_token,
        "image": current.get("image", DEFAULTS["image"]),
        "hours": current.get("hours", DEFAULTS["hours"]),
        "disk": current.get("disk", DEFAULTS["disk"]),
    }
    _write_config(updated)
    return updated


def _stock_is_available(stock: Any, counts: Any) -> bool:
    normalized = str(stock or "").strip().lower()
    if normalized in {"", "none", "unavailable"}:
        return False

    if isinstance(counts, list) and counts:
        try:
            return 1 in [int(value) for value in counts]
        except (TypeError, ValueError):
            return True

    return normalized in {"high", "medium", "low"}


def _discover_gpu_offers(api_key: str) -> list[dict[str, Any]]:
    response = run_graphql_query(GPU_QUERY, api_key=api_key)
    gpu_types = response.get("data", {}).get("gpuTypes", []) or []

    offers: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    for gpu in gpu_types:
        gpu_id = str(gpu.get("id") or "")
        if not gpu_id.startswith("NVIDIA "):
            continue

        try:
            vram = int(gpu.get("memoryInGb") or 0)
        except (TypeError, ValueError):
            continue

        if vram < 24:
            continue

        display_name = str(gpu.get("displayName") or gpu_id.replace("NVIDIA ", ""))

        for field, cloud in (("community", "COMMUNITY"), ("secure", "SECURE")):
            price_data = gpu.get(field) or {}
            price = price_data.get("uninterruptablePrice")
            stock = price_data.get("stockStatus")
            counts = price_data.get("availableGpuCounts")

            if price is None or not _stock_is_available(stock, counts):
                continue

            key = (gpu_id, cloud)
            if key in seen:
                continue
            seen.add(key)

            try:
                price_float = float(price)
            except (TypeError, ValueError):
                continue

            offers.append({
                "gpu_id": gpu_id,
                "name": display_name,
                "vram_gb": vram,
                "cloud": cloud,
                "price_per_hour": round(price_float, 4),
                "stock": str(stock or "").upper(),
            })

    offers.sort(key=lambda item: (item["price_per_hour"], -item["vram_gb"], item["name"]))
    return offers


def _probe_workspace(url: str) -> bool:
    if not url:
        return False
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/api/health", timeout=4) as response:
            return response.status == 200
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def _clear_active_session() -> None:
    saved = _read_config()
    if "active_session" in saved:
        saved.pop("active_session", None)
        _write_config(saved)

    STATE.update({
        "launching": False,
        "pod_id": "",
        "dashboard_url": "",
        "workspace_url": "",
        "selected_gpu": "",
        "selected_cloud": "",
        "error": "",
    })


def _recover_active_session() -> dict[str, Any] | None:
    saved = _read_config()
    session = saved.get("active_session")
    if not isinstance(session, dict):
        return None

    pod_id = str(session.get("pod_id") or "").strip()
    api_key = str(saved.get("runpod_api_key") or "").strip()
    if not pod_id or not api_key:
        return None

    try:
        runpod.api_key = api_key
        pods = runpod.get_pods(api_key=api_key)
    except Exception:
        # If Runpod cannot be queried right now, keep the persisted session so
        # a temporary network problem does not make the UI forget a paid Pod.
        return session

    active = next((pod for pod in pods if str(pod.get("id") or "") == pod_id), None)
    if not active:
        _clear_active_session()
        return None

    return {
        **session,
        "pod_status": str(
            active.get("desiredStatus")
            or active.get("status")
            or active.get("runtime", {}).get("uptimeInSeconds")
            or "RUNNING"
        ),
    }


def _session_status_payload() -> dict[str, Any]:
    if STATE.get("pod_id"):
        session = {
            "pod_id": STATE["pod_id"],
            "dashboard_url": STATE["dashboard_url"],
            "workspace_url": STATE["workspace_url"],
            "selected_gpu": STATE["selected_gpu"],
            "selected_cloud": STATE["selected_cloud"],
        }
    else:
        session = _recover_active_session() or {}

    if session:
        STATE.update({
            "pod_id": str(session.get("pod_id") or ""),
            "dashboard_url": str(session.get("dashboard_url") or ""),
            "workspace_url": str(session.get("workspace_url") or ""),
            "selected_gpu": str(session.get("selected_gpu") or ""),
            "selected_cloud": str(session.get("selected_cloud") or ""),
        })

    dashboard_url = str(session.get("dashboard_url") or STATE.get("dashboard_url") or "")
    ready = _probe_workspace(dashboard_url) if dashboard_url else False

    return {
        **STATE,
        **session,
        "ready": ready,
        "active": bool(session.get("pod_id")),
        "config_path": str(CONFIG_PATH),
    }


def _terminate_active_session() -> dict[str, Any]:
    saved = _read_config()
    session = saved.get("active_session")
    if not isinstance(session, dict) and STATE.get("pod_id"):
        session = {
            "pod_id": STATE["pod_id"],
            "selected_gpu": STATE.get("selected_gpu", ""),
            "selected_cloud": STATE.get("selected_cloud", ""),
        }

    if not isinstance(session, dict) or not session.get("pod_id"):
        _clear_active_session()
        return {"ok": True, "already_stopped": True}

    api_key = str(saved.get("runpod_api_key") or "").strip()
    if not api_key:
        raise ValueError("Runpod API key is missing; cannot terminate the active Pod.")

    pod_id = str(session["pod_id"])
    runpod.api_key = api_key

    try:
        runpod.terminate_pod(pod_id)
    except Exception as exc:
        # If the Pod is already gone, clear local state. Otherwise surface the
        # error so users never believe spend stopped when it might not have.
        message = str(exc).lower()
        if "not found" not in message and "does not exist" not in message:
            raise

    _clear_active_session()
    return {"ok": True, "pod_id": pod_id}


class Handler(BaseHTTPRequestHandler):
    server_version = "UGCFactoryLauncher/2.0"

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
        self.end_headers()
        self.wfile.write(raw)

    def _read_json(self) -> dict[str, Any]:
        size = int(self.headers.get("Content-Length", "0"))
        if size <= 0 or size > 128 * 1024:
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

        if parsed.path == "/api/gpus":
            try:
                saved = _read_config()
                api_key = str(saved.get("runpod_api_key") or "")
                if not api_key:
                    raise ValueError("Save a Runpod API key first.")
                offers = _discover_gpu_offers(api_key)
                self._json({"offers": offers})
            except Exception as exc:
                self._json({"error": str(exc)}, 400)
            return

        if parsed.path == "/api/status":
            self._json(_session_status_payload())
            return

        self.send_error(404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)

        if not self._authorized():
            self._json({"error": "Unauthorized local launcher request."}, 403)
            return

        if parsed.path == "/api/credentials":
            try:
                payload = self._read_json()
                runpod_key, hf_token = _credentials_from_payload(payload)

                _validate_runpod_key(runpod_key)
                _validate_hf_token(hf_token)
                _save_credentials(runpod_key, hf_token)

                self._json({
                    "ok": True,
                    "runpod_masked": _mask(runpod_key),
                    "hf_masked": _mask(hf_token),
                    "hf_saved": bool(hf_token),
                    "config_path": str(CONFIG_PATH),
                })
            except Exception as exc:
                self._json({"error": str(exc)}, 400)
            return

        if parsed.path == "/api/forget":
            try:
                CONFIG_PATH.unlink(missing_ok=True)
                self._json({"ok": True})
            except OSError as exc:
                self._json({"error": str(exc)}, 500)
            return

        if parsed.path == "/api/terminate-active":
            try:
                self._json(_terminate_active_session())
            except Exception as exc:
                self._json({"error": str(exc)}, 400)
            return

        if parsed.path != "/api/launch":
            self.send_error(404)
            return

        if STATE["launching"]:
            self._json({"error": "A Pod is already being created."}, 409)
            return

        try:
            payload = self._read_json()
            saved = _read_config()

            runpod_key = str(saved.get("runpod_api_key") or "").strip()
            hf_token = str(saved.get("hf_token") or "").strip()

            if not runpod_key:
                raise ValueError("Runpod API key is missing. Go back to Credentials.")

            gpu = str(payload.get("gpu") or "").strip()
            cloud = str(payload.get("cloud") or "").strip().upper()
            if not gpu or cloud not in {"COMMUNITY", "SECURE"}:
                raise ValueError("Choose an available GPU first.")

            try:
                vram = int(payload.get("vram"))
                price = float(payload.get("price"))
                hours = float(payload.get("hours"))
                disk = int(payload.get("disk"))
            except (TypeError, ValueError) as exc:
                raise ValueError("Session settings are invalid.") from exc

            if not 0.25 <= hours <= 24:
                raise ValueError("Session length must be between 0.25 and 24 hours.")
            if not 100 <= disk <= 1000:
                raise ValueError("Ephemeral disk must be between 100 and 1000 GB.")
            if price < 0:
                raise ValueError("GPU price is invalid.")

            image = str(payload.get("image") or saved.get("image") or DEFAULTS["image"]).strip()

            STATE.update({
                "launching": True,
                "pod_id": "",
                "dashboard_url": "",
                "workspace_url": "",
                "selected_gpu": gpu,
                "selected_cloud": cloud,
                "error": "",
            })

            result = launch_pod(
                api_key=runpod_key,
                image=image,
                gpu=gpu,
                cloud=cloud,
                hours=hours,
                disk=disk,
                hf_token=hf_token,
                rate=price,
            )

            _write_config({
                **saved,
                "image": image,
                "hours": hours,
                "disk": disk,
                "selected_gpu": gpu,
                "selected_cloud": cloud,
                "selected_price": price,
                "selected_vram": vram,
                "active_session": {
                    "pod_id": result["pod_id"],
                    "dashboard_url": result["dashboard_url"],
                    "workspace_url": result["workspace_url"],
                    "selected_gpu": result.get("selected_gpu", gpu),
                    "selected_cloud": result.get("selected_cloud", cloud),
                    "selected_price": price,
                    "selected_vram": vram,
                    "hours": hours,
                },
            })

            STATE.update({
                "launching": False,
                "pod_id": result["pod_id"],
                "dashboard_url": result["dashboard_url"],
                "workspace_url": result["workspace_url"],
                "selected_gpu": result.get("selected_gpu", gpu),
                "selected_cloud": result.get("selected_cloud", cloud),
                "error": "",
            })
            self._json({"ok": True, **STATE})
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
    print("Credentials are saved locally and never written to the repository.")

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
