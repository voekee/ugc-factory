"""One isolated Wan process per worker, with serialized requests and bounded recovery."""
from __future__ import annotations

import json
import os
import queue
import shlex
import signal
import subprocess
import threading
import time
from collections import deque

from app.config import settings
from app.renderers.base import Renderer, RenderRequest

RESULT_PREFIX = "@@WAN_RESULT@@"


class WanRenderer(Renderer):
    id = "wan22"

    def __init__(self):
        self._lock = threading.Lock()
        self._process = None
        self._lines = None

    def close(self):
        process = self._process
        self._process = None
        if process is not None:
            if process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            process.wait(timeout=10)
            for stream in (process.stdin, process.stdout):
                if stream:
                    stream.close()

    def _start(self):
        if self._process is not None and self._process.poll() is None:
            return
        self.close()
        lines = queue.Queue()
        process = subprocess.Popen(
            shlex.split(settings.wan_runner_cmd) + ["--resident"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1, start_new_session=True,
        )
        self._process, self._lines = process, lines

        def read():
            try:
                for line in process.stdout:
                    lines.put(line)
            finally:
                lines.put(None)

        threading.Thread(target=read, name="wan-log", daemon=True).start()

    def render(self, req: RenderRequest):
        with self._lock:
            req.output_path.parent.mkdir(parents=True, exist_ok=True)
            log_dir = settings.data_dir / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            tail = deque(maxlen=30)
            try:
                self._start()
                payload = {"job_id": req.job_id, "prompt": req.prompt,
                           "duration": req.duration, "seed": req.seed,
                           "start_frame": str(req.start_frame) if req.start_frame else None,
                           "output": str(req.output_path)}
                self._process.stdin.write(json.dumps(payload) + "\n")
                self._process.stdin.flush()
                deadline = time.monotonic() + settings.render_timeout_seconds
                with (log_dir / (req.job_id + ".log")).open("w") as log:
                    while True:
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            raise TimeoutError("Video generation timed out. The model process was reset; you can retry.")
                        try:
                            line = self._lines.get(timeout=remaining)
                        except queue.Empty:
                            raise TimeoutError("Video generation timed out. The model process was reset; you can retry.")
                        if line is None:
                            raise RuntimeError("Video engine stopped unexpectedly. You can retry; the model will reload.")
                        if line.startswith(RESULT_PREFIX):
                            result = json.loads(line[len(RESULT_PREFIX):])
                            if result.get("job_id") != req.job_id:
                                raise RuntimeError("Video engine response did not match this job. The engine was reset.")
                            if not result.get("ok"):
                                raise RuntimeError(result.get("error") or "Video generation failed. You can retry.")
                            break
                        log.write(line)
                        log.flush()
                        tail.append(line.strip())
                if not req.output_path.exists() or req.output_path.stat().st_size < 1024:
                    raise RuntimeError("Video engine returned an empty video. Please retry.")
            except Exception:
                # No ambiguous outstanding inference survives a timeout or protocol failure.
                self.close()
                req.output_path.unlink(missing_ok=True)
                raise


wan_renderer = WanRenderer()
