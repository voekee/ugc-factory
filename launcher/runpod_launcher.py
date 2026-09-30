#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import secrets
import sys
from datetime import datetime, timezone
from typing import Any, Callable
from pathlib import Path
from urllib.parse import quote

import runpod

# Filled only after the reference runtime builds successfully; never a floating tag.
SKYREELS_IMAGE = "ghcr.io/voekee/ugc-factory@sha256:705a3fbc52304cec52eabc6535141b2be4f61333342da2f26d038097abbde82d"

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


AUTO_GPU_CANDIDATES = [
    "NVIDIA GeForce RTX 5090",
    "NVIDIA RTX 6000 Ada Generation",
    "NVIDIA L40S",
    "NVIDIA RTX A6000",
    "NVIDIA A40",
    "NVIDIA A100 80GB PCIe",
    "NVIDIA GeForce RTX 4090",
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
    model: str = "legacy",
    on_creating: Callable | None = None,
) -> dict[str, Any]:
    extra = {}
    h3_env = {}
    gpu_count = 1
    if model == "h3-fl2va":
        from app.h3 import deployment_reason, PROFILES
        from app.config import settings
        if reason := deployment_reason():
            raise ValueError(reason)
        image = settings.h3_worker_image
        profile = PROFILES[settings.h3_profile]
        gpu, gpu_count, cloud = profile["gpu"], profile["count"], "SECURE"
        extra = {"network_volume_id": settings.h3_network_volume_id,
                 "data_center_id": settings.h3_data_center_id,
                 "country_code": settings.h3_allowed_region.upper(), "min_memory_in_gb": profile["host_ram_gb"]}
        h3_env = {name.upper(): str(getattr(settings, name)) for name in (
            "h3_enabled", "h3_license_authorized", "h3_allowed_region", "h3_operator_region",
            "h3_license_mode", "h3_authorization_reference", "h3_profile")}
    elif model == "skyreelsv3":
        if not SKYREELS_IMAGE or image != SKYREELS_IMAGE:
            raise ValueError("SkyReels needs its prepared, pinned worker image before GPU allocation")
    elif model not in {"legacy", "wan22"}:
        raise ValueError("Unknown session model")
    if model in {"legacy", "wan22", "skyreelsv3"}:
        from lifecycle_test import enabled
        if not enabled():
            extra.update({"min_memory_in_gb": 160 if model == "wan22" else 128, "min_vcpu_count": 8})
    runpod.api_key = api_key
    access = secrets.token_urlsafe(18)
    session_name = f"ugc-factory-{secrets.token_hex(4)}"

    env = {
        "RUNPOD_API_KEY": api_key,
        "RUNPOD_SESSION_NAME": session_name,
        "RUNPOD_GPU_COUNT": str(gpu_count),
        "UGC_GPU_TYPE": gpu,
        "APP_ACCESS_TOKEN": access,
        "HF_TOKEN": hf_token,
        "UGC_RENDERER_MODE": "real",
        "SESSION_MODEL": model,
        "DATA_DIR": "/workspace/ugc-factory-data",
        "SESSION_STARTED_AT": datetime.now(timezone.utc).isoformat(),
        "SESSION_HOURLY_RATE_USD": str(rate),
        "MAX_SESSION_HOURS": str(hours),
        "EXTERNAL_GUARDIAN": str(on_creating is not None),
        **h3_env,
    }

    if on_creating:
        # Journal the exact remote name before sending a non-idempotent allocation request.
        on_creating({"session_name": session_name, "started_at": env["SESSION_STARTED_AT"],
                     "hours": hours, "model": model, "session_token": access,
                     "selected_gpu": gpu, "selected_cloud": cloud})
    from lifecycle_test import enabled, pod_options
    if enabled() and model == "legacy":
        extra_test, env_test = pod_options()
        extra.update(extra_test)
        env.update(env_test)
        image, disk = "python:3.11-slim-bookworm", 10
        env["MAX_SESSION_HOURS"] = str(min(hours, 0.25))
    pod = runpod.create_pod(
        name=session_name,
        image_name=image,
        gpu_type_id=gpu,
        cloud_type=cloud,
        gpu_count=gpu_count,
        volume_in_gb=0,
        container_disk_in_gb=disk,
        ports="8000/http",
        env=env,
        start_ssh=False,
        **extra,
    )

    pod_id = str(pod["id"])
    dashboard_url = f"https://{pod_id}-8000.proxy.runpod.net"
    workspace_url = f"{dashboard_url}/?session_token={quote(access, safe='')}"

    return {
        "pod_id": pod_id,
        "session_name": session_name,
        "dashboard_url": dashboard_url,
        "workspace_url": workspace_url,
        "access_token": access,
        "selected_gpu": gpu,
        "selected_cloud": cloud,
        "gpu_count": gpu_count,
        "model": model,
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
    model: str = "legacy",
    on_creating: Callable | None = None,
) -> dict[str, Any]:
    if not api_key:
        raise ValueError("Runpod API key is required.")

    if gpu != "AUTO" or model == "h3-fl2va":
        return _create_single_pod(
            api_key=api_key,
            image=image,
            gpu=gpu,
            cloud=cloud,
            hours=hours,
            disk=disk,
            hf_token=hf_token,
            rate=rate, model=model, on_creating=on_creating,
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
                    rate=rate, model=model, on_creating=on_creating,
                )
            except Exception as exc:
                # Unknown/network errors can mean allocation succeeded but the reply was lost.
                # Never create a second paid Pod in that case.
                message = str(exc).lower()
                if not any(term in message for term in ("no instances", "no available", "not enough resources", "insufficient capacity")):
                    raise
                errors.append(f"{candidate} / {candidate_cloud}: capacity unavailable")

    raise RuntimeError(
        "No supported GPU is currently available on Runpod for this session. "
        "Tried: " + ", ".join(AUTO_GPU_CANDIDATES) + ". "
        "Runpod capacity changes constantly; wait a few minutes and try again."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Advanced CLI launcher for an ephemeral UGC Factory Pod")
    parser.add_argument("--image", default=os.getenv("UGC_FACTORY_IMAGE", "ghcr.io/voekee/ugc-factory@sha256:705a3fbc52304cec52eabc6535141b2be4f61333342da2f26d038097abbde82d"))
    parser.add_argument("--model", choices=["legacy", "wan22", "skyreelsv3", "h3-fl2va"], default="legacy")
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
        rate=args.rate, model=args.model,
    )

    print(f"\nPod: {result['pod_id']}")
    print(f"GPU: {result['selected_gpu']} ({result['selected_cloud']})")
    print(f"Dashboard: {result['dashboard_url']}")
    print(f"Workspace: {result['workspace_url']}")
    print(f"Hard session target: {args.hours:g}h")
    print("After downloading outputs, terminate the Pod from the workspace.")


if __name__ == "__main__":
    main()
