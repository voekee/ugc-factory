#!/usr/bin/env bash
set -euo pipefail

: "${UGC_OUTPUT:?}"
: "${UGC_PROMPT:?}"
: "${UGC_START_FRAME:?SkyReels V3 requires a reference image}"
[ "${UGC_DURATION}" = "5" ] || { echo "SkyReels reference generation supports 5 seconds" >&2; exit 2; }

SKY_CODE="${SKY_CODE:-/opt/ugc-models/SkyReels-V3}"
SKY_PYTHON="${SKY_PYTHON:-/opt/sky-venv/bin/python}"
MODEL_ID="Skywork/SkyReels-V3-R2V-14B"

echo "[SkyReels] Checking CUDA runtime..."
"$SKY_PYTHON" - <<'PY'
import torch
print(f"[SkyReels] torch={torch.__version__} cuda={torch.version.cuda} available={torch.cuda.is_available()}")
if not torch.cuda.is_available():
    raise SystemExit("SkyReels needs a CUDA GPU")
print(f"[SkyReels] gpu={torch.cuda.get_device_name(0)}")
PY

mkdir -p /workspace/models/skyreels
export HF_HOME=/workspace/models/skyreels
export PYTORCH_CUDA_ALLOC_CONF="${PYTORCH_CUDA_ALLOC_CONF:-expandable_segments:True}"
export PYTHONUNBUFFERED=1

TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT
MARKER="$TMPDIR/before"
touch "$MARKER"

echo "[SkyReels] Downloading or loading reference model weights..."
cd "$SKY_CODE"
"$SKY_PYTHON" generate_video.py \
  --task_type reference_to_video \
  --model_id "$MODEL_ID" \
  --ref_imgs "$UGC_START_FRAME" \
  --prompt "$UGC_PROMPT" \
  --duration 5 \
  --resolution 720P \
  --offload \
  --seed "$UGC_SEED"

FOUND="$(find "$SKY_CODE/result/reference_to_video" -type f -name "${UGC_SEED}_*.mp4" -newer "$MARKER" -print 2>/dev/null | sort | tail -n 1)"
[ -n "$FOUND" ] || { echo "[SkyReels] Renderer produced no MP4" >&2; exit 3; }
mv "$FOUND" "$UGC_OUTPUT"
echo "[SkyReels] Render complete."
