"""Check a staged FL2VA checkpoint on its storage host without loading tensors."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def check_weights(root: Path) -> dict:
    family = root / "FL2VA"
    for path in (root / "model_index.json", family / "model_index.json"):
        try:
            index = json.loads(path.read_text())
            if not isinstance(index, dict):
                raise ValueError("model index must be an object")
        except (OSError, ValueError) as exc:
            raise ValueError(f"Missing or invalid H3 index: {path}") from exc
    for name in ("processor", "tokenizer"):
        path = family / name
        if not (path / "tokenizer_config.json").is_file():
            raise ValueError(f"Missing H3 {name} configuration")
    files = set()
    for name in ("text_encoder", "transformer", "video_vae", "audio_vae"):
        component = (family / name).resolve()
        if not (component / "config.json").is_file():
            raise ValueError(f"Missing H3 {name} configuration")
        candidates = set(component.rglob("*.safetensors"))
        if not candidates:
            raise ValueError(f"Missing H3 {name} weights")
        for path in component.glob("*.safetensors.index.json"):
            try:
                index = json.loads(path.read_text())
                names = set(index["weight_map"].values())
                if not names:
                    raise ValueError("empty weight map")
                for shard in names:
                    resolved = (component / shard).resolve()
                    if not resolved.is_relative_to(component):
                        raise ValueError("shard path leaves its component")
                    candidates.add(resolved)
            except (OSError, ValueError, KeyError, TypeError) as exc:
                raise ValueError(f"Invalid H3 {name} shard index") from exc
        for path in candidates:
            if not path.is_file() or path.stat().st_size < 1024:
                raise ValueError(f"Missing or incomplete H3 weight shard: {path.name}")
        files.update(candidates)
    return {"family": "FL2VA", "weight_files": len(files),
            "weight_bytes": sum(p.stat().st_size for p in files),
            "check": "File presence and shard completeness only; GPU inference not verified"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model_root", type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(check_weights(args.model_root), indent=2))
    except ValueError as exc:
        parser.exit(1, f"H3 checkpoint not ready: {exc}\n")


if __name__ == "__main__":
    main()
