"""Validated, EXIF-oriented, content-addressed input assets, shared by every variation."""
from __future__ import annotations
import hashlib
import io
import os
import tempfile
import warnings
from pathlib import Path
from PIL import Image, ImageOps, UnidentifiedImageError
from app.config import settings


def store_image(payload: bytes) -> str:
    if len(payload) > settings.max_upload_mb * 1024 * 1024:
        raise ValueError("Image exceeds upload size limit")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(payload)) as source:
                if source.format not in {"PNG", "JPEG", "WEBP"}:
                    raise ValueError("Use a PNG, JPEG or WebP image")
                if getattr(source, "n_frames", 1) != 1:
                    raise ValueError("Animated images are not supported")
                if min(source.size) < 32 or max(source.size) > 8192 or source.width * source.height > 32_000_000:
                    raise ValueError("Image dimensions must be 32–8192 pixels and at most 32 megapixels")
                image = ImageOps.exif_transpose(source).convert("RGB")
                buf = io.BytesIO()
                image.save(buf, format="PNG")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValueError("Invalid or oversized image") from exc
    normalized = buf.getvalue()
    folder = settings.data_dir / "inputs"
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / (hashlib.sha256(normalized).hexdigest() + ".png")
    if not dest.exists():
        fd, tmp = tempfile.mkstemp(dir=folder, suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as out:
                out.write(normalized)
            os.replace(tmp, dest)
        finally:
            Path(tmp).unlink(missing_ok=True)
    return str(dest)


def validate_pair(start: str | None, end: str | None) -> None:
    if not start or not end:
        return
    with Image.open(start) as a, Image.open(end) as b:
        if abs((a.width / a.height) / (b.width / b.height) - 1) > 0.02:
            raise ValueError("Start and end frames must have matching aspect ratios (within 2%); crop them to the same composition first")
