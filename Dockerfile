FROM runpod/pytorch:1.0.3-cu1281-torch291-ubuntu2404

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    VIRTUAL_ENV=/opt/ugc-venv \
    PATH="/opt/ugc-venv/bin:$PATH" \
    LTX_CODE=/opt/ugc-models/LTX-2 \
    LTX_REV=a95ab856bf29407b6b066ede0abe1846050db56c \
    SKY_CODE=/opt/ugc-models/SkyReels-V3 \
    SKY_REV=28c771e8456341be6a213e3d1133ed1fd19bf75d

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libimage-exiftool-perl git curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN curl -LsSf https://astral.sh/uv/install.sh | sh \
    && ln -s /root/.local/bin/uv /usr/local/bin/uv \
    && uv venv --seed --system-site-packages "$VIRTUAL_ENV" --python python3

WORKDIR /app

COPY requirements.txt .
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r requirements.txt \
    && python -m pip install --no-cache-dir "huggingface_hub[cli]"

# Bake the pinned LTX source and runtime into the image once. The venv can see
# the base PyTorch installation; pip may still select a newer compatible Torch.
# Verify the resulting stack at build time and never install it on a Pod.
# We intentionally do NOT install the optional NATTEN extra here. The official
# pipeline supports PyTorch SDPA / fallback decoding without NATTEN, and keeping
# the existing Torch 2.9.1 + CUDA 12.8 stack avoids replacing it with another
# CUDA/Torch toolchain on every ephemeral Pod.
RUN mkdir -p /opt/ugc-models \
    && git clone --no-checkout --filter=blob:none https://github.com/Lightricks/LTX-2.git "$LTX_CODE" \
    && git -C "$LTX_CODE" fetch --depth 1 origin "$LTX_REV" \
    && git -C "$LTX_CODE" checkout --detach -q "$LTX_REV" \
    && python -m pip install --no-cache-dir -e "$LTX_CODE/packages/ltx-core" \
    && python -m pip install --no-cache-dir -e "$LTX_CODE/packages/ltx-pipelines" \
    && python - <<'PY'
import torch
import ltx_core
import ltx_pipelines
print("UGC Factory LTX runtime ready")
print("torch", torch.__version__)
print("cuda", torch.version.cuda)
PY

COPY . .

# SkyReels requires Transformers 4.x while LTX uses 5.x. Keep its single-GPU
# reference runtime separate, baked into the image, and reuse the base Torch.
RUN git clone --no-checkout --filter=blob:none https://github.com/SkyworkAI/SkyReels-V3.git "$SKY_CODE" \
    && git -C "$SKY_CODE" fetch --depth 1 origin "$SKY_REV" \
    && git -C "$SKY_CODE" checkout --detach -q "$SKY_REV" \
    && python scripts/prepare_skyreels.py "$SKY_CODE" \
    && uv venv --seed --system-site-packages /opt/sky-venv --python python3 \
    && grep -v -E '^(torch==|torchvision==|flash_attn==|xfuser==|yunchang==|torchao==)' "$SKY_CODE/requirements.txt" > /tmp/sky-requirements.txt \
    && /opt/sky-venv/bin/pip install --no-cache-dir -r /tmp/sky-requirements.txt imageio einops sentencepiece av torchvision==0.24.1 \
    && cd "$SKY_CODE" \
    && /opt/sky-venv/bin/python - <<'PY'
import torch, torchvision
from PIL import Image
from skyreels_v3.pipelines import ReferenceToVideoPipeline
from skyreels_v3.modules.attention import FLASH_ATTN_2_AVAILABLE, FLASH_ATTN_3_AVAILABLE
from skyreels_v3.utils.util import get_height_width_from_image
print("SkyReels reference runtime ready", torch.__version__, torchvision.__version__)
print("flash-attn available", FLASH_ATTN_2_AVAILABLE or FLASH_ATTN_3_AVAILABLE)
print("portrait 720P model dimensions", get_height_width_from_image(Image.new("RGB", (720, 1280)), "720P"))
PY

EXPOSE 8000

CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000","--workers","1"]
