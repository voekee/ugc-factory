#!/usr/bin/env bash
set -euo pipefail
# Dependencies and pinned source are baked into the image, never installed on a paid Pod.
[ -f /opt/skyreels-runtime.json ] && [ -x /opt/skyreels-venv/bin/python ] || {
  echo 'SkyReels runtime is not prepared. Update the worker image before starting a GPU.' >&2
  exit 2
}
export PYTHONPATH="/opt/ugc-models/SkyReels-Reference${PYTHONPATH:+:$PYTHONPATH}"
exec /opt/skyreels-venv/bin/python /app/scripts/run_skyreels_resident.py "$@"
