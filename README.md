<p align="center">
  <img src="assets/ugc-factory-hero.svg" alt="UGC Factory — ephemeral local AI video render farm" width="100%">
</p>

<p align="center">
  <strong>Private AI video generation without per-clip credits.</strong><br>
  Spin up a GPU, generate batches of vertical UGC, download the winners, terminate the machine.
</p>

<p align="center">
  <a href="https://github.com/voekee/ugc-factory/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/voekee/ugc-factory/ci.yml?branch=main&style=for-the-badge&label=CI" alt="CI"></a>
  <a href="https://github.com/voekee/ugc-factory/actions/workflows/ghcr.yml"><img src="https://img.shields.io/github/actions/workflow/status/voekee/ugc-factory/ghcr.yml?branch=main&style=for-the-badge&label=CONTAINER" alt="Container build"></a>
  <img src="https://img.shields.io/badge/output-720×1280-111827?style=for-the-badge" alt="720x1280">
  <img src="https://img.shields.io/badge/storage-ephemeral-111827?style=for-the-badge" alt="Ephemeral storage">
  <img src="https://img.shields.io/badge/license-MIT-111827?style=for-the-badge" alt="MIT">
</p>

---

## UGC Factory in one sentence

**Upload a start frame, choose a local video model, queue as many variations as you want, get clean 720×1280 MP4s, then destroy the GPU Pod so nothing keeps billing in the background.**

UGC Factory is deliberately **not** a giant AI SaaS. It is a focused internal render machine for high-volume short-form creative testing.

### What V1 gives you

| | Capability |
|---|---|
| 🎬 | **Three local video engines:** LTX-2.5, Wan 2.2, SkyReels V3 |
| 🖼️ | Start/reference frame upload |
| 🎞️ | Native end-frame control on LTX-2.5 |
| ⏱️ | 4–10 second generations where supported |
| 📱 | Finalized **720 × 1280 · 9:16** output |
| ⚡ | 1–100 variations in one batch |
| 👥 | Shared queue for two or more creators |
| 🧹 | Automatic ordinary MP4 metadata removal |
| 📦 | Single MP4 download or ZIP export |
| 💸 | Session timer + optional cost estimate |
| 🛡️ | Termination guard for active and undownloaded jobs |
| ☠️ | Hard runtime watchdog |
| 🧱 | **No Runpod Network Volume** |
| 🧩 | Renderer-adapter architecture for future models |

> [!IMPORTANT]
> **The entire cost model is ephemeral.** The launcher requests no Runpod Network Volume. Once you **Terminate** the Pod, the Pod and its local disk are destroyed. That means there is no UGC Factory GPU or Pod-local storage left running between sessions. The trade-off is that model weights must be downloaded again on a fresh session.

---

## How a session works

<p align="center">
  <img src="assets/session-architecture.svg" alt="UGC Factory session architecture" width="100%">
</p>

~~~text
Your Mac / laptop
      │
      │  RUNPOD_API_KEY
      ▼
launcher/start.sh
      │
      ├── creates fresh GPU Pod
      ├── volume_in_gb = 0
      ├── ephemeral container disk = 350 GB
      ├── exposes dashboard on port 8000
      └── generates a temporary session access token
                │
                ▼
        UGC Factory Dashboard
                │
      ┌─────────┼──────────┐
      ▼         ▼          ▼
   LTX-2.5   Wan 2.2   SkyReels V3
      │         │          │
      └─────────┼──────────┘
                ▼
           Shared Queue
                ▼
      Raw model generation
                ▼
       FFmpeg + ExifTool
                ▼
          720×1280 MP4
                ▼
       Download / ZIP export
                ▼
          TERMINATE POD
                ▼
       local Pod data deleted
~~~

---

# Quick Start

This is the shortest safe route from a fresh clone to your first real GPU render.

## 0. What you need

Have these ready:

- A **GitHub account**
- A **Runpod account with billing/credits enabled**
- A **Runpod API key**
- **Python 3.11+** on your Mac or Linux machine
- Git
- For **LTX-2.5 only:** a Hugging Face account with model access and a read token
- A pullable UGC Factory GHCR image

Useful official pages:

- Runpod docs: https://docs.runpod.io/
- Hugging Face tokens: https://huggingface.co/settings/tokens
- Hugging Face gated-model access: https://huggingface.co/docs/hub/models-gated

---

## 1. Clone the repository

~~~bash
git clone https://github.com/voekee/ugc-factory.git
cd ugc-factory
~~~

You should now be inside:

~~~text
ugc-factory/
├── app/                 # backend, queue, metadata, termination
├── assets/              # README artwork
├── launcher/            # creates the ephemeral Runpod Pod
├── scripts/             # model-specific renderer adapters
├── static/              # web dashboard
├── tests/               # mock E2E + metadata tests
├── Dockerfile
└── README.md
~~~

---

## 2. Make sure the container image exists

Every push to <code>main</code> that changes the runtime triggers:

<code>.github/workflows/ghcr.yml</code>

and publishes:

<code>ghcr.io/voekee/ugc-factory:latest</code>

Check:

**GitHub → Actions → Build container**

Once that workflow is green, the package should exist under the repository/account packages.

### If Runpod cannot pull the image

The easiest setup is to make the GHCR package public.

If you intentionally keep GHCR private, Runpod needs registry credentials capable of pulling it.

**Never put a GitHub token in this repository.**

---

## 3. Create a Runpod API key

Create a Runpod API key in your own Runpod account.

Then export it **only in your local terminal**:

~~~bash
export RUNPOD_API_KEY='YOUR_RUNPOD_API_KEY'
~~~

Never:

- paste it into GitHub
- commit it into <code>.env</code>
- send it to your teammate
- put it into screenshots

The launcher passes it into the temporary Pod because the dashboard needs permission to terminate its own Runpod session.

---

## 4. Tell the launcher which image to use

~~~bash
export UGC_FACTORY_IMAGE='ghcr.io/voekee/ugc-factory:latest'
~~~

Confirm:

~~~bash
echo "$UGC_FACTORY_IMAGE"
~~~

Expected:

~~~text
ghcr.io/voekee/ugc-factory:latest
~~~

---

## 5. Enable LTX-2.5

LTX-2.5 is the recommended engine for the first test.

Because the upstream model is gated, first complete the access/terms flow on the LTX-2.5 Hugging Face model page using your own account.

Then create a **read** or appropriately scoped token:

https://huggingface.co/settings/tokens

Export it before launching the Pod:

~~~bash
export HF_TOKEN='hf_...'
~~~

> [!NOTE]
> <code>HF_TOKEN</code> is primarily needed by the gated LTX adapter. Wan and SkyReels do not use the same LTX gated-access flow.

---

## 6. Launch a 5-hour ephemeral render session

From the repository root:

~~~bash
bash launcher/start.sh --hours 5 --rate 0.99
~~~

### What these settings mean

| Setting | Meaning |
|---|---|
| <code>--hours 5</code> | hard session watchdog target of 5 hours |
| <code>--rate 0.99</code> | **display-only** hourly rate for the dashboard estimate |
| default GPU | <code>NVIDIA GeForce RTX 5090</code> |
| default cloud | <code>COMMUNITY</code> |
| default disk | 350 GB ephemeral container disk |
| Network Volume | **none** |

> [!WARNING]
> <code>--rate</code> does **not** control Runpod billing. It only tells the dashboard what number to use for its rough session-cost display. Your real price is whatever Runpod charges for the Pod you receive.

Override the defaults if needed:

~~~bash
bash launcher/start.sh \
  --gpu 'NVIDIA GeForce RTX 5090' \
  --cloud COMMUNITY \
  --hours 5 \
  --disk 350 \
  --rate 0.99
~~~

The launcher prints something like:

~~~text
Creating ephemeral Runpod Pod. No persistent/network volume is requested...

Pod: abc123xyz
Dashboard: https://abc123xyz-8000.proxy.runpod.net
Session access token: <temporary random token>
Hard session target: 5h
~~~

Keep that terminal output open.

---

# First production run

**Do not start with 50 clips.**

The safest first real test is:

1. Open the printed **Dashboard URL**.
2. Paste the printed **session access token**.
3. Enter your creator name.
4. Select **LTX-2.5**.
5. Upload one valid start frame.
6. Leave End Frame empty for the first test.
7. Select **4 seconds**.
8. Set **Variations = 1**.
9. Use a simple motion prompt.
10. Click **Generate batch**.

Example prompt:

~~~text
Natural handheld smartphone UGC. The person holds the package,
looks down at it and begins opening the top flap naturally.
Subtle body movement, realistic hands, slight phone-camera motion,
normal indoor lighting, no cinematic camera move.
~~~

### Why one clip first?

The application, queue, export, metadata-cleaning and termination flow are covered by automated tests.

The part that depends on the exact GPU, model access and CUDA/runtime combination is **real model inference**.

Use this sequence:

~~~text
1 clip
  ↓
verify
  ↓
10 clips
  ↓
verify speed + quality
  ↓
large batches
~~~

---

# Dashboard workflow

## 1. Choose who is creating

Example:

~~~text
Who's creating?
Mehmet
~~~

The creator name is stored locally in that browser and attached to every queued job.

That is how two people can share one render session without mixing up outputs.

---

## 2. Choose a renderer

### LTX-2.5

**Use this first.**

Best V1 fit for:

- rapid UGC iteration
- short controlled motion
- first-frame + last-frame control
- many variations
- native audio experiments

~~~text
Start Frame:  yes
End Frame:    yes
Duration:     4–10 sec
Audio:        supported by the model path
Final output: 720×1280
~~~

The adapter uses the official fast distilled pipeline.

---

### Wan 2.2 I2V A14B

Use it when you want a different motion/fidelity profile.

~~~text
Start Frame:  yes
End Frame:    no
Duration:     4–10 sec
Final output: 720×1280
~~~

The upstream I2V checkpoint is very large, roughly **126 GB**.

Because UGC Factory intentionally has no persistent model storage, first use in every fresh Pod has a significant download/setup cost.

That is why Wan is an alternate engine, not the default spam engine.

---

### SkyReels V3

Use it for reference-driven shots where subject/product consistency matters.

~~~text
Reference Frame: yes
End Frame:       no
Duration:        5 sec
Resolution:      720p path
~~~

The dashboard is capability-aware and does not expose controls the adapter does not truly support.

---

## Model matrix

| Renderer | Start / Reference | End Frame | Duration | Audio | V1 role |
|---|---:|---:|---:|---:|---|
| **LTX-2.5** | ✅ | ✅ | 4–10s | ✅ | default mass-generation engine |
| **Wan 2.2** | ✅ | ❌ | 4–10s | ❌ | fidelity/motion alternate |
| **SkyReels V3** | ✅ | ❌ | 5s | ❌ | reference consistency alternate |

---

# Batch generation

Set:

~~~text
Variations
20
~~~

and submit once.

The backend creates 20 jobs with different seeds:

~~~text
Mehmet · LTX-2.5 · rendering
Mehmet · LTX-2.5 · queued
Mehmet · LTX-2.5 · queued
...
~~~

V1 uses **one render worker per Pod** because one Pod represents one GPU.

Both creators can queue work simultaneously, but the single GPU renders those jobs sequentially.

The queue/renderer architecture is already separated so future multi-GPU scheduling can be added without redesigning the dashboard.

---

# Two people, one GPU

This is supported from V1.

### Person 1

~~~text
Mehmet
20 × Bayern unboxing
~~~

### Person 2

Opens the same Dashboard URL with the same temporary session token:

~~~text
Joshua
20 × Dortmund reaction
~~~

Shared queue:

~~~text
01  Mehmet   LTX-2.5       rendering
02  Mehmet   LTX-2.5       queued
03  Joshua   SkyReels V3   queued
04  Joshua   SkyReels V3   queued
...
~~~

### Share only

- Dashboard URL
- temporary UGC Factory session access token

### Do not share

- <code>RUNPOD_API_KEY</code>
- <code>HF_TOKEN</code>

---

# Automatic video finalization

Raw model output never goes straight to download.

Every successful job passes through:

~~~text
MODEL OUTPUT
     ↓
FFmpeg
     ↓
exact 720×1280
H.264 / yuv420p
audio preserved when present
chapters removed
ordinary container metadata removed
     ↓
ExifTool
     ↓
standard visible metadata removed
     ↓
CLEAN MP4
~~~

The raw intermediate is deleted after the clean file is created.

> [!NOTE]
> This removes ordinary file/container metadata. It does not remove visible watermarks, perceptual fingerprints, or information Instagram, TikTok or YouTube create after upload.

---

# Downloading results

You can:

- preview clips in the gallery
- download one clean MP4
- select multiple ready clips
- export selected clips as one ZIP

A successful download marks that job as downloaded.

This matters because of the termination safety system.

---

# Ending a session correctly

When you are finished:

1. Wait until the queue is empty.
2. Download every clip you want to keep.
3. Click the red **Terminate Pod** button.
4. Confirm.
5. The dashboard disconnects when the Pod disappears.

## Stop is not Terminate

For this project the goal is **zero persistent Runpod infrastructure between render sessions**.

Runpod distinguishes stopping a Pod from deleting/terminating it.

UGC Factory is designed around:

~~~text
RENDER
   ↓
DOWNLOAD
   ↓
TERMINATE
   ↓
Pod deleted
Local Pod disk deleted
No Network Volume exists
   ↓
UGC Factory idle Runpod cost = $0
~~~

---

## Termination guard

Normal termination is rejected when:

- a job is queued
- a job is rendering
- a job is being cleaned
- a completed output is still marked undownloaded

Example:

~~~text
⚠ 3 active jobs
⚠ 7 undownloaded outputs

Terminate blocked.
~~~

Force terminate remains available, but it permanently destroys files that still exist only on that Pod.

---

## Hard runtime watchdog

If you launch with:

~~~bash
bash launcher/start.sh --hours 5
~~~

the app starts a watchdog.

Its purpose is simple:

> If you forget about the machine, do not let the GPU run forever.

The watchdog can terminate the Pod when the configured deadline is reached.

**Download important outputs before that deadline.**

---

# Cost model

UGC Factory does not use per-generation credits.

The core cost is approximately:

~~~text
GPU hourly price
×
time Pod exists
~~~

plus whatever resource charges Runpod applies to the Pod you selected.

There is intentionally:

- no Network Volume
- no persistent UGC Factory database
- no persistent model cache after Pod termination

### The trade-off

Every fresh session starts clean:

~~~text
new Pod
  ↓
model must download again
  ↓
first generation takes longer
~~~

Later jobs with the same model in the **same session** reuse the model files already on that Pod.

So the architecture makes most sense for concentrated render sessions:

~~~text
Start GPU
→ render hard for 3–5 hours
→ download everything
→ terminate
~~~

not one tiny generation at a time.

---

# Recommended production workflow

For short-form e-commerce and UGC testing:

~~~text
1. Prepare 10–30 strong start frames before starting Runpod
2. Start one 3–5 hour GPU session
3. Test LTX with one short generation
4. Queue 10 variants
5. Check motion + product consistency
6. Queue larger batches
7. Use Wan / SkyReels for shots that benefit from them
8. Download winners continuously
9. Export final ZIPs
10. Terminate the Pod
~~~

That keeps expensive GPU time focused on inference instead of creative planning.

---

# Example: 20-variant UGC shot

### Start frame

~~~text
Woman sitting on a sofa with the product box in her hands.
~~~

### Prompt

~~~text
Natural handheld iPhone-style UGC. She looks at the box,
raises one hand naturally and starts opening the top flap.
Keep the motion simple and realistic. Subtle camera shake,
normal indoor lighting, natural hands, no cinematic movement.
~~~

### Settings

~~~text
Renderer:   LTX-2.5
Duration:   4 sec
Variations: 20
Output:     720×1280
~~~

The goal is not to make one generation carry an entire 20-second ad.

Generate **short controllable shots**, then edit the strongest shots together.

---

# Local development without paying for a GPU

UGC Factory includes a mock renderer.

Requirements:

- Python 3.11+
- FFmpeg
- ExifTool

Create an environment:

~~~bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
~~~

Set a local access token inside <code>.env</code>:

~~~text
APP_ACCESS_TOKEN=dev
UGC_RENDERER_MODE=mock
~~~

Start:

~~~bash
uvicorn app.main:app --reload --port 8000
~~~

Open:

~~~text
http://localhost:8000
~~~

Enter:

~~~text
dev
~~~

The mock renderer generates placeholder MP4s so the complete UI → queue → cleaner → preview → ZIP → terminate-guard flow can be tested without CUDA.

---

# Tests

~~~bash
pytest -q
python -m compileall app launcher tests
bash -n scripts/*.sh launcher/start.sh
node --check static/app.js
~~~

The automated suite covers:

- renderer capabilities
- shared multi-user queue
- 720×1280 normalization
- ordinary metadata removal
- video preview
- ZIP download
- download-state tracking
- safe termination guard
- mock end-to-end flow

GitHub Actions runs CI automatically.

---

# Troubleshooting

## Permission denied on launcher/start.sh

Use:

~~~bash
bash launcher/start.sh --hours 5 --rate 0.99
~~~

instead of executing the file directly.

---

## Runpod cannot pull ghcr.io/voekee/ugc-factory:latest

Check:

1. **GitHub → Actions → Build container** is green.
2. The GHCR package exists.
3. The package is public, or Runpod has valid registry credentials.

Do not solve this by putting a GitHub personal access token into this repository.

---

## LTX fails with Hugging Face 401 / 403

Check:

1. You completed the model access flow while logged into Hugging Face.
2. Your token has read access.
3. You exported it before launching:

~~~bash
export HF_TOKEN='hf_...'
~~~

Then launch a **new Pod** so the environment receives the token.

---

## RTX 5090 is unavailable

Pass another Runpod GPU type:

~~~bash
bash launcher/start.sh \
  --gpu 'YOUR RUNPOD GPU TYPE' \
  --hours 5 \
  --disk 350
~~~

GPU availability is controlled by Runpod and changes over time.

---

## First generation is slow

Expected.

This project has **no persistent model cache**.

First use of a renderer inside a fresh Pod can include:

- cloning pinned upstream code
- creating the renderer environment
- installing renderer dependencies
- downloading model weights
- loading weights into memory

Later jobs with that same renderer in the same session avoid most of that setup.

---

## Switching to Wan suddenly uses a lot of disk

Expected.

Wan 2.2 I2V is a very large checkpoint.

The default ephemeral disk is 350 GB so a normal session has room for models and outputs.

If you intentionally use several large engines in one session:

~~~bash
bash launcher/start.sh --disk 450 --hours 5
~~~

Check your Runpod configuration and pricing before increasing resources.

---

## Terminate is blocked

That is the safety system.

Check:

- queue is empty
- no job says rendering
- no job says cleaning
- completed outputs you care about were downloaded

Then terminate again.

---

## Dashboard opens but generation fails

Reduce the test to:

~~~text
LTX-2.5
4 seconds
1 variation
one valid start frame
simple prompt
~~~

Inspect the Pod logs before queueing a large batch.

---

# Security model

## Secrets

Never commit:

~~~text
RUNPOD_API_KEY
HF_TOKEN
APP_ACCESS_TOKEN
~~~

<code>.env</code> is ignored by Git.

## Team access

Your teammate needs only:

- dashboard URL
- temporary session token

They do not need your Runpod or Hugging Face credentials.

## Data persistence

Inputs, outputs and the SQLite queue live on the temporary Pod.

Terminate it:

~~~text
queue database → gone
model cache    → gone
inputs         → gone
outputs        → gone
~~~

Anything you need later must be downloaded first.

---

# Environment variables

See <code>.env.example</code>.

| Variable | Purpose |
|---|---|
| <code>RUNPOD_API_KEY</code> | create and terminate Pods |
| <code>RUNPOD_SESSION_NAME</code> | identify the current session |
| <code>APP_ACCESS_TOKEN</code> | protect dashboard/API |
| <code>HF_TOKEN</code> | gated model download access |
| <code>UGC_RENDERER_MODE</code> | <code>real</code> on Runpod, <code>mock</code> locally |
| <code>DATA_DIR</code> | ephemeral working directory |
| <code>SESSION_STARTED_AT</code> | elapsed-time calculation |
| <code>SESSION_HOURLY_RATE_USD</code> | display estimate only |
| <code>MAX_SESSION_HOURS</code> | watchdog limit |
| <code>LTX_RUNNER_CMD</code> | override LTX adapter |
| <code>WAN_RUNNER_CMD</code> | override Wan adapter |
| <code>SKYREELS_RUNNER_CMD</code> | override SkyReels adapter |

---

# Reproducibility

Renderer source is pinned instead of pulling a moving branch at inference time.

| Renderer | Pinned revision |
|---|---|
| LTX-2 | <code>a95ab856bf29407b6b066ede0abe1846050db56c</code> |
| Wan 2.2 | <code>1ea34ff48f87168174e12956e200b1d908b1c5ff</code> |
| SkyReels V3 | <code>28c771e8456341be6a213e3d1133ed1fd19bf75d</code> |

Model checkpoints still come from their respective upstream repositories.

---

# Repository architecture

~~~text
ugc-factory/
│
├── app/
│   ├── main.py              FastAPI routes
│   ├── db.py                ephemeral SQLite queue
│   ├── queue_worker.py      single-GPU worker
│   ├── metadata.py          FFmpeg + ExifTool finalizer
│   ├── runpod.py            session status + terminate
│   ├── watchdog.py          hard runtime safety
│   └── renderers/
│       ├── base.py          renderer contract
│       ├── command.py       shell adapter
│       └── mock.py          zero-GPU local testing
│
├── scripts/
│   ├── run_ltx.sh
│   ├── run_wan.sh
│   └── run_skyreels.sh
│
├── launcher/
│   ├── start.sh
│   └── runpod_launcher.py
│
├── static/
│   ├── index.html
│   ├── app.js
│   └── styles.css
│
├── assets/
├── tests/
├── Dockerfile
└── docker-compose.yml
~~~

The important abstraction is:

~~~text
Dashboard / Queue
       │
       ▼
Renderer Adapter
       │
  ┌────┼────┐
  ▼    ▼    ▼
 LTX  Wan  SkyReels
~~~

A future model can be added without rebuilding the queue, dashboard, metadata cleaner or Runpod lifecycle.

---

# What V1 intentionally does not do

UGC Factory is intentionally focused.

It does **not** currently include:

- payments
- user accounts
- permanent cloud history
- persistent model storage
- a multi-GPU scheduler
- an ad library
- a full editing timeline
- automatic social publishing
- external paid video-generation APIs

The V1 goal is:

> **Get a temporary GPU, generate a lot of short UGC, keep the winners, kill the machine.**

---

# Model licenses

This repository does **not** redistribute model weights.

Every user is responsible for reviewing and complying with the current upstream model license and access terms before use, especially for commercial work. Upstream terms can change independently of this repository.

The UGC Factory application code itself is licensed under the repository's [MIT License](LICENSE).

---

# Validation boundary

Covered by local/CI testing:

- API
- multi-user queue
- mock generation
- output normalization
- metadata-cleaning flow
- browser UI syntax
- ZIP export
- termination guard
- Python compilation

A real CUDA render still depends on:

- selected Runpod GPU
- upstream model availability
- gated-model permissions
- CUDA/runtime combination
- upstream model dependencies

For that reason, every new deployment should begin with:

~~~text
LTX-2.5
4 seconds
1 variation
~~~

before a large batch.

---

<p align="center">
  <strong>START GPU → GENERATE HARD → DOWNLOAD WINNERS → TERMINATE</strong>
</p>

<p align="center">
  No credits per clip. No Network Volume. No idle render farm.
</p>
