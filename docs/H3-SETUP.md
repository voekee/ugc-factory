# H3 preparation, before connecting a GPU

The local setup prepares **H3-Base FL2VA**, native first and last keyframes,
768p, BF16, 50 steps, and one resident SGLang process. It does not allocate
a Pod, download weights, or claim measured H3 speed or quality.

MiniMax's official Context-IR planner and Regenerate-2K are hosted components,
not part of the released self-hosted base. This setup does not imply that the
complete official 2K product is running locally.

## Prepare this Mac

```sh
.venv/bin/python scripts/setup_h3.py --operator-country CN --deployment-country CN
bash start.sh
```

The owner-only file `~/.ugc-factory/h3.env` stores declared countries and
connection settings separately from Git. The normal launcher loads it on
startup. Operator and desired deployment country are declarations; a saved
`CN` value does not verify where a GPU actually runs. Existing RunPod
credentials, working Wan/SkyReels images, and idle defaults remain unchanged.

Private operation in China can use the community path subject to all terms.
Country selection is not license acceptance. After reading the actual license,
the operator can explicitly record acceptance with:

```sh
.venv/bin/python scripts/setup_h3.py --accept-community-license
```

Even this command leaves execution disabled. EU, UK, US and Republic of Korea
deployments/operators require separate written authorization; this command
rejects them. Output/use restrictions also apply.

## Connect later

1. Verify the physical deployment country with the provider. Do not infer it
   from browser location or a configuration field.
2. Choose the dedicated H3 topology. `h100-4` uses four H100 80 GB cards;
   `h200-4` uses four H200 cards; `5090-2` uses two RTX 5090 cards and needs
   a 384 GB-class host for its CPU offload recipe. These are upstream recipes,
   not locally GPU-validated configurations or price estimates.
3. Build `Dockerfile.h3` using **Build container → runtime h3**. Its distinct
   candidate tag does not replace the working Wan/SkyReels runtime. Record
   the resulting immutable digest. A successful container build is not a
   CUDA/renderer smoke test.
4. After license acceptance, stage only `model_index.json` and `FL2VA/*`
   from `MiniMaxAI/MiniMax-H3` at `/runpod-volume/models/MiniMax-H3` on the
   selected persistent volume. No startup download is allowed. Persistent
   storage can cost money even when no GPU runs.
5. Save connection details, without enabling execution:

```sh
.venv/bin/python scripts/setup_h3.py \
  --profile h100-4 \
  --worker-image ghcr.io/voekee/ugc-factory@sha256:ACTUAL_DIGEST \
  --volume-id ACTUAL_VOLUME_ID --datacenter-id ACTUAL_DATACENTER_ID
```

6. Validate location, staged files, image pull, multi-GPU stock and total hourly
   price before any paid launch. The ordinary browser launcher continues to
   block H3 allocation until the dedicated connection is validated; its
   single-GPU offers are not a truthful H3 price quote. A controlled GPU smoke
   test is the next separate operation. Enable only for that explicit test,
   check real readiness, generate a first/last-frame clip, archive the result,
   terminate and query the exact Pod again. Never leave a test Pod running.

Use `scripts/benchmark_h3.py` only after an authorized ready worker exists.
It measures observed results and requests session end; the guardian must
separately verify actual termination. No H3 inference is verified yet.

## Sources

- [Official H3 license](https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/LICENSE)
- [Official release, base vs hosted components](https://github.com/MiniMax-AI/MiniMax-H3)
- [Pinned SGLang hardware recipes](https://github.com/sgl-project/sglang/blob/7b30ff26eea8b593efe00d429eb001ad446c3f2a/docs/cookbook/diffusion/MiniMax/MiniMax-H3.mdx)
