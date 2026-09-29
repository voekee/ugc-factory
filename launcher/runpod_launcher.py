#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import secrets
import sys
from datetime import datetime, timezone

import runpod


def main() -> None:
    ap=argparse.ArgumentParser(description="Launch an ephemeral UGC Factory Runpod Pod")
    ap.add_argument("--image", required=True, help="Public Docker image, e.g. ghcr.io/OWNER/ugc-factory:latest")
    ap.add_argument("--gpu", default="NVIDIA GeForce RTX 5090")
    ap.add_argument("--cloud", choices=["ALL","SECURE","COMMUNITY"], default="COMMUNITY")
    ap.add_argument("--hours", type=float, default=5.0)
    ap.add_argument("--disk", type=int, default=350, help="Ephemeral container disk GB; no network volume")
    ap.add_argument("--hf-token", default=os.getenv("HF_TOKEN",""))
    ap.add_argument("--rate", type=float, default=0.0, help="Optional hourly rate for dashboard estimate")
    args=ap.parse_args()

    api_key=os.getenv("RUNPOD_API_KEY")
    if not api_key:
        sys.exit("RUNPOD_API_KEY is not set")
    runpod.api_key=api_key
    access=secrets.token_urlsafe(18)
    session_name=f"ugc-factory-{secrets.token_hex(4)}"
    env={
        "RUNPOD_API_KEY":api_key,
        "RUNPOD_SESSION_NAME":session_name,
        "APP_ACCESS_TOKEN":access,
        "HF_TOKEN":args.hf_token,
        "UGC_RENDERER_MODE":"real",
        "DATA_DIR":"/workspace/ugc-factory-data",
        "SESSION_STARTED_AT":datetime.now(timezone.utc).isoformat(),
        "SESSION_HOURLY_RATE_USD":str(args.rate),
        "MAX_SESSION_HOURS":str(args.hours),
    }
    print("Creating ephemeral Runpod Pod. No persistent/network volume is requested...")
    pod=runpod.create_pod(
        name=session_name, image_name=args.image, gpu_type_id=args.gpu, cloud_type=args.cloud,
        gpu_count=1, volume_in_gb=0, container_disk_in_gb=args.disk, ports="8000/http",
        env=env, start_ssh=True,
    )
    pod_id=str(pod["id"])
    print(f"\nPod: {pod_id}")
    print(f"Dashboard: https://{pod_id}-8000.proxy.runpod.net")
    print(f"Session access token: {access}")
    print(f"Hard session target: {args.hours:g}h. The app watchdog will terminate the Pod at that limit.")
    print("After downloading all outputs, use the red Terminate Pod button. Termination deletes the ephemeral disk.")

if __name__=="__main__": main()
