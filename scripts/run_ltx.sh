#!/usr/bin/env bash
set -euo pipefail

: "${UGC_OUTPUT:?}"
: "${UGC_PROMPT:?}"
: "${UGC_START_FRAME:?LTX requires a start frame}"

MODEL_ROOT="${MODEL_ROOT:-/workspace/models}"
CODE_ROOT="${CODE_ROOT:-/opt/ugc-models}"
LTX_CODE="$CODE_ROOT/LTX-2"
LTX_MODELS="$MODEL_ROOT/LTX-2.5"
LTX_REV="${LTX_REV:-a95ab856bf29407b6b066ede0abe1846050db56c}"

mkdir -p "$MODEL_ROOT" "$CODE_ROOT"
export PYTORCH_CUDA_ALLOC_CONF="${PYTORCH_CUDA_ALLOC_CONF:-expandable_segments:True}"

echo "[LTX] Preparing pinned LTX-2.5 runtime..."

if [ ! -d "$LTX_CODE/.git" ]; then
  rm -rf "$LTX_CODE"
  git clone --no-checkout --filter=blob:none https://github.com/Lightricks/LTX-2.git "$LTX_CODE"
fi

git -C "$LTX_CODE" fetch --depth 1 origin "$LTX_REV"
git -C "$LTX_CODE" checkout --detach -q "$LTX_REV"

# The UGC Factory container has its own VIRTUAL_ENV. LTX must use its own project
# environment, otherwise uv sees /opt/ugc-venv and can target the wrong environment.
if [ ! -f "$LTX_CODE/.ugc_env_ready" ]; then
  echo "[LTX] Installing LTX dependencies..."
  (
    unset VIRTUAL_ENV
    cd "$LTX_CODE"
    uv sync --extra natten
  )
  touch "$LTX_CODE/.ugc_env_ready"
fi

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

  echo "[LTX] Downloading required LTX-2.5 weights..."
  mkdir -p "$LTX_MODELS"

  hf download Lightricks/LTX-2.5     diffusion_models/ltx-2.5-22b-distilled-transformer-bf16.safetensors     text_encoders/gemma4-12b-with-proj-ltx-2.5-bf16.safetensors     vae/ltx-2.5-video-vae-bf16.safetensors     vae/ltx-2.5-audio-vae-bf16.safetensors     latent_upscale_models/ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors     --local-dir "$LTX_MODELS"     --token "$HF_TOKEN"
fi

FRAMES=$(( UGC_DURATION * 24 + 1 ))

echo "[LTX] Starting render: ${UGC_DURATION}s, ${FRAMES} frames, 736x1280..."

CMD=(
  env -u VIRTUAL_ENV
  uv run --project "$LTX_CODE"
  python -m ltx_pipelines.distilled
  --transformer-path "$TRANSFORMER"
  --text-encoder-path "$TEXT_ENCODER"
  --video-vae-path "$VIDEO_VAE"
  --audio-vae-path "$AUDIO_VAE"
  --spatial-upsampler-path "$SPATIAL_UPSCALER"
  --width 736
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
