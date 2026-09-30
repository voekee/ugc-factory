"""Prepare a local H3 deployment without allocating GPUs or downloading weights."""
from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import dotenv_values
from app.config import Settings
from app.h3 import EXCLUDED, ISO_COUNTRIES, PROFILES

DEFAULT_PATH = Path.home() / ".ugc-factory" / "h3.env"
LICENSE_URL = "https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/LICENSE"


def save_config(path: Path, values: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as stream:
        stream.write("# H3 deployment preparation. No GPU is started by this file.\n")
        for key, value in values.items():
            stream.write(f"{key}={json.dumps(value)}\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)
    path.chmod(0o600)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_PATH)
    parser.add_argument("--operator-country")
    parser.add_argument("--deployment-country")
    parser.add_argument("--profile", choices=PROFILES)
    parser.add_argument("--worker-image")
    parser.add_argument("--volume-id")
    parser.add_argument("--datacenter-id")
    parser.add_argument("--accept-community-license", action="store_true",
                        help="Record your actual acceptance of the linked community license")
    args = parser.parse_args()
    values = {k: v for k, v in dotenv_values(args.config).items()
              if k.startswith("H3_") and v is not None} if args.config.exists() else {}
    values = {"H3_ENABLED": "false", "H3_LICENSE_AUTHORIZED": "false",
              "H3_LICENSE_MODE": "disabled", "H3_PROFILE": "h100-4",
              "H3_ALLOWED_REGION": "", "H3_OPERATOR_REGION": "",
              "H3_WORKER_IMAGE": "", "H3_NETWORK_VOLUME_ID": "",
              "H3_DATA_CENTER_ID": "", **values}
    changes = {"H3_OPERATOR_REGION": args.operator_country,
               "H3_ALLOWED_REGION": args.deployment_country,
               "H3_PROFILE": args.profile, "H3_WORKER_IMAGE": args.worker_image,
               "H3_NETWORK_VOLUME_ID": args.volume_id, "H3_DATA_CENTER_ID": args.datacenter_id}
    for key, value in changes.items():
        if value is not None:
            if key.endswith("REGION"):
                value = value.upper()
                if value not in ISO_COUNTRIES:
                    parser.error("Countries must be explicit ISO country codes, for example CN")
            if key == "H3_WORKER_IMAGE" and value and not re.fullmatch(r"[^\s]+@sha256:[a-f0-9]{64}", value):
                parser.error("Use an actual immutable H3 image digest, not a floating tag")
            values[key] = value
    if args.accept_community_license:
        countries = {values["H3_OPERATOR_REGION"], values["H3_ALLOWED_REGION"]}
        if not countries <= ISO_COUNTRIES or countries & EXCLUDED:
            parser.error("Community license acceptance requires eligible operator and deployment countries")
        values.update(H3_LICENSE_AUTHORIZED="true", H3_LICENSE_MODE="community")
    if any(v is not None for v in changes.values()) or args.accept_community_license:
        # Preparation never enables execution. Connecting/testing hardware is a separate step.
        values["H3_ENABLED"] = "false"
        Settings(_env_file=None, **{key.lower(): value for key, value in values.items()})
        save_config(args.config, values)
    if values["H3_PROFILE"] not in PROFILES:
        parser.error("Saved H3 hardware profile is invalid")
    profile = PROFILES[values["H3_PROFILE"]]
    pending = []
    if values["H3_LICENSE_AUTHORIZED"].lower() != "true":
        pending.append("Actual license acceptance has not been recorded")
    for key, label in (("H3_WORKER_IMAGE", "Prepared worker image"),
                       ("H3_NETWORK_VOLUME_ID", "Staged FL2VA weight volume"),
                       ("H3_DATA_CENTER_ID", "Verified GPU deployment location")):
        if not values[key]:
            pending.append(label)
    pending.append("Real GPU startup and Start + End Frame smoke test")
    print(json.dumps({"config": str(args.config), "operator_country": values["H3_OPERATOR_REGION"],
                     "requested_deployment_country": values["H3_ALLOWED_REGION"],
                     "execution_enabled": False, "profile": values["H3_PROFILE"],
                     "gpu_count": profile["count"], "gpu": profile["gpu"],
                     "host_ram_gb": profile["host_ram_gb"], "pending": pending,
                     "license": LICENSE_URL}, indent=2))


if __name__ == "__main__":
    main()
