#!/usr/bin/env bash
set -euo pipefail
exec /opt/wan-venv/bin/python /app/scripts/run_wan_diffusers.py "$@"
