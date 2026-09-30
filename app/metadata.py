from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path


def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def strip_metadata(source: Path, destination: Path, *, preserve_canvas: bool = False, audio: bool = True) -> None:
    """Normalize to social 720x1280 and remove ordinary MP4/container metadata."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    if preserve_canvas:
        _run(["ffmpeg", "-y", "-i", str(source), "-map", "0:v:0",
              *(["-map", "0:a?"] if audio else ["-an"]), "-c", "copy",
              "-map_metadata", "-1", "-map_chapters", "-1", "-movflags", "+faststart", str(destination)])
        return
    _run([
        "ffmpeg", "-y", "-i", str(source),
        "-map", "0:v:0", *(["-map", "0:a?"] if audio else ["-an"]),
        "-vf", "scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "17", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-map_metadata", "-1", "-map_chapters", "-1",
        "-metadata", "creation_time=", "-metadata", "encoder=",
        "-movflags", "+faststart",
        str(destination),
    ])
    if shutil.which("exiftool"):
        _run(["exiftool", "-all=", "-overwrite_original", str(destination)])


def inspect_metadata(path: Path) -> dict:
    proc = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", str(path)],
        check=True, capture_output=True, text=True,
    )
    return json.loads(proc.stdout)
