#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import secrets
import sys
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import runpod


AUTO_GPU_CANDIDATES = [
    "NVIDIA RTX PRO 6000 Blackwell Server Edition MIG 2g.48gb",
    "NVIDIA L40S",
    "NVIDIA RTX 6000 Ada Generation",
    "NVIDIA RTX PRO 6000 Blackwell Server Edition",
    "NVIDIA H100 PCIe",
]


def _create_single_pod(
    *,
    api_key: str,
    image: str,
    gpu: str,
    cloud: str,
    hours: float,
    disk: int,
    hf_token: str,
    rate: float,
) -> dict[str, Any]:
    runpod.api_key = api_key
    access = secrets.token_urlsafe(18)
    session_name = f"ugc-factory-{secrets.token_hex(4)}"

    env = {
        "RUNPOD_API_KEY": api_key,
        "RUNPOD_SESSION_NAME": session_name,
        "APP_ACCESS_TOKEN": access,
        "HF_TOKEN": hf_token,
        "UGC_RENDERER_MODE": "real",
        "DATA_DIR": "/workspace/ugc-factory-data",
        "SESSION_STARTED_AT": datetime.now(timezone.utc).isoformat(),
        "SESSION_HOURLY_RATE_USD": str(rate),
        "MAX_SESSION_HOURS": str(hours),
    }

    pod = runpod.create_pod(
        name=session_name,
        image_name=image,
        gpu_type_id=gpu,
        cloud_type=cloud,
        gpu_count=1,
        volume_in_gb=0,
        container_disk_in_gb=disk,
        ports="8000/http",
        env=env,
        start_ssh=False,
    )

    pod_id = str(pod["id"])
    dashboard_url = f"https://{pod_id}-8000.proxy.runpod.net"
    workspace_url = f"{dashboard_url}/#token={quote(access, safe='')}"

    return {
        "pod_id": pod_id,
        "session_name": session_name,
        "dashboard_url": dashboard_url,
        "workspace_url": workspace_url,
        "access_token": access,
        "selected_gpu": gpu,
        "selected_cloud": cloud,
    }


def launch_pod(
    *,
    api_key: str,
    image: str,
    gpu: str = "AUTO",
    cloud: str = "ALL",
    hours: float = 5.0,
    disk: int = 180,
    hf_token: str = "",
    rate: float = 0.0,
) -> dict[str, Any]:
    if not api_key:
        raise ValueError("Runpod API key is required.")

    if gpu != "AUTO":
        return _create_single_pod(
            api_key=api_key,
            image=image,
            gpu=gpu,
            cloud=cloud,
            hours=hours,
            disk=disk,
            hf_token=hf_token,
            rate=rate,
        )

    cloud_order = ["COMMUNITY", "SECURE"] if cloud == "ALL" else [cloud]
    errors: list[str] = []

    for candidate in AUTO_GPU_CANDIDATES:
        for candidate_cloud in cloud_order:
            try:
                return _create_single_pod(
                    api_key=api_key,
                    image=image,
                    gpu=candidate,
                    cloud=candidate_cloud,
                    hours=hours,
                    disk=disk,
                    hf_token=hf_token,
                    rate=rate,
                )
            except Exception as exc:
                errors.append(f"{candidate} / {candidate_cloud}: {exc}")

    raise RuntimeError(
        "No supported GPU is currently available on Runpod for this session. "
        "Tried: " + ", ".join(AUTO_GPU_CANDIDATES) + ". "
        "Runpod capacity changes constantly; wait a few minutes and try again."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Advanced CLI launcher for an ephemeral UGC Factory Pod")
    parser.add_argument("--image", default=os.getenv("UGC_FACTORY_IMAGE", "ghcr.io/voekee/ugc-factory:latest"))
    parser.add_argument("--gpu", default="AUTO")
    parser.add_argument("--cloud", choices=["ALL", "SECURE", "COMMUNITY"], default="ALL")
    parser.add_argument("--hours", type=float, default=5.0)
    parser.add_argument("--disk", type=int, default=180)
    parser.add_argument("--hf-token", default=os.getenv("HF_TOKEN", ""))
    parser.add_argument("--rate", type=float, default=0.0)
    args = parser.parse_args()

    api_key = os.getenv("RUNPOD_API_KEY", "")
    if not api_key:
        sys.exit("RUNPOD_API_KEY is not set. Normal users should run: bash start.sh")

    result = launch_pod(
        api_key=api_key,
        image=args.image,
        gpu=args.gpu,
        cloud=args.cloud,
        hours=args.hours,
        disk=args.disk,
        hf_token=args.hf_token,
        rate=args.rate,
    )

    print(f"\nPod: {result['pod_id']}")
    print(f"GPU: {result['selected_gpu']} ({result['selected_cloud']})")
    print(f"Dashboard: {result['dashboard_url']}")
    print(f"Workspace: {result['workspace_url']}")
    print(f"Hard session target: {args.hours:g}h")
    print("After downloading outputs, terminate the Pod from the workspace.")


if __name__ == "__main__":
    main()
