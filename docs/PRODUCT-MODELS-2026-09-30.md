# Product video model paths — 30 September 2026

Target inspected: `New project-3.mp4` and `New project.mp4`, both H.264, 480×852, 24 FPS, 4.04 seconds, silent. Scenes: hand installing a compact car-door projector; blue circular logo projected on paving. User wants newly generated video, not reuse of the original footage. Still reference images may guide new scenes.

## What is implemented

| Path | Inputs and purpose | Evidence |
| --- | --- | --- |
| Wan 2.2 Lightning I2V | One first frame, silent product variants, 720×1280 at 16 FPS, four trained steps | Previous real resident-worker test: 97.41 seconds warm per 4-second clip. Not a benchmark on these two product clips. |
| SkyReels V3 Reference2Video | One to four still references for product/person/scene, first reference aspect, five seconds, 24 FPS, official eight-step BF16 path | New resident adapter, API, database, UI and isolated runtime preparation. CPU contracts pass. GPU timing and product fidelity pending. |
| LTX-2.5 distilled 22B | First and optional last keyframe, audio, existing native adapter | Already implemented; no measured comparison with Wan on this hardware. Loads anew per clip in the existing path. |
| LongCat Avatar 1.5 | Portrait plus driving speech/audio, talking creator | Not integrated into this product flow. Official multi-GPU/audio runtime would require a separate prepared image and audio-upload flow. Silent mounting/projection clips are not its intended task. |
| MiniMax H3 | Native first/last plus audio | Contract tests only; deployment license authorization remains required before allocation/execution. |

These are task capabilities, not 9/10 rankings. None establishes parity with Kling or Seedance or guarantees unchanged logos, correct finger contact or physical installation mechanics. Review geometry, logo/lettering, contact, temporal stability and camera motion for each usable output. A reference is not a guaranteed first/last keyframe in SkyReels.

## Changes and safeguards

- Resident SkyReels subprocess uses the bounded, serialized job protocol and timeout/process-group recovery already exercised for Wan. Model/source revisions are pinned; output is H.264/yuv420p/faststart. No dependency installation or source checkout on a paid Pod.
- Additional image inputs are validated, stored once by content hash, persisted with the jobs, reused across variations and preserved on explicit retry. Models that do not accept them reject them before queueing. At most four references; no forced aspect match between independent product/scene references.
- SkyReels uses a dedicated session. An unprepared image is blocked before allocation; switching to it inside a loaded Wan/LTX session is blocked.
- The separate SkyReels runtime keeps Torch 2.9.1/CUDA 12.8 and the working Wan/LTX environments. Only upstream package initializers are narrowed to the reference pipeline, avoiding unneeded talking-avatar and distributed dependencies; official reference transformer/SDPA/scheduler implementation remains intact. No quantization or reduction below its trained eight steps.
- Wan text cache stores exact detached embeddings on CPU, bounded to eight prompts, and preserves the reference, random seed, frame count, resolution, weights and trained schedule. It is not frame/latent caching. `WAN_PROMPT_CACHE=0` disables it. Its extra speed benefit is unmeasured until a new GPU run.
- Generate stays disabled while uploads are prepared/queued, even when periodic status refresh completes.
- Idle timeout stays 600 seconds. All paid validation Pods must be independently verified terminated.

## Further speed work

The prior 100×4-second estimate was approximately 2h42m after loading on one tested GPU. It is an extrapolation, not a 100-video run. More throughput would require measured kernels/compilation or independent GPU workers. More GPUs increase spend. FP8/NVFP4, sparse attention, lower resolution, interpolation and fewer steps must not be presented as the same proven quality. SkyReels eight-step 24 FPS output is a fidelity experiment, not an assumed faster renderer.

Official sources: [SkyReels V3](https://github.com/SkyworkAI/SkyReels-V3), [LTX pipeline choices](https://github.com/Lightricks/LTX-2/blob/main/packages/ltx-pipelines/docs/pipeline-selection.md), [LongCat Video/Avatar](https://github.com/meituan-longcat/LongCat-Video), [Diffusers Wan pipeline](https://github.com/huggingface/diffusers/blob/v0.38.0/src/diffusers/pipelines/wan/pipeline_wan_i2v.py).
