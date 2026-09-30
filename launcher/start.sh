#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${UGC_LAUNCHER_VENV:-$ROOT/.venv-launcher}"
UV_BIN="${UGC_UV_BIN:-}"

find_uv() {
  if [ -n "$UV_BIN" ] && [ -x "$UV_BIN" ]; then
    return 0
  fi

  if command -v uv >/dev/null 2>&1; then
    UV_BIN="$(command -v uv)"
    return 0
  fi

  if [ -x "$HOME/.local/bin/uv" ]; then
    UV_BIN="$HOME/.local/bin/uv"
    return 0
  fi

  return 1
}

install_uv() {
  if ! command -v curl >/dev/null 2>&1; then
    echo "UGC Factory needs curl to install its local launcher runtime."
    echo "curl is normally included with macOS."
    exit 1
  fi

  echo "Installing the small local runtime manager…"
  curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null

  if [ -x "$HOME/.local/bin/uv" ]; then
    UV_BIN="$HOME/.local/bin/uv"
  elif command -v uv >/dev/null 2>&1; then
    UV_BIN="$(command -v uv)"
  else
    echo "uv was installed, but the launcher could not find it."
    echo "Close Terminal, open it again, then run: bash start.sh"
    exit 1
  fi
}

venv_is_compatible() {
  if [ ! -x "$VENV/bin/python" ]; then
    return 1
  fi

  "$VENV/bin/python" - <<'PY' >/dev/null 2>&1
import sys
raise SystemExit(0 if sys.version_info >= (3, 10) else 1)
PY
}

if ! find_uv; then
  install_uv
fi

if ! venv_is_compatible; then
  if [ -d "$VENV" ]; then
    echo "Replacing the old launcher environment with Python 3.12…"
    rm -rf "$VENV"
  else
    echo "Preparing the local UGC Factory launcher…"
  fi

  "$UV_BIN" python install 3.12 >/dev/null
  "$UV_BIN" venv --python 3.12 --seed "$VENV" >/dev/null
  "$VENV/bin/pip" install --quiet -r "$ROOT/launcher/requirements.txt"
elif ! "$VENV/bin/python" -c "import runpod, pydantic_settings" >/dev/null 2>&1; then
  echo "Finishing the local launcher setup…"
  "$VENV/bin/pip" install --quiet -r "$ROOT/launcher/requirements.txt"
fi

exec "$VENV/bin/python" "$ROOT/launcher/onboarding.py" "$@"
