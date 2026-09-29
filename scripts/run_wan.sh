#!/usr/bin/env bash
set -euo pipefail
: "${UGC_OUTPUT:?}"
: "${UGC_PROMPT:?}"
: "${UGC_START_FRAME:?Wan V1 requires a start frame}"
MODEL_ROOT="${MODEL_ROOT:-/workspace/models}"
CODE_ROOT="${CODE_ROOT:-/opt/ugc-models}"
WAN_REV="${WAN_REV:-1ea34ff48f87168174e12956e200b1d908b1c5ff}"
mkdir -p "$MODEL_ROOT" "$CODE_ROOT"
if [ ! -d "$CODE_ROOT/Wan2.2/.git" ]; then git clone --no-checkout --filter=blob:none https://github.com/Wan-Video/Wan2.2.git "$CODE_ROOT/Wan2.2"; fi
git -C "$CODE_ROOT/Wan2.2" fetch --depth 1 origin "$WAN_REV"
git -C "$CODE_ROOT/Wan2.2" checkout --detach -q "$WAN_REV"
if [ ! -d "$CODE_ROOT/Wan2.2/.venv" ]; then
  uv venv --seed "$CODE_ROOT/Wan2.2/.venv" --python 3.11
  "$CODE_ROOT/Wan2.2/.venv/bin/pip" install --upgrade pip setuptools wheel
  grep -v -E '^flash[_-]attn([<=> ].*)?$' "$CODE_ROOT/Wan2.2/requirements.txt" > "$CODE_ROOT/Wan2.2/.requirements-no-flash.txt"
  "$CODE_ROOT/Wan2.2/.venv/bin/pip" install -r "$CODE_ROOT/Wan2.2/.requirements-no-flash.txt"
  "$CODE_ROOT/Wan2.2/.venv/bin/pip" install flash-attn --no-build-isolation
fi
if [ ! -d "$MODEL_ROOT/Wan2.2-I2V-A14B" ]; then hf download Wan-AI/Wan2.2-I2V-A14B --local-dir "$MODEL_ROOT/Wan2.2-I2V-A14B"; fi
FRAMES=$(( UGC_DURATION * 16 + 1 ))
"$CODE_ROOT/Wan2.2/.venv/bin/python" "$CODE_ROOT/Wan2.2/generate.py"   --task i2v-A14B --size 720*1280 --frame_num "$FRAMES"   --ckpt_dir "$MODEL_ROOT/Wan2.2-I2V-A14B" --offload_model True --convert_model_dtype   --image "$UGC_START_FRAME" --prompt "$UGC_PROMPT" --base_seed "$UGC_SEED" --t5_cpu --save_file "$UGC_OUTPUT"
