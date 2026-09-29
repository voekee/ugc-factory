#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${UGC_LAUNCHER_VENV:-$ROOT/.venv-launcher}"

if ! command -v python3 >/dev/null 2>&1; then
  echo "UGC Factory needs Python 3.11+ on this computer."
  echo "Install Python, then run: bash launcher/start.sh"
  exit 1
fi

if [ ! -x "$VENV/bin/python" ]; then
  echo "Preparing the local UGC Factory launcher…"
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install --quiet --upgrade pip
  "$VENV/bin/pip" install --quiet -r "$ROOT/launcher/requirements.txt"
fi

exec "$VENV/bin/python" "$ROOT/launcher/onboarding.py" "$@"
