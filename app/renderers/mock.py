from __future__ import annotations

import subprocess

from app.renderers.base import RenderRequest, Renderer


class MockRenderer(Renderer):
    id = "mock"

    def render(self, req: RenderRequest) -> None:
        req.output_path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run([
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", f"testsrc2=s=720x1280:d={req.duration}",
            "-r", "24", "-pix_fmt", "yuv420p",
            "-metadata", "comment=mock-metadata-to-remove",
            str(req.output_path),
        ], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
