# Fully generated product clips: live validation, 30 September 2026

The supplied four-second videos were inspected and used only to extract still references. All output video frames were newly generated. The originals were not modified, reused as footage or composited into the results. Neither a model name nor the copied 9/10 ratings establishes a quality benchmark.

## A. COMPUTER USE VERIFIED

- Safari: selected SkyReels and uploaded a product still through the file picker in the local synthetic application; later opened the actual archived SkyReels projection MP4 and played it to its five-second end. Real Wan Safari generation/playback/download from the preceding pass is documented separately in `WAN-RESIDENT-VALIDATION-2026-09-30.md`.
- Visible Codex browser: real launcher GPU selection, H3 blocked before Start, SkyReels and Wan session creation, duplicate Start clicks, refresh during startup, authentic workspace opening, uploads, product-scene presets, quantity, Generate double clicks, queue, live states, refresh recovery, real MP4 playback and downloads.
- Exactly two Wan jobs after Generate × 2 double-click; no duplicate batch or second Pod. Exactly one Pod for each session after duplicate Start and refresh.
- SkyReels's two-reference mounting job and three-reference projection job completed. End-after-queue was double-clicked while the second job was running, then the page refreshed. The worker retained the ending barrier and completed/archive-saved both jobs before verified termination. The launcher visibly showed GPU TERMINATED. The remote page honestly showed connection lost after its Pod disappeared, with Generate disabled.
- Wan refresh recovered the same two jobs and GPU association. After idle termination, launcher refresh showed GPU TERMINATED; its Saved videos links successfully downloaded the warm clip from the local archive. A direct worker download attempted after termination was unavailable; the archive recovered the result.
- Separate localhost synthetic UI checks: four-reference previews/limit, reference removal, invalid-image decode error, model switches, unavailable H3/disabled Generate, missing-reference error, double Generate, queue persistence, synthetic playback/download. These are UI evidence, not model-inference evidence.
- Fixed misleading stale archive-error text, mixed form settings during async uploads, submission labels, unsupported End Frame controls, and cryptic archive names. New UI source checked locally; final image build validates inherited runtimes on CPU. No extra GPU was rented solely for these UI corrections.

## B. LIVE RUNPOD VERIFIED

Both sessions used one Community RTX PRO 6000 Blackwell Workstation Edition, 96 GB VRAM, reported $1.69/hour, 180 GB ephemeral disk, no network volume and a 30-minute maximum. Before each allocation the actual creation time was recorded and RunPod listed zero UGC Pods.

| Purpose | Pod ID | Before allocation UTC | Recorded start UTC | Verified termination UTC | Estimated GPU compute |
| --- | --- | --- | --- | --- | --- |
| SkyReels references | `3egis73c2rngkw` | 17:29:53 | 17:30:07 | 17:56:14 | ~$0.736 |
| Wan prompt cache + idle | `dik7r5nbxmaoda` | 17:58:36 | 17:58:44 | 18:08:29 | ~$0.275 |

These are runtime × reported rate estimates, not invoices; storage/network charges are not included. Real creation, monitoring, honest startup/model-download/model-loading/generation phases, actual outputs, archive, termination requests and post-termination RunPod listings were observed. Each exact Pod was absent; the `ugc-factory-*` orphan check returned zero. No API secrets are included in this report.

The Wan session alone used a 75-second local-guardian idle threshold. Its idle timer began 18:07:05 UTC; verified termination was 84.36 seconds later, within the 15-second polling interval. No End request was used to trigger that idle test. Production default remains 600 seconds, and no active session or temporary global idle override remains.

| Real job | Input | Duration / output | Renderer wall time |
| --- | --- | --- | --- |
| `f66d4383b058445fb1ef8fae8b32b34e` | SkyReels product + door | 5.04s, 720×1280, 24 FPS | 639.19s cold, including download/load |
| `1d6c2af396654419980083d7cf759b98` | SkyReels projection + product + logo crop | 5.04s, 720×1280, 24 FPS | 559.40s warm |
| `617a24a82f404b96beed97221c0557d0` | Wan projection, first prompt encoding | 4.06s, 720×1280, 16 FPS | 316.87s cold, including download/load |
| `03be8e23a8094481b214c99de1a8d27e` | Wan same prompt/reference, new seed | 4.06s, 720×1280, 16 FPS | 96.88s warm |

Real logs show SkyReels model reuse and Wan model plus prompt-embedding reuse. SkyReels cold download took 89.07s and load 7.54s. Two different SkyReels reference sets are not a controlled cold/warm speed comparison. Wan's new result is effectively the prior ~97-second warm baseline; no substantial extra cache speedup is claimed.

Subjective visual review of all four outputs: SkyReels mounting has plausible hand motion, but the compact projector changes shape and surface markings; reject this as an exact-product ad. SkyReels projection keeps the circular blue S04 motif recognizable, but small details vary. Both restrained Wan projection variants preserve the motif and paving reasonably well in inspected frames. These narrow examples do not verify complex installation mechanics, exact typography or all products. No Kling/Seedance equivalence claim.

100 four-second Wan clips at this measured warm cadence would be approximately 2h42m on one GPU, plus cold startup and any rejected outputs. This is extrapolation, not a 100-video endurance test or the time for 100 edited multi-scene ads. SkyReels's measured warm cadence would be approximately 15h32m for 100 five-second clips. Clip lengths/FPS and references differ, so these are task-specific throughput estimates rather than a matched model benchmark.

## C. AUTOMATED TEST VERIFIED

55 pytest tests pass, including first/last H3 contract indices 0/-1, license/allocation gates, session safety, references and retries, bounded exact-dtype CPU prompt LRU, resident subprocess reuse and timeout recovery. JavaScript syntax and Git whitespace checks pass. Mocked/CPU contracts do not substitute for the real inference results above.

## D. NOT YET VERIFIED

- Real H3 inference, actual Start + End fidelity, audio, generation time, throughput, cost per output and Ref2VA. H3 remains gated; no authorization was invented or restricted weights executed.
- Reliable exact-product installation, exact lettering across arbitrary motion, quality parity with Kling/Seedance, or a production 100-video batch.
- LTX quality/speed comparison on these product references. Existing LTX keyframe/audio path remains available in its own session.
- LongCat Avatar 1.5 integration, portrait/audio UI and inference. It is a talking-creator path and has not been presented as an available silent-product renderer.
- FP8/NVFP4, custom attention, compilation, multi-GPU batch scaling or claims that reduced precision/steps preserve quality. No such unmeasured shortcuts were enabled.

Local evidence and MP4s: `~/.ugc-factory/validation/2026-09-30-product-models/` and `~/.ugc-factory/sessions/{3egis73c2rngkw,dik7r5nbxmaoda}/`. Lifecycle files contain sanitized Pod facts, never credentials. Original/reference/generated product media are not committed to Git.

Final worker: `ghcr.io/voekee/ugc-factory@sha256:705a3fbc52304cec52eabc6535141b2be4f61333342da2f26d038097abbde82d`, source `4b651f6`, successful build `36756942176` and CI `36756942260`. Inherits the actual GPU-tested runtime/image `4dcb299…`; renderer code, weights and dependency pins are unchanged from the live run. Final copy changes affect UI wording/control layout and local archive labels. Public image pullability checked without renting a GPU. Local launcher defaults and saved image are updated to this immutable image; main is not merged.
