# UGC Factory

A local-first studio for making short vertical videos on a temporary Runpod GPU. Start a session, create clips with open video models, download the results, and terminate the Pod. There is no Network Volume or permanent cloud library.

## Start

You need a Runpod account with GPU credit, a Runpod API key, and a Hugging Face token with access to [Lightricks/LTX-2.5](https://huggingface.co/Lightricks/LTX-2.5). Accept that model's terms on Hugging Face before starting. On first launch, the script installs its small local Python runtime; macOS and Linux need Bash, curl, and a browser.

```bash
git clone https://github.com/voekee/ugc-factory.git
cd ugc-factory
bash start.sh
```

The launcher opens on `127.0.0.1`. Paste both keys once. They are stored in `~/.ugc-factory/config.json` with owner-only permissions, outside the repository. You can remove them with **Forget saved keys** after ending the active session. The launcher verifies Runpod access, Hugging Face token validity, and access to the gated LTX checkpoint before renting a GPU.

Choose a live GPU offer. The launcher shows only compatible NVIDIA GPUs with at least 48 GB of VRAM, displays the current price and stock, and marks the best value. The default is 48 GB. Choose 1, 3, or 5 hours and review the maximum estimated compute **plus container disk** cost. No Network Volume is requested. The default container disk is 180 GB and exists only with the Pod.

Click **Start session** once. The launcher waits for the workspace health check and opens the authenticated studio. Keep the launcher tab available: it reconnects to the active session after a refresh and can terminate the Pod. **Closing a tab does not stop GPU billing.**

## Create and download

1. Enter a creator name.
2. Choose LTX-2.5 for start-frame or start-and-end-frame video, or SkyReels V3 for a reference-driven shot.
3. Drop an image or use **Choose image**, write a motion prompt, choose duration and variations, then generate.
4. Watch one **Rendering** job and the numbered **Queued** jobs. Queued jobs can be cancelled. Open **Live log** for technical progress.
5. Play completed clips in the library, download one MP4 or select several for a ZIP, then end the session.

The Pod processes one GPU-heavy job at a time. Completed files remain available only while that Pod exists. The first render for each model downloads weights into ephemeral storage; later renders in the same session reuse those files. A new Pod downloads them again.

| Model | Input | Duration | Status |
|---|---|---:|---|
| LTX-2.5 distilled two-stage | Start frame; optional end frame | 4–10 s | Real 4 s renders verified on a 48 GB Blackwell MIG GPU |
| SkyReels V3 Reference-to-Video | Reference image | 5 s | Official reference path; GPU retest pending after baked-runtime fix |
| Wan 2.2 I2V A14B | Start frame | — | Disabled: the official recipe calls for at least 80 GB VRAM |

Wan is intentionally absent from the production model picker. [Wan's official instructions](https://github.com/Wan-Video/Wan2.2) place I2V A14B at 80 GB or more, above this studio's normal 48 GB target. SkyReels uses the [official V3 reference model](https://github.com/SkyworkAI/SkyReels-V3) and accepts one reference image in this UI; that image is **not** a guaranteed first frame. Its end-frame control is not exposed because the reference model does not support it.

Outputs are normalized to 720×1280 H.264/yuv420p MP4 at 24 fps with faststart and ordinary metadata removed. `ffprobe` checks duration, video stream, dimensions and format before a result is marked Ready; a full decode catches damaged frames. A short first use may spend several minutes downloading model weights and loading them before inference begins.

## End the session and billing

Download everything you need, then use **End session** in the studio or **Terminate Pod** in the launcher. Normal termination warns about queued work and undownloaded outputs. The launcher confirms that Runpod no longer lists the Pod before reporting billing stopped. Container disk and all model files disappear with termination. There is no Network Volume and no recurring storage from this setup after termination.

If the workspace tab is closed, reopen `bash start.sh` and the local launcher reconnects to the saved active session. A **Copy session token** fallback is available for sharing a workspace with a trusted collaborator. Teammates need the workspace link and session token, not the Runpod or Hugging Face keys. On a second computer, clone the repo, run `bash start.sh`, and enter that computer's own credentials; local configuration is deliberately not synchronized.

## Costs

The launcher reads live Runpod GPU offers. Its maximum-spend estimate is the selected GPU's hourly rate plus container disk at Runpod's [published $0.10/GB/month rate](https://www.runpod.io/pricing), prorated over 730 hours, multiplied by the chosen session length. Actual billing is determined by Runpod and stops only when the Pod is terminated. GPU availability and prices change; refresh the offer list before starting.

## Troubleshooting

- **No GPUs shown:** raise the price filter or refresh. GPUs below 48 GB and older FP8-incompatible families are excluded for the current models.
- **Hugging Face access denied:** accept the LTX-2.5 model terms and use a token allowed to read gated repositories. The launcher checks this before Pod creation.
- **Container does not start:** check the Pod/system log in the Runpod console and confirm `ghcr.io/voekee/ugc-factory:latest` is public. The launcher waits for the actual workspace health check, not merely container telemetry.
- **First render is slow:** model weights are downloaded on first use of each Pod. The queue log distinguishes download, loading, inference, and finalization where the renderer reports them.
- **Failed render:** open the job's error and live log. Corrupt or truncated output is rejected before entering the library.
- **Browser closed while Pod runs:** restart the launcher, reconnect, download results, and terminate. Runpod's Pods page is the final authority if the local network cannot verify termination.

## Local development

The local mock renderer exercises the queue and MP4 pipeline without renting a GPU. Install FFmpeg and ExifTool, then:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
APP_ACCESS_TOKEN=dev UGC_RENDERER_MODE=mock DATA_DIR=/tmp/ugc-factory-data \
  .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/#token=dev`. The mock produces test MP4s and is never used by the Runpod launcher. To run checks:

```bash
.venv/bin/pytest -q
python3 -m compileall app launcher
bash -n start.sh launcher/start.sh scripts/*.sh
node --check static/app.js
```

The container pins LTX-2 source to `a95ab856bf29407b6b066ede0abe1846050db56c` and SkyReels V3 to `28c771e8456341be6a213e3d1133ed1fd19bf75d`. Runtimes are baked into the image; model weights are downloaded during the temporary session. Secrets never belong in Git, `.env` is ignored, and the browser token is removed from the URL after the studio receives it. Only share a session token with someone who should control that session.
