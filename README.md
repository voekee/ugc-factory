# UGC Factory

A clean, ephemeral, multi-user AI UGC render farm for Runpod.

The product goal is deliberately narrow: upload a start frame, optionally an end frame when the selected renderer supports it, choose 4–10 seconds, enter a prompt, queue many variations, render 720p vertical clips, automatically strip ordinary video metadata, download the outputs, then terminate the GPU Pod. No Runpod Network Volume is used.

## What is included

- Clean responsive web dashboard
- Shared session for two or more creators
- Per-job creator/owner labels
- Three selectable local video renderers
- Start/reference frame upload
- Native end-frame support where the upstream model supports it
- 4–10 second selector where supported by the selected renderer
- 720 × 1280 final output
- Batch generation from 1–100 variations
- Shared FIFO queue
- Video gallery and previews
- Download one or download selected as ZIP
- Automatic metadata cleaning with FFmpeg + ExifTool
- Runpod elapsed-time and estimated-cost display
- Safe termination guard for active jobs and undownloaded outputs
- Hard maximum-runtime watchdog
- No Network Volume
- No persistent database
- No persistent Runpod storage after Pod termination
- Renderer-adapter architecture so future models can be added without rebuilding the UI/queue
- Mock renderer and automated tests for development/CI

## Renderers

### LTX-2.5

Default mass-generation engine. The V1 adapter uses the official fast distilled pipeline, supports a real first and last frame, 4–10 second clips, 24 fps generation and optional native audio from the model. The first use in every fresh ephemeral Pod downloads the required LTX model components.

### Wan 2.2 I2V A14B

720p image-to-video alternate with native 720 × 1280 generation. V1 supports 4–10 seconds and does not fake an end-frame control. The official checkpoint is large, roughly 126 GB, so it is intentionally not the default spam engine.

### SkyReels V3 Reference-to-Video

Reference-focused 720p alternate for people/product consistency. V1 uses the official 5-second Reference-to-Video path and a dedicated Python 3.12 environment. End frame is not exposed because the adapter does not fake unsupported control.

The dashboard is capability-aware, so it only shows duration/end-frame controls that the selected renderer really supports.

## Ephemeral cost model

UGC Factory requests **no Runpod Network Volume**.

A session is:

1. Start a fresh GPU Pod.
2. Download the selected model lazily on first use.
3. Render as many queued jobs as desired while the Pod is alive.
4. Download the outputs.
5. Click **Terminate Pod**.
6. The Pod and its local disk disappear.

The launcher uses `volume_in_gb=0`. After Pod termination this project leaves no Runpod Network Volume or Pod-local storage behind. The trade-off is intentional: every fresh session has to download model weights again.

The default ephemeral container disk is 350 GB. Change it with `--disk` if your session will use several large models.

## Two-person workflow

Both people open the same Runpod proxy URL and enter the same temporary session access token. Each browser remembers its creator name locally.

Example:

- Mehmet queues 20 LTX clips.
- Joshua queues 20 SkyReels clips.
- Both batches enter the same queue and remain labeled by owner.
- Both users can preview and download results.
- Termination is blocked while work is active or finished outputs are still marked undownloaded, unless someone explicitly force-terminates.

One Pod in this V1 has one render worker because it represents one GPU. More GPUs can later be added behind the same renderer/queue contract without changing the UI.

## GitHub / container flow

The repository includes two GitHub Actions workflows:

- `CI` runs tests and Python compilation.
- `Build container` publishes `ghcr.io/<OWNER>/ugc-factory:latest` on pushes to `main` that affect the runtime.

For the easiest portable setup, make the GHCR package public after its first successful build. Otherwise configure Runpod with credentials that can pull the private image.

Model weights are **not** bundled into the Docker image. That keeps the image portable and avoids redistributing upstream weights.

## First-time setup

### 1. Clone

```bash
git clone https://github.com/YOUR_USER/ugc-factory.git
cd ugc-factory
```

### 2. Build/publish the image

Push to `main` and let the included GitHub Action publish the GHCR image, or build the Dockerfile yourself.

Set:

```bash
export UGC_FACTORY_IMAGE=ghcr.io/YOUR_USER/ugc-factory:latest
```

### 3. Create your own Runpod API key

Keep it local. Never commit it.

```bash
export RUNPOD_API_KEY='...'
```

### 4. LTX only: accept upstream gated access and create a Hugging Face read token

```bash
export HF_TOKEN='...'
```

The token is passed into the ephemeral Pod only for the session. The LTX runner provides it directly to `hf download`; it is not committed to the repository.

### 5. Launch

```bash
./launcher/start.sh --hours 5 --rate 0.69
```

Defaults:

- GPU: `NVIDIA GeForce RTX 5090`
- Cloud: `COMMUNITY`
- Ephemeral disk: `350 GB`
- Session length watchdog: `5 hours` when `--hours 5` is provided

You can override them:

```bash
./launcher/start.sh \
  --gpu 'NVIDIA GeForce RTX 5090' \
  --cloud COMMUNITY \
  --hours 5 \
  --disk 350 \
  --rate 0.69
```

The launcher prints:

- Pod ID
- Dashboard URL
- random temporary session access token

Share only the dashboard URL and access token with the teammate who should use that render session.

## Ending a session

Use **Terminate Pod**, not merely Stop, when the goal is to leave no Pod-local storage behind.

The UI refuses normal termination while:

- jobs are queued/rendering/cleaning, or
- completed outputs are still marked undownloaded.

Force termination is still available and permanently destroys remaining Pod-local files.

There is also a maximum-runtime watchdog. Its purpose is cost safety: if the configured deadline is reached, it may terminate the Pod even if a user forgot to download something.

## Metadata cleaner

Every generated video is finalized through FFmpeg and, when available, ExifTool.

The finalizer:

- outputs exact 720 × 1280 H.264 MP4
- preserves audio when present
- removes ordinary source/container metadata and chapters
- removes standard ExifTool-visible metadata
- deletes the raw intermediate after a clean output is created

This removes ordinary file metadata. It does not remove visible watermarks, perceptual fingerprints, or information that a social platform itself records after upload.

## Local development

Requirements: Python 3.11+, FFmpeg and ExifTool.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
UGC_RENDERER_MODE=mock uvicorn app.main:app --reload --port 8000
```

Open `http://localhost:8000` and use the `APP_ACCESS_TOKEN` from `.env`.

## Tests

```bash
pytest -q
python -m compileall app launcher tests
bash -n scripts/*.sh launcher/start.sh
node --check static/app.js
```

The automated suite covers renderer capabilities, metadata removal and 720 × 1280 normalization, shared multi-user queueing, preview/download behavior, and safe termination guarding in mock mode.

## Environment variables

See `.env.example`.

Runpod sessions use:

- `RUNPOD_API_KEY`
- `RUNPOD_SESSION_NAME`
- `APP_ACCESS_TOKEN`
- `HF_TOKEN` when needed
- `UGC_RENDERER_MODE=real`
- `DATA_DIR=/workspace/ugc-factory-data`
- `SESSION_STARTED_AT`
- `SESSION_HOURLY_RATE_USD`
- `MAX_SESSION_HOURS`

Optional renderer command overrides:

- `LTX_RUNNER_CMD`
- `WAN_RUNNER_CMD`
- `SKYREELS_RUNNER_CMD`

## Reproducibility

The runner scripts pin upstream code revisions instead of pulling a moving `main` branch at inference time:

- LTX-2 revision `a95ab856bf29407b6b066ede0abe1846050db56c`
- Wan 2.2 revision `1ea34ff48f87168174e12956e200b1d908b1c5ff`
- SkyReels V3 revision `28c771e8456341be6a213e3d1133ed1fd19bf75d`

Model checkpoints still come from the upstream model repositories.

## Model licenses

This repository does not redistribute model weights. Each person using it is responsible for accepting and following each upstream model license and usage terms. Re-check upstream terms before commercial use because model licenses can change independently of this repository.

The project code itself is under the license in `LICENSE`.

## Validation boundary

The app, API, queue, metadata cleaner, UI JavaScript syntax, runner shell syntax, download flow and termination guard can be validated without a GPU and are covered by local/CI checks.

Actual CUDA inference cannot be truthfully certified without running the exact container on a real Runpod GPU with valid upstream model access. The first production session should therefore begin with one short LTX generation before queueing a large batch.
