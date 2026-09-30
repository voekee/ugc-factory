#!/usr/bin/env bash
set -euo pipefail

: "${UGC_OUTPUT:?}"
: "${UGC_PROMPT:?}"
: "${UGC_START_FRAME:?LTX requires a start frame}"

MODEL_ROOT="${MODEL_ROOT:-/workspace/models}"
LTX_CODE="${LTX_CODE:-/opt/ugc-models/LTX-2}"
LTX_MODELS="$MODEL_ROOT/LTX-2.5"

mkdir -p "$MODEL_ROOT"
export PYTORCH_CUDA_ALLOC_CONF="${PYTORCH_CUDA_ALLOC_CONF:-expandable_segments:True}"

echo "[LTX] Runtime baked into container."
python - <<'PY'
import torch
import ltx_core
import ltx_pipelines
print(f"[LTX] torch={torch.__version__} cuda={torch.version.cuda} available={torch.cuda.is_available()}")
if not torch.cuda.is_available():
    raise SystemExit("[LTX] CUDA is not available inside the Pod")
print(f"[LTX] gpu={torch.cuda.get_device_name(0)}")
PY

TRANSFORMER="$LTX_MODELS/diffusion_models/ltx-2.5-22b-distilled-transformer-bf16.safetensors"
TEXT_ENCODER="$LTX_MODELS/text_encoders/gemma4-12b-with-proj-ltx-2.5-bf16.safetensors"
VIDEO_VAE="$LTX_MODELS/vae/ltx-2.5-video-vae-bf16.safetensors"
AUDIO_VAE="$LTX_MODELS/vae/ltx-2.5-audio-vae-bf16.safetensors"
SPATIAL_UPSCALER="$LTX_MODELS/latent_upscale_models/ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors"

NEED_DOWNLOAD=0
for file in "$TRANSFORMER" "$TEXT_ENCODER" "$VIDEO_VAE" "$AUDIO_VAE" "$SPATIAL_UPSCALER"; do
  if [ ! -s "$file" ]; then
    NEED_DOWNLOAD=1
    break
  fi
done

if [ "$NEED_DOWNLOAD" -eq 1 ]; then
  [ -n "${HF_TOKEN:-}" ] || {
    echo "[LTX] HF_TOKEN is required for gated LTX-2.5 weights" >&2
    exit 2
  }

  echo "[LTX] Downloading LTX-2.5 model weights..."
  mkdir -p "$LTX_MODELS"

  hf download Lightricks/LTX-2.5 \
    diffusion_models/ltx-2.5-22b-distilled-transformer-bf16.safetensors \
    text_encoders/gemma4-12b-with-proj-ltx-2.5-bf16.safetensors \
    vae/ltx-2.5-video-vae-bf16.safetensors \
    vae/ltx-2.5-audio-vae-bf16.safetensors \
    latent_upscale_models/ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors \
    --local-dir "$LTX_MODELS" \
    --token "$HF_TOKEN"
fi

FRAMES=$(( UGC_DURATION * 24 + 1 ))

echo "[LTX] Loading model and starting render: ${UGC_DURATION}s, ${FRAMES} frames, 768x1280..."

CMD=(
  python -m ltx_pipelines.distilled
  --transformer-path "$TRANSFORMER"
  --text-encoder-path "$TEXT_ENCODER"
  --video-vae-path "$VIDEO_VAE"
  --audio-vae-path "$AUDIO_VAE"
  --spatial-upsampler-path "$SPATIAL_UPSCALER"
  --width 768
  --height 1280
  --frame-rate 24
  --num-frames "$FRAMES"
  --seed "$UGC_SEED"
  --prompt "$UGC_PROMPT"
  --output-path "$UGC_OUTPUT"
  --quantization fp8-cast
  --offload cpu
  --image "$UGC_START_FRAME" 0 1.0
)

if [ -n "${UGC_END_FRAME:-}" ]; then
  CMD+=(--image "$UGC_END_FRAME" $(( FRAMES - 1 )) 1.0)
fi

"${CMD[@]}"

echo "[LTX] Render complete."
