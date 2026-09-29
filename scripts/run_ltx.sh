#!/usr/bin/env bash
set -euo pipefail
: "${UGC_OUTPUT:?}"
: "${UGC_PROMPT:?}"
: "${UGC_START_FRAME:?LTX V1 requires a start frame}"

APP_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODEL_ROOT="${MODEL_ROOT:-/workspace/models}"
CODE_ROOT="${CODE_ROOT:-/opt/ugc-models}"
LTX_CODE="$CODE_ROOT/LTX-2"
LTX_MODELS="$MODEL_ROOT/LTX-2.5"
LTX_REV="${LTX_REV:-a95ab856bf29407b6b066ede0abe1846050db56c}"
mkdir -p "$MODEL_ROOT" "$CODE_ROOT"
export PYTORCH_CUDA_ALLOC_CONF="${PYTORCH_CUDA_ALLOC_CONF:-expandable_segments:True}"

if [ ! -d "$LTX_CODE/.git" ]; then
  git clone --no-checkout --filter=blob:none https://github.com/Lightricks/LTX-2.git "$LTX_CODE"
fi
git -C "$LTX_CODE" fetch --depth 1 origin "$LTX_REV"
git -C "$LTX_CODE" checkout --detach -q "$LTX_REV"
if [ ! -d "$LTX_CODE/.venv" ]; then
  cd "$LTX_CODE"
  uv sync --frozen --extra natten
fi
if [ ! -d "$LTX_MODELS/diffusion_models" ]; then
  [ -n "${HF_TOKEN:-}" ] || { echo "HF_TOKEN is required for gated LTX-2.5 weights" >&2; exit 2; }
  hf download Lightricks/LTX-2.5     diffusion_models/ltx-2.5-22b-distilled-transformer-bf16.safetensors     text_encoders/gemma4-12b-with-proj-ltx-2.5-bf16.safetensors     vae/ltx-2.5-video-vae-bf16.safetensors     vae/ltx-2.5-audio-vae-bf16.safetensors     latent_upscale_models/ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors     --local-dir "$LTX_MODELS" --token "$HF_TOKEN"
fi

FRAMES=$(( UGC_DURATION * 24 + 1 ))
CMD=(uv run --project "$LTX_CODE" python -m ltx_pipelines.distilled
  --transformer-path "$LTX_MODELS/diffusion_models/ltx-2.5-22b-distilled-transformer-bf16.safetensors"
  --text-encoder-path "$LTX_MODELS/text_encoders/gemma4-12b-with-proj-ltx-2.5-bf16.safetensors"
  --video-vae-path "$LTX_MODELS/vae/ltx-2.5-video-vae-bf16.safetensors"
  --audio-vae-path "$LTX_MODELS/vae/ltx-2.5-audio-vae-bf16.safetensors"
  --spatial-upsampler-path "$LTX_MODELS/latent_upscale_models/ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors"
  --width 736 --height 1280 --frame-rate 24 --num-frames "$FRAMES"
  --seed "$UGC_SEED" --prompt "$UGC_PROMPT" --output-path "$UGC_OUTPUT"
  --quantization fp8-cast --offload cpu
  --image "$UGC_START_FRAME" 0 1.0)
if [ -n "${UGC_END_FRAME:-}" ]; then
  CMD+=(--image "$UGC_END_FRAME" $(( FRAMES - 1 )) 1.0)
fi
"${CMD[@]}"
