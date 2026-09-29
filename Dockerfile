FROM runpod/pytorch:1.0.3-cu1281-torch291-ubuntu2404

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    VIRTUAL_ENV=/opt/ugc-venv \
    PATH="/opt/ugc-venv/bin:$PATH" \
    LTX_CODE=/opt/ugc-models/LTX-2 \
    LTX_REV=a95ab856bf29407b6b066ede0abe1846050db56c

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libimage-exiftool-perl git curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN curl -LsSf https://astral.sh/uv/install.sh | sh \
    && ln -s /root/.local/bin/uv /usr/local/bin/uv \
    && uv venv --seed "$VIRTUAL_ENV" --python python3

WORKDIR /app

COPY requirements.txt .
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r requirements.txt \
    && python -m pip install --no-cache-dir "huggingface_hub[cli]"

# Bake the pinned LTX source and its runtime dependencies into the image once.
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

EXPOSE 8000

CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000","--workers","1"]
