from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path


def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def strip_metadata(source: Path, destination: Path, expected_duration: float | None = None) -> None:
    """Normalize to social 720x1280 and remove ordinary MP4/container metadata."""
    destination.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "ffmpeg", "-y",
        "-fflags", "+genpts",
        "-i", str(source),
        "-map", "0:v:0", "-map", "0:a?",
        "-vf", "scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,fps=24,format=yuv420p,setpts=N/(24*TB)",
        "-af", "aresample=async=1:first_pts=0",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "17", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-map_metadata", "-1", "-map_chapters", "-1",
        "-metadata", "creation_time=", "-metadata", "encoder=",
        "-movflags", "+faststart",
    ]
    if expected_duration is not None:
        cmd += ["-t", f"{float(expected_duration):.3f}"]
    cmd.append(str(destination))
    _run(cmd)

    if shutil.which("exiftool"):
        _run(["exiftool", "-all=", "-overwrite_original", str(destination)])


def inspect_metadata(path: Path) -> dict:
    proc = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", str(path)],
        check=True, capture_output=True, text=True,
    )
    return json.loads(proc.stdout)


def validate_source_duration(path: Path, expected_duration: float) -> None:
    data = inspect_metadata(path)
    video = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    if video is None:
        raise RuntimeError("Renderer output has no video stream.")
    duration = float(video.get("duration") or data.get("format", {}).get("duration") or 0)
    if duration < expected_duration - 0.35:
        raise RuntimeError(
            f"Renderer output is truncated at {duration:.2f}s; expected about {expected_duration:.1f}s."
        )


def validate_video(path: Path, expected_duration: float) -> dict:
    """Reject truncated or malformed outputs before the UI marks them ready."""
    data = inspect_metadata(path)
    streams = data.get("streams", [])
    video = next((stream for stream in streams if stream.get("codec_type") == "video"), None)
    if video is None:
        raise RuntimeError("Final MP4 has no video stream.")

    try:
        duration = float(data.get("format", {}).get("duration") or video.get("duration") or 0.0)
    except (TypeError, ValueError):
        duration = 0.0

    width = int(video.get("width") or 0)
    height = int(video.get("height") or 0)

    minimum = max(0.5, float(expected_duration) - 0.35)
    maximum = float(expected_duration) + 0.5

    if not minimum <= duration <= maximum:
        raise RuntimeError(
            f"Final MP4 duration is {duration:.3f}s; expected about {expected_duration:.1f}s. "
            "Refusing to publish a truncated video."
        )
    if (width, height) != (720, 1280):
        raise RuntimeError(f"Final MP4 is {width}x{height}; expected 720x1280.")

    if video.get("codec_name") != "h264" or video.get("pix_fmt") != "yuv420p":
        raise RuntimeError("Final MP4 is not H.264 yuv420p video.")

    # ffprobe checks structure; a full decode catches damaged frames in an otherwise valid container.
    decode = subprocess.run(
        ["ffmpeg", "-v", "error", "-xerror", "-i", str(path), "-map", "0:v:0", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    if decode.returncode != 0:
        raise RuntimeError("Final MP4 contains corrupt video frames: " + decode.stderr[-500:])

    return {"duration": duration, "width": width, "height": height}
