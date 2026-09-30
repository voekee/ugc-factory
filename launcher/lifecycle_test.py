"""Explicit development-only real Pod / synthetic renderer validation.

No model weights or model credentials are shipped. Disabled unless the local
launcher process has UGC_LIFECYCLE_TEST=1. Never stored as a production default.
"""
import base64
import io
import json
import os
from pathlib import Path
import tarfile


def enabled():
    return os.environ.get("UGC_LIFECYCLE_TEST") == "1"


def pod_options():
    if not enabled():
        raise ValueError("Infrastructure test mode is disabled")
    root = Path(__file__).resolve().parents[1]
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w:gz") as tar:
        for folder in ("app", "static"):
            for path in sorted((root / folder).rglob("*")):
                if path.is_file() and "__pycache__" not in path.parts:
                    tar.add(path, arcname=str(path.relative_to(root)))
        tar.add(root / "requirements.txt", arcname="requirements.txt")
    bootstrap = "import os,base64,tarfile,io;os.makedirs('/opt/ugc',exist_ok=True);tarfile.open(fileobj=io.BytesIO(base64.b64decode(os.environ['UGC_TEST_SOURCE']))).extractall('/opt/ugc')"
    import shlex
    command = "python -c " + shlex.quote(bootstrap) + " && cd /opt/ugc && apt-get update -qq && apt-get install -y -qq ffmpeg && pip install --no-cache-dir -q -r requirements.txt && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"
    return {"docker_args": json.dumps("bash -lc " + shlex.quote(command))[1:-1]}, {
        "UGC_TEST_SOURCE": base64.b64encode(archive.getvalue()).decode(),
        "UGC_RENDERER_MODE": "mock", "IDLE_TIMEOUT_SECONDS": "75", "HF_TOKEN": "",
    }
