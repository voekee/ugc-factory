from __future__ import annotations

import os
import shlex
import subprocess

from app.renderers.base import RenderRequest, Renderer


class CommandRenderer(Renderer):
    def __init__(self, renderer_id: str, command: str):
        self.id = renderer_id
        self.command = command

    def render(self, req: RenderRequest) -> None:
        env = os.environ.copy()
        env.update({
            "UGC_JOB_ID": req.job_id,
            "UGC_PROMPT": req.prompt,
            "UGC_DURATION": str(req.duration),
            "UGC_SEED": str(req.seed),
            "UGC_START_FRAME": str(req.start_frame or ""),
            "UGC_END_FRAME": str(req.end_frame or ""),
            "UGC_OUTPUT": str(req.output_path),
        })
        req.output_path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(shlex.split(self.command), check=True, env=env)
        if not req.output_path.exists() or req.output_path.stat().st_size < 1024:
            raise RuntimeError(f"Renderer {self.id} exited without producing a valid output")
