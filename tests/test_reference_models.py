"""CPU contracts and safety checks; these tests are not real model inference."""
import io
import json
import sys
from pathlib import Path

import pytest
from PIL import Image
from fastapi.testclient import TestClient

from app import db
from app.config import settings
from app.main import app, _create_job_records, renderer_unavailable_reason
from app.renderers.base import RenderRequest
from app.renderers.skyreels import SkyReelsRenderer
from scripts.run_wan_diffusers import PromptCache
from scripts import run_skyreels_resident as sky


def test_sky_resident_loop_loads_once_and_preserves_references(monkeypatch, capsys):
    loaded, requests = [], []
    pipeline = object()
    monkeypatch.setattr(sky, 'load_pipeline', lambda: loaded.append(True) or pipeline)
    monkeypatch.setattr(sky, 'generate', lambda p, r: requests.append((p, r['reference_frames'])))
    monkeypatch.setattr(sys, 'argv', ['worker', '--resident'])
    monkeypatch.setattr(sys, 'stdin', io.StringIO(''.join(json.dumps({
        'job_id': str(i), 'start_frame': 'product.png', 'reference_frames': ['logo.png','door.png'],
        'duration': 5})+'\n' for i in range(2))))
    sky.main()
    assert loaded == [True]
    assert requests == [(pipeline, ['logo.png','door.png'])]*2
    assert capsys.readouterr().out.count('@@SKYREELS_RESULT@@') == 2


@pytest.mark.parametrize('references,duration', [(['a']*4,5), ([None],5), ([],4)])
def test_invalid_sky_inputs_never_load_model(monkeypatch, capsys, references, duration):
    def forbidden():
        pytest.fail('invalid input must not load/download weights')
    monkeypatch.setattr(sky, 'load_pipeline', forbidden)
    monkeypatch.setattr(sys, 'argv', ['worker','--resident'])
    monkeypatch.setattr(sys, 'stdin', io.StringIO(json.dumps({
        'job_id':'a','start_frame':'product.png','reference_frames':references,'duration':duration})+'\n'))
    sky.main()
    assert '"ok": false' in capsys.readouterr().out


def test_sky_subprocess_reuse_receives_four_exact_paths(tmp_path, monkeypatch):
    script = tmp_path/'sky.py'
    script.write_text('''import json,sys,os
from pathlib import Path
for line in sys.stdin:
 r=json.loads(line)
 Path(r['output']).write_bytes(json.dumps({'pid':os.getpid(),'refs':r['reference_frames']}).encode().ljust(2048,b' '))
 print('@@SKYREELS_RESULT@@'+json.dumps({'job_id':r['job_id'],'ok':True}),flush=True)
''')
    monkeypatch.setattr(settings, 'skyreels_runner_cmd', f'{sys.executable} {script}')
    monkeypatch.setattr(settings, 'data_dir', tmp_path)
    engine = SkyReelsRenderer()
    try:
        for job_id in ['a','b']:
            engine.render(RenderRequest(job_id, 'demo',5,42,tmp_path/'product.png',None,tmp_path/f'{job_id}.mp4',
                                        (tmp_path/'logo.png',tmp_path/'door.png',tmp_path/'hand.png')))
        a = json.loads((tmp_path/'a.mp4').read_bytes())
        b = json.loads((tmp_path/'b.mp4').read_bytes())
        assert a == b
        assert a['refs'] == [str(tmp_path/p) for p in ['logo.png','door.png','hand.png']]
    finally:
        engine.close()


def test_references_persist_and_non_reference_model_rejects_them(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, 'data_dir', tmp_path)
    monkeypatch.setattr(settings, 'ugc_renderer_mode', 'mock')
    monkeypatch.setattr(settings, 'session_model', 'legacy')
    db.init_db()
    paths = []
    for i in range(4):
        path=tmp_path/f'{i}.png';Image.new('RGB',(96,128)).save(path);paths.append(str(path))
    args=dict(owner='test', prompt='product demo',duration=5,variations=2,start_path=paths[0],end_path=None,
              reference_paths=paths[1:])
    result=_create_job_records(renderer='skyreelsv3',**args)
    assert len(result['job_ids']) == 2
    assert all(json.loads(db.get_job(job)['reference_frames']) == paths[1:] for job in result['job_ids'])
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as error:
        _create_job_records(renderer='wan22',**args)
    assert error.value.status_code == 400
    assert len(db.list_jobs()) == 2


def test_unprepared_sky_is_blocked_before_pod_allocation(monkeypatch):
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'launcher'))
    import runpod_launcher
    monkeypatch.setattr(runpod_launcher, 'SKYREELS_IMAGE', '')
    def forbidden(**kwargs):
        pytest.fail('no paid allocation may occur')
    monkeypatch.setattr(runpod_launcher.runpod, 'create_pod', forbidden)
    with pytest.raises(ValueError, match='prepared'):
        runpod_launcher._create_single_pod(api_key='test', image='unprepared:latest', gpu='test',
            cloud='COMMUNITY',hours=.5,disk=180,hf_token='',rate=1,model='skyreelsv3')
    monkeypatch.setattr(settings, 'ugc_renderer_mode', 'real')
    monkeypatch.setattr(settings, 'session_model', 'skyreelsv3')
    monkeypatch.setattr(sky, 'runtime_ready', lambda: False)
    assert 'not prepared' in renderer_unavailable_reason('skyreelsv3')
    assert renderer_unavailable_reason('wan22')


def test_prompt_cache_bounds_memory_and_preserves_exact_values():
    class Tensor:
        def __init__(self, value): self.value=value
        def detach(self): return self
        def cpu(self): return self
    calls=[]
    def encode(value):
        calls.append(value);return Tensor(value),None
    cache=PromptCache(capacity=2)
    first,hit=cache.get('a',lambda:encode(123))
    assert not hit and first[0].value == 123
    again,hit=cache.get('a',lambda:encode(999))
    assert hit and again is first and calls == [123]
    cache.get('b',lambda:encode(456))
    cache.get('a',lambda:encode(999))
    cache.get('c',lambda:encode(789))
    assert list(cache.values) == ['a','c']
    _,hit=cache.get('b',lambda:encode(456))
    assert not hit and len(cache.values) == 2
