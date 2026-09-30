from __future__ import annotations

from collections import deque
import os
import shlex
import subprocess
import signal
import threading

from app.config import settings
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

        log_dir = settings.data_dir / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / f"{req.job_id}.log"

        tail: deque[str] = deque(maxlen=240)

        with log_path.open("w", encoding="utf-8", errors="replace") as log_file:
            process = subprocess.Popen(
                shlex.split(self.command),
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=1,
                start_new_session=True,
            )

            timed_out = threading.Event()
            def expire():
                if process.poll() is None:
                    timed_out.set()
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
            timer = threading.Timer(settings.render_timeout_seconds, expire)
            timer.daemon = True
            timer.start()
            try:
                assert process.stdout is not None
                for line in process.stdout:
                    log_file.write(line)
                    log_file.flush()
                    tail.append(line)
                return_code = process.wait()
            finally:
                timer.cancel()
            if timed_out.is_set():
                raise TimeoutError(f"Renderer {self.id} exceeded its {settings.render_timeout_seconds}s timeout")

        if return_code != 0:
            diagnostics = "".join(tail).strip()
            raise RuntimeError(
                f"Renderer {self.id} failed with exit code {return_code}."
                + (f"\n\n{diagnostics[-12000:]}" if diagnostics else "")
            )

        if not req.output_path.exists() or req.output_path.stat().st_size < 1024:
            diagnostics = "".join(tail).strip()
            raise RuntimeError(
                f"Renderer {self.id} exited without producing a valid output."
                + (f"\n\n{diagnostics[-6000:]}" if diagnostics else "")
            )
