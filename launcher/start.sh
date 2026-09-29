#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
: "${UGC_FACTORY_IMAGE:?Set UGC_FACTORY_IMAGE, e.g. ghcr.io/voekee/ugc-factory:latest}"
: "${RUNPOD_API_KEY:?Set RUNPOD_API_KEY in your shell}"
VENV="${UGC_LAUNCHER_VENV:-$ROOT/.venv-launcher}"
if [ ! -x "$VENV/bin/python" ]; then
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install -r "$ROOT/launcher/requirements.txt"
fi
exec "$VENV/bin/python" "$ROOT/launcher/runpod_launcher.py" --image "$UGC_FACTORY_IMAGE" "$@"
