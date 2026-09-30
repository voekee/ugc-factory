# Resident Wan speed validation — 2026-09-30

Implemented a single persistent isolated Wan process for the queue. Download, BF16 model load and Lightning adapter fusion occur once per worker process. On GPUs with at least 90 GiB memory, both experts stay on CUDA; smaller supported GPUs retain CPU offload with resident RAM weights. GPU jobs remain serialized. Errors, invalid protocol responses and timeouts kill the process group before a subsequent request can reload. Worker shutdown closes it. Custom runner commands retain the command adapter.

No inference steps, resolution, model revision, adapter strength, precision, scheduler or guidance parameters were reduced. This is a throughput improvement to the existing four-step preset, not a claim of proprietary-model parity or identical pixels across different seeds.

## A. Computer Use verified

Native Safari, actual local launcher and real RunPod-hosted product:

- Inspected the user's existing session and two real completed videos, including playback. Preserved both in the local archive before ending that session through the UI with explicit user approval.
- Observed GPU TERMINATED after fresh RunPod verification.
- Selected the lowest-price available suitable GPU, RTX PRO 6000 Blackwell Workstation Edition, Community, 96 GB; selected 30 minutes and verified the new immutable worker image in Advanced settings.
- Clicked Start session, observed an available workspace after its health check and opened it through the launcher.
- Uploaded the same fictional adult skincare creator reference as the previous benchmark. Entered the same product-demo prompt, selected four seconds and two variations, then clicked Generate × 2.
- Saw one downloading/loading/rendering job and one queued job. Refreshed Safari during download: recovered the same session and two jobs without duplicate allocation/submission. Unsubmitted inputs reset as before.
- Saw the first completed result and the second active job. Real worker logs verified the second reused the loaded model. This log reuse evidence was obtained through authenticated debugging reads; the UI showed real job phases and results.
- Played the warm result in Safari from zero to its four-second end. Clicked Download and allowed the browser's download permission. The actual MP4 is in Downloads.
- Clicked End session after both jobs completed and were archived. Reloaded the launcher: GPU TERMINATED, 19:17 elapsed, estimated compute $0.543.
- Fixed a launcher bug discovered in the previous live session: monitoring a healthy workspace for twelve minutes incorrectly raised a startup timeout. The deadline now applies only until readiness has first been observed. New starts also clear stale terminated/readiness text and workspace URLs before allocation. The corrected terminated UI was verified in Safari; the twelve-minute monitor regression was tested with a virtual clock, without another paid Pod.

## B. Live RunPod verified

Old user session `yftlzwh5h98e0x`: both completed outputs archived on this Mac. Started 15:12:07.179883 UTC; termination verified 15:37:26.938893 UTC. Independent listing at 15:37:59.406749 UTC: exact Pod absent and zero UGC Factory Pods.

New benchmark Pod:

- ID `y523etimgxvzao`, name `ugc-factory-9f9797e2`.
- RTX PRO 6000 Blackwell Workstation Edition, 96 GB, Community, 167 GB host RAM and 37 vCPUs; reported GPU compute $1.69/hour.
- Pre-click 15:42:28 UTC; saved start 15:42:45.842439 UTC. Fresh listing at 15:43:30.143110 UTC confirmed RUNNING and exact image.
- Thirty-minute hard limit, normal 600-second idle timeout; no persistent volume.
- Exact image `sha256:5fded60862880be5e9585f060d746c1b85d6b34ac4b014e37ca61c14b23f4bf9`, build `36737311769`, source `8e1d9d1`.

| Job | State | Render wall time | Final metadata cleaning | Finished UTC |
|---|---|---:|---:|---|
| `43a9c5a68a3a44f79022e8e14ee805dc` | Cold download/load + real inference | 474.74 s | 0.42 s | 15:59:10.425951 |
| `a21fbde07c7648eba3822e94f36be2be` | Same loaded process, real inference | 97.00 s | 0.41 s | 16:00:47.884929 |

Both were submitted in one UI batch at 15:51:14.584885 UTC. The second job's submitted-to-completed time includes waiting for the first; **97.41 seconds is its actual processing time**, not its queue latency.

Cold log: download 253.33 s, load/merge/GPU placement 124.24 s. Warm log explicitly begins `Reusing loaded model; no download or adapter merge`. Four denoising steps took ~66.4 s, compared with ~97 s in the previous offloaded benchmark. Full warm result time is ~97.4 s including preparation, decode and MP4 finalization.

Previous four-second cached-file result was ~214 s. This sample achieved ~2.2× throughput / ~55% less processing time. It compares different seeds and two runs on the same GPU class, not a controlled multi-run statistical benchmark.

Extrapolation: 100 identical-config four-second clips × 97.41 s = ~2h 42m with the pipeline already loaded. Add roughly six minutes for this observed cold download/load and additional Pod startup. At $1.69/hour, steady processing compute is ~$4.57, excluding setup/storage/other charges. **No 100-video batch was run**, and longer clips, other prompts, host contention, retries and different hardware can change this estimate.

Termination verified 16:02:03.302875 UTC. Independent fresh listing at 16:02:18.752116 UTC: exact test Pod absent and **zero `ugc-factory-*` Pods**. Test runtime 19m 17s, approximate compute $0.543. Both new videos are archived locally before shutdown. Final cleanup recheck is recorded at completion.

## C. Automated / artifact verified

- 47 pytest tests pass: previous H3 gates, session/queue/termination protections, real subprocess reuse and separate logs, timeout/crash/mismatched-job recovery, actual resident worker loop loading exactly once for two requests, and real launcher JavaScript startup-deadline behavior using a virtual clock.
- CPU container build validated actual high/low adapter tensors: 800 keys/shapes each, plus two-high/two-low schedule. No GPU used for build/tests.
- Warm MP4 inspected with ffprobe: H.264, 720×1280, 16 FPS, 65 frames, 4.0625 s, 2,400,429 bytes. Frame inspection showed a coherent face, hand, green cap/leaf bottle and kitchen through the sampled clip. This is subjective sample inspection, not proof of universal product fidelity.
- Launcher defaults and saved local configuration pin the exact live-tested resident image. Subsequent commits update tests, launcher behavior/defaults and this report; the live-tested renderer code remains unchanged.
- Branch `codex/h3-session-safety` is pushed to `voekee/ugc-factory`; main remains unmerged.

## D. Not yet verified

- Real H3 inference, Start/End fidelity, speed, throughput, cost/output, Ref2VA and audio. Authorization gate remains intact; no restricted weights downloaded or executed.
- A 100-clip endurance run, memory peaks/throughput for longer clips and 80-GB offloaded resident mode, broad quality benchmarks, precise typography, complex product interactions and proprietary Kling/Seedance quality parity.
- Multi-GPU sharding, quantization, sparse attention, approximate caches and compiled inference were not enabled or claimed as measured improvements. No record-speed claim is established.
- Wan still produces silent video without a native End Frame path.

Local evidence: `~/.ugc-factory/sessions/y523etimgxvzao/`, `~/.ugc-factory/validation/2026-09-30-resident/`, and `~/Downloads/Wan-resident-speed-test-wan22-4s-a21fbde0.mp4`.

For a batch, queue the outputs and use End session to drain accepted jobs, archive their outputs and terminate after completion, rather than waiting through idle timeout. Keep the local launcher running for the guardian and local backups.
