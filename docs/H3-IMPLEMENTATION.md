# H3 and session safety — implementation status, 2026-09-30

Repository: `/Users/josh/ugc-factory`, origin `https://github.com/voekee/ugc-factory.git`.
The previously selected `/Users/josh/Documents/ChatGPT/ugc factory` is an unrelated empty Git initialization.

## Verified locally

- Existing mock renderer → persistent SQLite queue → FFmpeg output → metadata finalization → preview/download/ZIP remains covered by an integration test.
- Content-addressed image storage validates decoded PNG/JPEG/WebP, dimensions, EXIF orientation, and matching endpoint aspect ratios. All variations share the same normalized image files. Different aspect ratios are rejected instead of silently cropping the last frame.
- A batch is inserted atomically; multiple claimers cannot claim the same job. Cancelling a queued job cannot overwrite a running job. Restart marks interrupted jobs failed instead of replaying ambiguous GPU requests. Explicit retry increments an attempt count.
- End session blocks new work and drains accepted jobs. The CPU guardian archives completed videos and metadata under `~/.ugc-factory/sessions/<pod>/`, then verifies Pod absence with RunPod before clearing the tracked session. The launcher provides local downloads after termination.
- Failed shutdown keeps session identity, retries, and never announces verified termination. An exact pre-allocation session name is journaled before Pod creation; ambiguous API failures do not trigger another paid allocation. The guardian reconciles these names and detects still-running Pods from closed sessions. Unknown `ugc-factory-` Pods are surfaced with a termination action.
- Idle timeout defaults to 600 seconds; queued/running/encoding jobs inhibit idle closure. The worker and CPU guardian independently enforce the hard runtime cap. The cap intentionally takes priority over a failed archive connection; such a failure is recorded, and output loss remains possible at the cap.
- The browser no longer receives fabricated startup percentages or treats container uptime as application readiness. GPU price is fetched server-side rather than trusted from a browser payload. Unknown cost is displayed as unavailable.
- H3 FL2VA request contracts cover no frame, first frame, last frame, and both frames. Both endpoints use separate `keyframe` conditions with `frame_index: 0` and `-1`. An HTTP stub verifies asynchronous submission, polling, engine-job identity persistence, and MP4 retrieval. These are contract tests, **not H3 inference tests**.
- H3 keeps SGLang as a resident child process. The startup supervisor exposes loading/warming separately, marks readiness only after a successful warm-up, and clears readiness on exit. H3 finalization remuxes instead of cropping or re-encoding the native canvas; audio-off strips the soundtrack at export, not during model computation.

## License and hardware execution gate

The official [H3 license](https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/LICENSE) excludes the EU, UK, US, and Republic of Korea from its community grant. No authorization is inferred from the user's timezone or a GPU's location.

H3 execution requires explicit `H3_ENABLED`, `H3_LICENSE_AUTHORIZED`, ISO deployment and operator country codes, and `H3_LICENSE_MODE`. Excluded territories require `authorized` mode and a recorded reference to separate written authorization. These are administrator attestations, not independent license verification or a complete multi-tenant compliance system. No license was accepted, no model weights were downloaded, and no H3 model was run during this change.

`Dockerfile.h3` is a **candidate, unbuilt image**. Docker is unavailable on this Mac. It pins SGLang source revision `7b30ff26eea8b593efe00d429eb001ad446c3f2a`. Its dependency resolution, CUDA compatibility, readiness endpoint, startup command, and warm-up must pass a Linux/GPU smoke test before deployment. The existing LTX Dockerfile and deployment remain the default.

Topology candidates follow the current [SGLang H3 cookbook](https://github.com/sgl-project/sglang/blob/7b30ff26eea8b593efe00d429eb001ad446c3f2a/docs/cookbook/diffusion/MiniMax/MiniMax-H3.mdx): 4 H100 TP2/Ulysses2, 2 RTX 5090 TP2 with layerwise offload, and 4 H200 Ulysses4. No topology is claimed as validated by this project. The launcher candidate accepts `model="h3-fl2va"`, requires a configured persistent volume/datacenter, and applies a deployment-country filter. No volume has been provisioned or staged. Stage only the required FL2VA family and shared components at the model root; startup runs offline and refuses missing FL2VA weights.

## Real external checks

The Safari/live validation pass on 2026-09-30 created and terminated two real RTX 3070 Community Pods at RunPod's reported $0.13/hour. Manual startup shutdown and automatic idle shutdown both ended with verified Pod absence. See [the evidence report](VALIDATION-2026-09-30.md) for IDs, timestamps, browser actions, fixes, and incomplete checks.

These were infrastructure tests using the actual application with its explicitly synthetic renderer. No real model inference, model performance, cost/output, or frame fidelity is claimed. Ref2VA is not implemented.

## Remaining work and operating limits

1. Obtain deployment authorization, build the candidate image, stage weights, and perform the requested real smoke suite before enabling H3 in production. H3 is visible but disabled by default; the launcher UI still launches the existing legacy worker image.
2. The CPU guardian currently lives in the local launcher process. Browser closure does not stop it, but quitting the launcher or powering off the Mac does. An always-on CPU controller is required for independent termination verification through worker failure when the Mac is unavailable. The in-Pod watchdog alone cannot survive destruction of its own runtime.
3. The queue and inputs still reside on the Pod. Archived outputs and job metadata survive Pod termination; queued jobs do not yet resume on replacement Pods. No automatic Pod replacement or OOM profile fallback is enabled. Unsafe H3 errors pause submissions rather than repeatedly crashing.
4. One GPU request executes at a time. Concurrency and a CPU encode pipeline need real memory/throughput measurements before tuning. The command-based legacy models still reload per job. H3's resident pipeline avoids this, but has not been GPU-validated.
5. `scripts/benchmark_h3.py` records observed batch wall time, per-job render/finalization times, startup reports, and session cost metrics from an explicitly provisioned authorized worker. It requests graceful closure when finished. It does not provision or verify termination itself. Device-level VRAM/utilization telemetry and human quality review remain to be added. The runner has not been used on real H3.
6. UGC prompt compiler, presets, validated Fast/Balanced/Quality mappings, Ref2VA, product/creator profiles, distributed durable queue, and automatic hardware ranking remain pending. No arbitrary quality settings or performance figures were substituted.
7. Secrets remain in the existing local server-side config protected by mode 0600 inside a 0700 directory; they are masked in public responses. Encryption-at-rest/keychain migration is not included. The current worker still receives the RunPod key for its independent watchdog.
8. The existing UI has broader typography/contrast issues identified by the design detector. This change fixes control overflow and operational messages; it does not redesign the product.

## Local checks

38 tests passed locally. Python compilation, both JavaScript syntax checks, shell syntax, and Git whitespace checks passed. Browser inspection confirmed H3 generation is disabled without authorization and the mobile composer fits its viewport.

```sh
uv pip install --python .venv/bin/python -r requirements-dev.txt
.venv/bin/pytest -q
.venv/bin/python -m compileall -q app launcher scripts tests
node --check static/app.js
bash -n start.sh launcher/start.sh scripts/run_ltx.sh scripts/run_wan.sh scripts/run_skyreels.sh
git diff --check
```

Existing output tests generate synthetic test patterns locally with FFmpeg. They are explicitly mock results and must never be used as H3 performance evidence.
