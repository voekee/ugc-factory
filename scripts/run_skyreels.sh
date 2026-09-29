#!/usr/bin/env bash
set -euo pipefail
: "${UGC_OUTPUT:?}"
: "${UGC_PROMPT:?}"
: "${UGC_START_FRAME:?SkyReels V3 V1 requires a reference frame}"
[ "${UGC_DURATION}" = "5" ] || { echo "SkyReels V3 reference adapter currently supports 5 seconds" >&2; exit 2; }
CODE_ROOT="${CODE_ROOT:-/opt/ugc-models}"
SKYREELS_REV="${SKYREELS_REV:-28c771e8456341be6a213e3d1133ed1fd19bf75d}"
mkdir -p "$CODE_ROOT"
if [ ! -d "$CODE_ROOT/SkyReels-V3/.git" ]; then git clone --no-checkout --filter=blob:none https://github.com/SkyworkAI/SkyReels-V3.git "$CODE_ROOT/SkyReels-V3"; fi
git -C "$CODE_ROOT/SkyReels-V3" fetch --depth 1 origin "$SKYREELS_REV"
git -C "$CODE_ROOT/SkyReels-V3" checkout --detach -q "$SKYREELS_REV"
if [ ! -d "$CODE_ROOT/SkyReels-V3/.venv" ]; then uv venv --seed "$CODE_ROOT/SkyReels-V3/.venv" --python 3.12; "$CODE_ROOT/SkyReels-V3/.venv/bin/pip" install -r "$CODE_ROOT/SkyReels-V3/requirements.txt"; fi
TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT
MARKER="$TMPDIR/before"
touch "$MARKER"
cd "$CODE_ROOT/SkyReels-V3"
"$CODE_ROOT/SkyReels-V3/.venv/bin/python" generate_video.py   --task_type reference_to_video --ref_imgs "$UGC_START_FRAME" --prompt "$UGC_PROMPT"   --duration 5 --resolution 720P --offload --seed "$UGC_SEED"
FOUND="$(find "$CODE_ROOT/SkyReels-V3/result/reference_to_video" -type f -name "${UGC_SEED}_*.mp4" -newer "$MARKER" -print 2>/dev/null | sort | tail -n 1)"
[ -n "$FOUND" ] || { echo "SkyReels produced no mp4" >&2; exit 3; }
mv "$FOUND" "$UGC_OUTPUT"
