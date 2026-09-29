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


def launch_pod(
    *,
    api_key: str,
    image: str,
    gpu: str = "NVIDIA GeForce RTX 5090",
    cloud: str = "COMMUNITY",
    hours: float = 5.0,
    disk: int = 350,
    hf_token: str = "",
    rate: float = 0.0,
) -> dict[str, Any]:
    if not api_key:
        raise ValueError("Runpod API key is required.")

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
        start_ssh=True,
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
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Advanced CLI launcher for an ephemeral UGC Factory Pod")
    parser.add_argument("--image", default=os.getenv("UGC_FACTORY_IMAGE", "ghcr.io/voekee/ugc-factory:latest"))
    parser.add_argument("--gpu", default="NVIDIA GeForce RTX 5090")
    parser.add_argument("--cloud", choices=["ALL", "SECURE", "COMMUNITY"], default="COMMUNITY")
    parser.add_argument("--hours", type=float, default=5.0)
    parser.add_argument("--disk", type=int, default=350)
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
    print(f"Dashboard: {result['dashboard_url']}")
    print(f"Workspace: {result['workspace_url']}")
    print(f"Hard session target: {args.hours:g}h")
    print("After downloading outputs, terminate the Pod from the workspace.")


if __name__ == "__main__":
    main()
