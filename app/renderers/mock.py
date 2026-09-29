from __future__ import annotations

import subprocess

from app.renderers.base import RenderRequest, Renderer


class MockRenderer(Renderer):
    id = "mock"

    def render(self, req: RenderRequest) -> None:
        req.output_path.parent.mkdir(parents=True, exist_ok=True)
        label = req.prompt.replace("'", "")[:48]
        subprocess.run([
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", f"color=c=0x111216:s=720x1280:d={req.duration}",
            "-vf", f"drawtext=text='{label}':fontcolor=white:fontsize=34:x=(w-text_w)/2:y=(h-text_h)/2",
            "-r", "24", "-pix_fmt", "yuv420p",
            "-metadata", "comment=mock-metadata-to-remove",
            str(req.output_path),
        ], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
