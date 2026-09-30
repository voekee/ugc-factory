"""Exercise real subprocess reuse and recovery without CUDA/model downloads."""
import sys
from pathlib import Path

import pytest

from app.config import settings
from app.renderers.base import RenderRequest
from app.renderers.wan import WanRenderer


def setup_engine(tmp_path, monkeypatch, body):
    script = tmp_path / 'engine.py'
    script.write_text(body)
    monkeypatch.setattr(settings, 'wan_runner_cmd', f'{sys.executable} {script}')
    monkeypatch.setattr(settings, 'data_dir', tmp_path)
    monkeypatch.setattr(settings, 'render_timeout_seconds', 2)
    return WanRenderer()


def request(tmp_path, job='a'):
    return RenderRequest(job, 'product demo', 4, 123, tmp_path/'frame.png', None, tmp_path/f'{job}.mp4')


def test_two_jobs_reuse_one_process_and_isolate_logs(tmp_path, monkeypatch):
    engine = setup_engine(tmp_path, monkeypatch, '''import sys,json,os
from pathlib import Path
for line in sys.stdin:
 r=json.loads(line)
 print('job '+r['job_id'],flush=True)
 Path(r['output']).write_bytes(str(os.getpid()).encode().ljust(2048,b'x'))
 print('@@WAN_RESULT@@'+json.dumps({'job_id':r['job_id'],'ok':True}),flush=True)
''')
    try:
        engine.render(request(tmp_path, 'a'))
        engine.render(request(tmp_path, 'b'))
        assert (tmp_path/'a.mp4').read_bytes() == (tmp_path/'b.mp4').read_bytes()
        assert (tmp_path/'logs/a.log').read_text() == 'job a\n'
        assert (tmp_path/'logs/b.log').read_text() == 'job b\n'
    finally:
        engine.close()


@pytest.mark.parametrize('body, message', [
    ('import time; time.sleep(20)', 'timed out'),
    ("print('@@WAN_RESULT@@{\"job_id\":\"other\",\"ok\":true}',flush=True)", 'did not match'),
    ('raise SystemExit(1)', 'stopped unexpectedly'),
])
def test_bad_engine_is_killed_and_next_job_can_restart(tmp_path, monkeypatch, body, message):
    engine = setup_engine(tmp_path, monkeypatch, body)
    with pytest.raises((RuntimeError, TimeoutError), match=message):
        engine.render(request(tmp_path))
    assert engine._process is None
    assert not (tmp_path/'a.mp4').exists()
    script = tmp_path/'engine.py'
    script.write_text('''import sys,json
from pathlib import Path
for line in sys.stdin:
 r=json.loads(line)
 Path(r['output']).write_bytes(b'x'*2048)
 print('@@WAN_RESULT@@'+json.dumps({'job_id':r['job_id'],'ok':True}),flush=True)
''')
    try:
        engine.render(request(tmp_path, 'recovered'))
        assert (tmp_path/'recovered.mp4').stat().st_size == 2048
    finally:
        engine.close()
