# Product validation evidence — 2026-09-30

Work performed in `/Users/josh/ugc-factory`, branch `codex/h3-session-safety`.
The core session pass is **complete for LTX on the tested L40**: real Safari operation, three real Pod lifecycles, and one genuine LTX render/playback/download/archive were performed. This does not establish every GPU/model combination. The Mac lock interrupted the first pass; browser work later resumed. No H3 authorization was recorded or inferred. No H3 weights were downloaded or executed.

## A. Computer Use verified

All items below were operated through native Safari using Computer Use, not API substitutions:

- Opened the local launcher, recovered saved credentials, and displayed live RunPod offers.
- Selected the cheapest available GPU (RTX 3070 Community, $0.13/hour) for explicit infrastructure-test mode.
- Selected H3 before allocation: Start became disabled and displayed “H3 execution requires deployment authorization. No GPU will be allocated.” Returned to the synthetic infrastructure configuration.
- Double-clicked Start for each successful live allocation. Refreshed the launcher during the first allocation and during the second active startup. The recovered session remained associated with its single Pod; API listings independently confirmed only one Pod at a time.
- Observed GPU STARTING / container-running states with Open workspace disabled. Observed actual health-confirmed Workspace available after correcting proxy client headers, then opened and authenticated to the actual application on the second Pod.
- Double-clicked End during the first Pod's startup and refreshed during shutdown. Saw ENDING SESSION; later refreshed and saw the persistent “GPU TERMINATED · verified with RunPod” banner.
- On the second real Pod, observed the worker's automatic idle transition to `ending`, with Generate disabled. An attempted submission during that transition did not create a job.
- On the local actual application with its synthetic renderer: selected unavailable H3 and saw Generate disabled; selected LTX; uploaded both start and end frames, with decoded dimensions shown; replaced a mismatched end frame; removed/replaced a start frame; uploaded a corrupt PNG and saw “This image could not be decoded.”
- Submitted mismatched portrait/landscape frames and saw a clear matching-aspect-ratio error. Removed the required start frame and saw “Add a start frame first.” Entered creator/prompt and changed quantity to four.
- Created four synthetic videos through the UI, observed the queue and completed result cards, refreshed and recovered the same four results, played an MP4 in Safari (Pause control and advancing playback), and downloaded it through Safari's download permission flow. The downloaded MP4 was independently present in Downloads (1,939,777 bytes).
- Started a separate CPU-only controlled-failure batch and cancelled a waiting job through the Queue UI; its active count fell from three to two. The fixture never invoked a GPU or model.

A native Safari screenshot exposed the composer covering result controls; the layout was changed to normal document flow. The Download link was then exercised successfully. Safari's file picker initially disabled the PNG fixtures with the restrictive MIME list; `image/*` plus application-side PNG/JPEG/WebP validation worked and enabled the corrupt-image test.

Computer Use then reported: the Mac is locked and automatic unlock could not unlock it. An unlock was requested. No further browser actions are claimed after that block.

## B. Live RunPod verified

The API key was used server-side and is not included in this report. Both Pods were real, paid, single-GPU **NVIDIA GeForce RTX 3070 / Community / 8 GB**, with RunPod reporting `costPerHr: 0.13`.

| Evidence | Manual startup shutdown | Automatic idle shutdown |
| --- | --- | --- |
| Pre-click UTC time | 03:34:21 | 03:36:12 |
| Pod ID | `adczz1q9b4y61o` | `j851254gsiwr4w` |
| Pod name | `ugc-factory-c746ace6` | `ugc-factory-6528bdf4` |
| Saved creation time UTC | 03:34:29.822 | 03:36:20.895 |
| Fresh listing confirmed creation | 03:34:36.442, RUNNING | 03:36:31.738, RUNNING |
| Termination verification persisted UTC | 03:34:54.868 | 03:38:47.930 |
| Independent exact-ID absence check UTC | 03:35:03.023 | 03:38:56.399 |
| Trigger | Safari End session during startup | 75-second development worker idle watchdog, then external guardian verification |
| Orphan check after closure | Zero `ugc-factory-*` Pods | Zero `ugc-factory-*` Pods |

The small `python:3.11-slim-bookworm` container bootstrapped the current application, FFmpeg and Python dependencies. Its renderer was explicitly synthetic; it downloaded no model weights and received no Hugging Face token. The second application became reachable through RunPod's real HTTP proxy. This validates infrastructure and application reachability, **not real model inference**.

The first attempted allocation (03:32:06 UTC) was rejected by RunPod's GraphQL parser before allocation because the SDK did not escape startup-command quotes. Two fresh listings found no Pod; the exact failed creation journal was cleared only after identifying the parser rejection. Startup-command serialization was corrected before the successful tests.

Another live failure was RunPod proxy HTTP 403 / code 1010 for the old client signature. A valid HTTP User-Agent fixed readiness probes and guardian communication. Browser readiness was not fabricated while these probes failed.

Final cleanup check at **03:45:04 UTC**: zero `ugc-factory-*` Pods, no active session, no pending creation. The development launcher and local renderer fixture were stopped. The launcher was restarted without `UGC_LIFECYCLE_TEST`; normal idle timeout remains **600 seconds**. Test timeout values exist only in closed session history and the explicit opt-in development helper.

## C. Automated test verified

**38 pytest tests passed**, with one upstream Starlette/httpx deprecation warning. Python compilation, both JavaScript syntax checks, shell syntax, and `git diff --check` passed.

Coverage includes image decoding/aspect checks, atomic batches/claims, queue cancellation, interrupted-job recovery and explicit retry, command timeout, mocked H3 asynchronous request/download contracts, first/last keyframe indices 0 and -1, license gates, verified-deletion retries, archive persistence/acknowledgment, orphan recovery and hard-cap behavior.

Added regression coverage exercises concurrent HTTP launch requests (one allocation, three conflicts), H3/invalid-model rejection before spending, idempotent End while the worker is unavailable, the default 600-second idle timeout, proxy authentication headers, and opt-in synthetic bootstrap packaging without weights/secrets.

These tests do not replace the live evidence above. H3 is **CONTRACT VERIFIED**, not **REAL H3 INFERENCE VERIFIED**.

## D. Not yet verified

- CPU-only Retry was subsequently exercised in Safari: the failed job completed and displayed playback/download controls after Retry.
- Every alternate legacy model configuration and exhaustive invalid quantity/configuration paths through Safari remain unverified. End Frame upload/removal was subsequently exercised in Safari.
- Alternate GPU types and Wan/SkyReels real inference remain unverified. The complete L40/LTX flow was subsequently verified below.
- Real LTX Start + End Frame fidelity and sustained throughput remain unverified; one Start Frame real render succeeded.
- Real H3 inference, Start + End Frame fidelity, generation time, throughput, GPU utilization during inference, cost per output, audio quality, Ref2VA, and production readiness.
- H3 candidate Docker image build, CUDA/SGLang compatibility and authorized GPU smoke test.
- Final visual recheck of the last small message/cost/recovery fixes after the lock. Their syntax and regression checks passed; that is not visual verification.

The launcher guardian still depends on the local launcher process remaining alive. The in-Pod watchdog is a second defense once the application starts; neither substitutes for an always-on external controller if the Mac is off and the container cannot boot.

## Resumed real renderer pass

- Safari selected NVIDIA L40 Community at the API-reported $0.69/hour, a 30-minute hard limit, and the immutable branch image `ghcr.io/voekee/ugc-factory@sha256:b12d048f5ecbb324285071482e091edbcc592ab9b7622cef6371786de6146b67`. Main's latest image was not changed.
- Pre-create timestamp: 03:56:12 UTC. Fresh RunPod listing at 03:56:34.669 UTC confirmed `medgy03486xot8` (`ugc-factory-a90b9a71`) RUNNING, NVIDIA L40, 151 GB host RAM, 9 vCPUs, $0.69/hour.
- This session uses `UGC_RENDERER_MODE=real`, no synthetic lifecycle bootstrap. Safari opened and authenticated to its health-confirmed workspace.
- Safari uploaded a generated test illustration `product.png` (768×1280), entered a camera-motion prompt, selected four seconds and one output, and clicked Generate. Job `e7d89e4baaf44655aa8be2a2dccca686` entered model download. The worker reports Torch 2.9.1 CUDA 12.8 and NVIDIA L40 with CUDA available.
- Refreshing Safari during model download recovered the same one active job and runtime/cost display. Draft file inputs reset on refresh; the submitted job remains persisted.
- Preflight now requires valid Hugging Face model access before paid legacy allocation, at least 48 GB VRAM, 128 GB host RAM and eight vCPUs. LTX two-stage dimensions corrected to 768×1280 (multiples of 64). Final output remains 720×1280.
- Found and fixed queue live-log expansion resetting each poll; this fix is local source validation until the next worker image is built. Launcher step switching now avoids removing/readding the same active view and repeated smooth scrolling.

### Real render outcome and final cleanup

- The real LTX job completed at **04:08:51.962 UTC**, following submission at 04:00:14.168 UTC (about 8m38s including first-use downloads). Logs confirmed real CUDA denoising, upsampling and video/audio decoding.
- Safari showed the completed result, played it (Pause control observed), downloaded it after the normal site download prompt, and clicked End session.
- Safari download: `/Users/josh/Downloads/Validation-ltx25-4s-e7d89e4b.mp4`, 308,276 bytes. ffprobe confirms H.264 video, 720×1280, AAC audio, 4.041667 seconds.
- Guardian archive: `~/.ugc-factory/sessions/medgy03486xot8/e7d89e4baaf44655aa8be2a2dccca686.mp4`, same byte size, with metadata and archival acknowledgment marker. Safari's Saved videos on this Mac showed the archived download after termination.
- Guardian verified real termination at **04:09:43.213 UTC**. Independent fresh RunPod query at **04:09:57.628 UTC** confirmed exact ID `medgy03486xot8` absent and **zero `ugc-factory-*` Pods**. Safari refresh showed “GPU TERMINATED · verified with RunPod”.
- Tracked session duration 13m21s × $0.69/hour ≈ **$0.154 estimated compute**. This is not a billing invoice and excludes storage or other provider charges. No extra Pod was created for inference.
- The final minor UI/token-handling fixes were built successfully in workflow `36667325771`, image digest `sha256:efe617884b42c53e3e5c6fd7c865969a987299d50de0c347b2a2fc77e01465e0`. Launcher defaults and this Mac's saved image are pinned to it. That final image build is verified; the live inference used the preceding b12d digest.
- Normal idle timeout remains 600 seconds. Local CPU fixture was stopped. No H3 model was loaded or authorized.
