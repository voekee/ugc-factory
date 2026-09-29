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

        proc = subprocess.run(
            shlex.split(self.command),
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        if proc.returncode != 0:
            stdout = (proc.stdout or "").strip()
            stderr = (proc.stderr or "").strip()

            details = []
            if stderr:
                details.append("stderr:\n" + stderr[-7000:])
            if stdout:
                details.append("stdout:\n" + stdout[-5000:])

            message = "\n\n".join(details) or "No renderer output was captured."
            raise RuntimeError(
                f"Renderer {self.id} failed with exit code {proc.returncode}.\n\n{message}"
            )

        if not req.output_path.exists() or req.output_path.stat().st_size < 1024:
            stdout = (proc.stdout or "").strip()
            stderr = (proc.stderr or "").strip()
            diagnostics = "\n".join(part for part in [stderr[-3000:], stdout[-3000:]] if part)
            raise RuntimeError(
                f"Renderer {self.id} exited without producing a valid output."
                + (f"\n\n{diagnostics}" if diagnostics else "")
            )
