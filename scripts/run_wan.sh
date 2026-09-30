#!/usr/bin/env bash
set -euo pipefail
: "${UGC_OUTPUT:?}"
: "${UGC_PROMPT:?}"
: "${UGC_START_FRAME:?Wan requires a start frame}"
exec /opt/wan-venv/bin/python /app/scripts/run_wan_diffusers.py
