import shutil
import subprocess
from pathlib import Path
import pytest
from app.metadata import strip_metadata, inspect_metadata

@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="ffmpeg missing")
def test_metadata_strip(tmp_path: Path):
    raw=tmp_path/"raw.mp4"; clean=tmp_path/"clean.mp4"
    subprocess.run(["ffmpeg","-y","-f","lavfi","-i","color=c=black:s=320x240:d=1","-metadata","comment=secret-tag",str(raw)],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    assert inspect_metadata(raw).get("format",{}).get("tags",{}).get("comment")=="secret-tag"
    strip_metadata(raw,clean)
    assert inspect_metadata(clean).get("format",{}).get("tags",{}).get("comment") in (None,"")


def test_metadata_normalizes_vertical_720p(tmp_path: Path):
    raw=tmp_path/"wide.mp4"; clean=tmp_path/"vertical.mp4"
    subprocess.run(["ffmpeg","-y","-f","lavfi","-i","color=c=black:s=640x360:d=1",str(raw)],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    strip_metadata(raw,clean)
    data=inspect_metadata(clean)
    video=next(stream for stream in data["streams"] if stream.get("codec_type")=="video")
    assert (video["width"], video["height"]) == (720,1280)
