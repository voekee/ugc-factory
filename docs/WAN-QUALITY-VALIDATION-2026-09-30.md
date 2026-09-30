# Wan UGC validation — 2026-09-30

User rejected further LTX testing. This pass implemented and ran Wan2.2-I2V-A14B with trained Lightning acceleration. Two real four-second product-demo clips completed. H3 stayed gated. No parity claim with H3, Seedance 2.5 or Kling 3.0 is established.

## A. Computer Use verified

Native Safari, actual launcher and real RunPod-hosted UGC Factory:

- Selected RTX PRO 6000 Blackwell Workstation Edition, Community, 96 GB, $1.69/hour, 30-minute hard limit, immutable worker image.
- Started a session; observed GPU STARTING, disabled Open workspace, then health-confirmed Workspace available.
- Refreshed during startup: recovered the same Pod and cost/runtime state.
- Opened the worker. Wan Lightning was available, H3 unavailable, End Frame explicitly unsupported.
- Uploaded a generated fictional adult creator holding an unbranded serum bottle. Entered a restrained single-shot product-demo prompt, four seconds, one variation; clicked Generate.
- Observed queue and real download/loading/inference logs. Completed result appeared.
- Played the first MP4 in Safari: controls advanced from zero to four seconds and ended normally. Clicked Download and accepted Safari's download permission.
- Submitted one cached repeat. Refreshed during inference: one active job, same Pod, previous result preserved; no duplicated queue or Pod. Unsubmitted image/prompt inputs reset on refresh; persisted jobs and creator recovered.
- Downloaded the repeat, clicked End session, observed ending state and disabled Generate.
- Returned to launcher: GPU TERMINATED after RunPod verification. Fixed stale readiness/utilization text and reloaded the actual terminated session to verify the correction.
- Expanded Saved videos on this Mac and downloaded the second archive after the Pod was gone.

Additional, explicitly synthetic CPU visual regression: loaded the updated frontend in Safari against a read-only local fixture. Verified both header and queue badge show Loading model, then Generating. No paid allocation or inference occurred in this fixture; it is not counted as live renderer evidence.

## B. Live RunPod verified

### Full 40-step attempt, stopped for cost/time

- Pod `efz74zxw53s5aw`, name `ugc-factory-e4a867ac`, RTX PRO 6000 Blackwell Workstation Edition, 96 GB, $1.69/hour.
- Pre-create 06:17:50 UTC; saved start 06:18:10.783 UTC. Creation confirmed by fresh RunPod listing; 227 GB host RAM, 16 vCPUs.
- Job `afddc20f2e644fd6b4dbd046774eb76d` downloaded real weights and entered genuine inference. Forty-step CFG 3.5 run settled near 36 seconds/step, so projected completion exceeded the 30-minute cap.
- Stopped via Safari End now with explicit disposable-test force confirmation. No video completed; this attempt does not establish quality.
- Terminated 06:34:32.020 UTC. Independent listing 06:34:46.961 UTC: zero UGC Factory Pods. Approximate compute $0.46.

### Successful Lightning session

- Pod `7s2obh7g062of6`, name `ugc-factory-e6282668`.
- RTX PRO 6000 Blackwell Workstation Edition, 96 GB, Community, actual reported rate $1.69/hour; 167 GB host RAM, 37 vCPUs.
- Pre-click 06:52:41 UTC; saved start 06:52:49.623 UTC. Fresh listing at 06:52:55.887 UTC verified creation/RUNNING.
- Thirty-minute cap, normal 600-second idle timeout; development lifecycle mode off.
- One Pod only during both jobs and browser refreshes.

| Job | Created UTC | Finished UTC | End-to-end | Denoising only |
|---|---|---|---|---|
| `0905c17d8cab47e2ad89a5bcfee23ad2` | 06:57:16.269 | 07:03:41.380 | 6m 25s | ~96s |
| `91df96e99e2b49bcbb224e39f8817547` | 07:04:47.720 | 07:08:21.545 | 3m 34s | ~97s |

First-job time includes the cold download. Repeat reuses disk weights but still starts a process, loads the model and merges adapters per job; it is not a resident warm-pipeline benchmark. Denoising times come from the live four-step progress logs, not advertising. Do not infer throughput from denoising alone.

- Both outputs: actual generated H.264 MP4, 720×1280, 16 FPS, silent, 65 frames / 4.0625 seconds.
- First download 2,622,308 bytes; repeat 2,355,630 bytes. Both archived under the local session directory with metadata and archive acknowledgments.
- End-session request came from Safari. Guardian verified exact Pod deletion at 07:08:46.409 UTC.
- Independent fresh RunPod listing at 07:08:55.684 UTC: exact Pod absent, **zero `ugc-factory-*` Pods**.
- Runtime ~15m 57s, estimated GPU compute **$0.449** for this session. Includes startup, downloads, two jobs and inspection. Storage/other charges are not included. Both Wan attempts together used approximately $0.91 compute.

## C. Automated and build verified

- **40 pytest tests passed**. H3 gate/FL2VA request-contract tests remain; 0/-1 frame indices are contract evidence only.
- Actual offer VRAM validation rejects unsuitable Wan allocation before billing; host RAM request is 160 GB minimum. CPU build validates real high/low adapter tensors: 800 converted keys/shapes each, against a metadata-only model, plus the two-high/two-low schedule.
- Regression test prevents checkpoint progress bars being misclassified as inference even after more than 5 KB of loading logs.
- Fixed header/queue phase copy, termination stale telemetry/readiness, and redundant ready-state override during shutdown.
- Lightning inference image: `sha256:d5c6a4f5ac1b27c9acc7ff9b9575be6e720bc038ae36dd6ef5333988b0121c7f`, build `36679958108`, source `1aefa08`.
- Later images only correct status/UI behavior; final pinned image/build recorded below. Those UI corrections were visually checked locally without allocating another GPU. Renderer code and dependency pins remain identical to the live-tested image.

## Model configuration and visual assessment

- Base `Wan-AI/Wan2.2-I2V-A14B-Diffusers`, revision `596658fd9ca6b7b71d5057529bbf319ecbc61d74`, Apache 2.0.
- `lightx2v/Wan2.2-Lightning`, revision `18bccf8884ec0a078eed79785eb4ef13ea16ce1e`, I2V rank-64 Seko V1 high/low adapters, unit strength, Apache 2.0.
- BF16 base transformers, FP32 VAE, native PyTorch SDPA, CPU model offload, VAE tiling. Euler/simple shift 5, four trained steps split two high/two low, CFG 1. Negative prompting is inactive at CFG 1.
- Isolated prebuilt Wan environment: Diffusers 0.38.0, PEFT 0.18.1, Torch 2.9.1 CUDA12.8. No install/compilation during GPU billing.
- Sample inspection: recognizable consistent face, restrained head/smile/blink movement, bottle tilt following the hand, visible green cap/leaf icon, stable kitchen composition. No obvious catastrophic hand/body deformation in inspected frames. This is subjective inspection of two closely related clips, not a comprehensive quality benchmark.
- Useful for restrained silent product demonstrations. Fine packaging text was absent in the reference and has not been validated. Neither complex gestures nor broad product categories were tested.

## D. Not yet verified

- Real H3 inference, first/last frame fidelity, audio, generation time, throughput, cost/output, Ref2VA. H3 deployment authorization remains absent; no H3 weights executed.
- Quality parity with proprietary H3/Seedance/Kling systems, consistent exact typography, complex hands/interactions, long clips, large batches and extensive product/identity benchmarks.
- Wan native End Frame and audio are unsupported by this adapter.
- A resident Wan pipeline and model-cache reuse across terminated Pods are not implemented. No persistent paid storage is created.
- Earlier duplicate-click, shutdown-repeat and 75-second idle tests are documented in `VALIDATION-2026-09-30.md`; this Wan pass rechecked refresh but did not repeat another paid idle-only test. Normal idle timeout is 600 seconds.

## Local artifacts

- Safari downloads: `~/Downloads/Wan-Lightning-UGC-wan22-4s-0905c17d.mp4` and `~/Downloads/Wan-cached-repeat-wan22-4s-91df96e9.mp4`.
- Durable launcher copies: `~/.ugc-factory/sessions/7s2obh7g062of6/`.

## Sources

- https://huggingface.co/Wan-AI/Wan2.2-I2V-A14B-Diffusers
- https://huggingface.co/lightx2v/Wan2.2-Lightning
- https://huggingface.co/docs/diffusers/api/pipelines/wan

## Final published worker

Build `36682343734` succeeded from source `baf5dad`. Final launcher and saved local default pin `sha256:c098241906b9cd872232b82eae64cc9817e0bab1e950e56601f8cb298444240b`. This contains the exact live-tested Wan renderer and dependencies plus the subsequent UI/status fixes; no further paid Pod was allocated for those fixes. `codex/h3-session-safety` is pushed; main is not merged.

Final independent cleanup check: 2026-09-30T07:18:00.890053+00:00 — zero UGC Factory Pods; both Wan test IDs absent. Normal idle timeout 600 seconds, lifecycle test mode off.
