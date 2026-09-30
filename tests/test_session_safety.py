from __future__ import annotations
import io
import json
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock
import pytest
from PIL import Image
from app import db
from app.assets import store_image, validate_pair
from app.config import settings
from app.h3 import gate_reason
from app.renderers.base import RenderRequest
from app.renderers.h3 import build_payload
from app.watchdog import watchdog_tick
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "launcher"))
import guardian
import onboarding


@pytest.fixture
def database(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    db.init_db()
    return tmp_path


def job(**changes):
    return {"id": uuid.uuid4().hex, "batch_id": "batch", "owner": "test", "renderer": "ltx25",
            "prompt": "open package", "duration": 4, "seed": 1,
            "start_frame": None, "end_frame": None, "status": "queued", **changes}


def test_batch_is_atomic_and_shutdown_blocks_submissions(database):
    item = job()
    with pytest.raises(Exception):
        db.create_jobs([item, item])
    assert db.list_jobs() == []
    db.create_jobs([job() for _ in range(20)])
    db.begin_shutdown()
    with pytest.raises(ValueError, match="ending"):
        db.create_job(job())
    assert len(db.list_jobs()) == 20


def test_parallel_claims_are_unique_and_end_drains(database):
    db.create_jobs([job() for _ in range(20)])
    db.begin_shutdown()
    with ThreadPoolExecutor(max_workers=8) as pool:
        claims = list(pool.map(lambda _: db.next_queued_job(), range(30)))
    ids = [c["id"] for c in claims if c]
    assert len(ids) == len(set(ids)) == 20
    assert db.job_counts() == {"rendering": 20}


def test_cancel_cannot_override_claim(database):
    item = job()
    db.create_job(item)
    db.next_queued_job()
    assert not db.cancel_queued_job(item["id"])
    assert db.get_job(item["id"])["status"] == "rendering"


def test_restart_requires_explicit_retry(database):
    item = job()
    db.create_job(item)
    db.next_queued_job()
    db.recover_interrupted_jobs()
    assert db.get_job(item["id"])["status"] == "failed"
    assert db.retry_job(item["id"])
    assert db.get_job(item["id"])["retry_count"] == 1
    assert not db.retry_job(item["id"])


def png(size=(96,128)):
    data=io.BytesIO()
    Image.new("RGB",size,"red").save(data,"PNG")
    return data.getvalue()


def test_assets_validate_cache_and_preserve_canvas(database):
    start = store_image(png())
    assert store_image(png()) == start
    end = store_image(png((192,256)))
    validate_pair(start,end)
    with pytest.raises(ValueError, match="aspect"):
        validate_pair(start,store_image(png((128,96))))
    with pytest.raises(ValueError, match="Invalid"):
        store_image(b"not-an-image")
    with Image.open(start) as image:
        assert image.size == (96,128)


@pytest.mark.parametrize("start,end,task,indices", [(None,None,"t2va",[]),("first.png",None,"fl2va",[0]),(None,"last.png","fl2va",[-1]),("first.png","last.png","fl2va",[0,-1])])
def test_h3_native_frame_contract(start,end,task,indices):
    req = RenderRequest("id","prompt",5,42,Path(start) if start else None,Path(end) if end else None,Path("out.mp4"))
    payload=build_payload(req)
    assert payload["task"] == task
    assert [c["frame_index"] for c in payload["conditions"]] == indices
    assert all(c["role"]=="keyframe" for c in payload["conditions"])
    if start and end:
        assert payload["conditions"][0]["uri"] != payload["conditions"][1]["uri"]


def test_license_fails_closed(monkeypatch):
    monkeypatch.setattr(settings,"h3_enabled",True)
    monkeypatch.setattr(settings,"h3_license_authorized",True)
    monkeypatch.setattr(settings,"h3_license_mode","community")
    monkeypatch.setattr(settings,"h3_allowed_region","DE")
    monkeypatch.setattr(settings,"h3_operator_region","DE")
    assert "excludes" in gate_reason()
    monkeypatch.setattr(settings,"h3_license_mode","authorized")
    assert "written" in gate_reason()
    monkeypatch.setattr(settings,"h3_authorization_reference","test-fixture-only")
    assert gate_reason() is None
    monkeypatch.setattr(settings,"h3_enabled",False)
    assert "authorization" in gate_reason()


def test_termination_is_verified_not_assumed(monkeypatch):
    monkeypatch.setattr(guardian.runpod,"get_pods",Mock(return_value=[{"id":"pod"}]))
    terminate=Mock()
    monkeypatch.setattr(guardian.runpod,"terminate_pod",terminate)
    with pytest.raises(RuntimeError,match="not verified"):
        guardian.terminate_verified("test-key","pod",pause=0)
    assert terminate.call_count==3
    monkeypatch.setattr(guardian.runpod,"get_pods",Mock(side_effect=[[{"id":"pod"}],[]]))
    guardian.terminate_verified("test-key","pod",pause=0)


def test_launcher_keeps_session_after_failed_termination(tmp_path,monkeypatch):
    monkeypatch.setattr(onboarding,"CONFIG_DIR",tmp_path)
    monkeypatch.setattr(onboarding,"CONFIG_PATH",tmp_path/"config.json")
    onboarding._write_config({"runpod_api_key":"secret","active_session":{"pod_id":"pod"}})
    monkeypatch.setattr(onboarding,"archive_outputs",Mock(return_value={}))
    monkeypatch.setattr(onboarding,"terminate_verified",Mock(side_effect=RuntimeError("not verified")))
    with pytest.raises(RuntimeError):
        onboarding._terminate_active_session()
    assert onboarding._read_config()["active_session"]["pod_id"]=="pod"
    assert "secret" not in json.dumps(onboarding._public_config())
    assert (tmp_path/"config.json").stat().st_mode & 0o777 == 0o600


def test_idle_watchdog_and_active_render_protection(database,monkeypatch):
    monkeypatch.setattr(settings,"ugc_renderer_mode","real")
    monkeypatch.setattr(settings,"runpod_api_key","test-key")
    monkeypatch.setattr(settings,"runpod_pod_id","pod")
    monkeypatch.setattr(settings,"session_started_at",datetime.now(timezone.utc).isoformat())
    monkeypatch.setattr(settings,"max_session_hours",6)
    monkeypatch.setattr(guardian.runpod,"terminate_pod",Mock())
    db.set_kv("idle_since",(datetime.now(timezone.utc)-timedelta(minutes=11)).isoformat())
    db.create_job(job())
    watchdog_tick()
    guardian.runpod.terminate_pod.assert_not_called()
    with db.connect() as con:
        con.execute("UPDATE jobs SET status='complete', downloaded=1")
    db.set_kv("idle_since",(datetime.now(timezone.utc)-timedelta(minutes=11)).isoformat())
    watchdog_tick()
    guardian.runpod.terminate_pod.assert_called_once_with("pod")
    assert db.get_kv("session_state")=="ending"


def test_guardian_drains_and_verifies_shutdown(tmp_path,monkeypatch):
    now=datetime.now(timezone.utc)
    config={"runpod_api_key":"test", "active_session":{"pod_id":"pod","started_at":now.isoformat(),"hours":6,"state":"ending"}}
    monkeypatch.setattr(guardian.runpod,"get_pods",Mock(return_value=[{"id":"pod"}]))
    monkeypatch.setattr(guardian,"archive_outputs",Mock(return_value={}))
    monkeypatch.setattr(guardian,"worker_json",Mock(return_value={"active_jobs":0}))
    terminate=Mock()
    monkeypatch.setattr(guardian,"terminate_verified",terminate)
    writes=[]
    g=guardian.Guardian(lambda:config,lambda c:writes.append(json.loads(json.dumps(c))),tmp_path)
    g.tick()
    terminate.assert_called_once_with("test","pod")
    assert "active_session" not in writes[-1]
    assert writes[-1]["session_history"][-1]["termination_verified"]


def test_guardian_does_not_close_on_archive_failure(tmp_path,monkeypatch):
    config={"runpod_api_key":"test", "active_session":{"pod_id":"pod","started_at":datetime.now(timezone.utc).isoformat(),"hours":6,"state":"ending"}}
    monkeypatch.setattr(guardian.runpod,"get_pods",Mock(return_value=[{"id":"pod"}]))
    monkeypatch.setattr(guardian,"archive_outputs",Mock(side_effect=OSError("disk full")))
    terminate=Mock()
    monkeypatch.setattr(guardian,"terminate_verified",terminate)
    guardian.Guardian(lambda:config,lambda _:None,tmp_path).tick()
    terminate.assert_not_called()
    assert config["active_session"]["archive_error"]


def test_h3_http_adapter_downloads_and_persists_engine_id(database,monkeypatch):
    import httpx
    import app.renderers.h3 as h3
    item=job(renderer="h3-fl2va")
    db.create_job(item)
    seen=[]
    def handler(request):
        seen.append(request)
        if request.method=="POST":
            assert [c["frame_index"] for c in json.loads(request.content)["conditions"]]==[0,-1]
            return httpx.Response(200,json={"id":"engine-job"})
        if request.url.path.endswith("/content"):
            return httpx.Response(200,content=b"test-video"*200)
        return httpx.Response(200,json={"status":"completed"})
    client=httpx.Client(base_url="http://127.0.0.1:30010",transport=httpx.MockTransport(handler))
    monkeypatch.setattr(h3,"require_h3",lambda:None)
    monkeypatch.setattr(h3.httpx,"Client",lambda **_:client)
    out=database/"video.mp4"
    h3.H3Renderer().render(RenderRequest(item["id"],"open box",5,1,database/"start.png",database/"end.png",out))
    assert out.stat().st_size==2000
    assert db.get_job(item["id"])["engine_job_id"]=="engine-job"
    assert len(seen)==3


def test_h3_launch_gates_before_spending(monkeypatch):
    import runpod_launcher
    create=Mock()
    monkeypatch.setattr(runpod_launcher.runpod,"create_pod",create)
    monkeypatch.setattr(settings,"h3_enabled",False)
    with pytest.raises(ValueError,match="authorization"):
        runpod_launcher.launch_pod(api_key="test",image="test:h3",model="h3-fl2va")
    create.assert_not_called()


def test_h3_launch_uses_profile_and_persistent_weights(monkeypatch):
    import runpod_launcher
    for name,value in {"h3_enabled":True,"h3_license_authorized":True,"h3_license_mode":"authorized",
        "h3_authorization_reference":"test-only", "h3_allowed_region":"DE","h3_operator_region":"DE",
        "h3_network_volume_id":"volume", "h3_data_center_id":"EU-DE-1","h3_profile":"h100-4",
        "h3_worker_image":"ghcr.io/test/h3@sha256:"+"a"*64}.items():
        monkeypatch.setattr(settings,name,value)
    create=Mock(return_value={"id":"pod"})
    monkeypatch.setattr(runpod_launcher.runpod,"create_pod",create)
    journal=Mock()
    result=runpod_launcher.launch_pod(api_key="test",image="test:h3",model="h3-fl2va",on_creating=journal)
    assert result["gpu_count"]==4
    assert create.call_args.kwargs["network_volume_id"]=="volume"
    assert create.call_args.kwargs["country_code"]=="DE"
    assert create.call_args.kwargs["image_name"] == settings.h3_worker_image
    assert create.call_args.kwargs["env"]["H3_LICENSE_MODE"]=="authorized"
    assert journal.call_count==1


def test_lost_allocation_reply_never_creates_second_pod(monkeypatch):
    import runpod_launcher
    create=Mock(side_effect=TimeoutError("lost reply"))
    monkeypatch.setattr(runpod_launcher.runpod,"create_pod",create)
    with pytest.raises(TimeoutError):
        runpod_launcher.launch_pod(api_key="test",image="test:legacy")
    assert create.call_count==1


def test_closed_session_orphan_gets_reterminated(tmp_path,monkeypatch):
    config={"runpod_api_key":"test", "session_history":[{"pod_id":"pod","state":"terminated"}]}
    monkeypatch.setattr(guardian.runpod,"get_pods",Mock(return_value=[{"id":"pod","name":"ugc-factory-old"}]))
    terminate=Mock()
    monkeypatch.setattr(guardian,"terminate_verified",terminate)
    guardian.Guardian(lambda:config,lambda _:None,tmp_path).tick()
    terminate.assert_called_once_with("test","pod")


def test_ambiguous_creation_is_recovered_by_exact_name(tmp_path,monkeypatch):
    config={"runpod_api_key":"test", "pending_creation":{"session_name":"ugc-factory-exact"}}
    monkeypatch.setattr(guardian.runpod,"get_pods",Mock(return_value=[{"id":"pod","name":"ugc-factory-exact"}]))
    terminate=Mock()
    monkeypatch.setattr(guardian,"terminate_verified",terminate)
    guardian.Guardian(lambda:config,lambda _:None,tmp_path).tick()
    assert terminate.call_args.args==("test","pod")
    assert "pending_creation" not in config


def test_hard_cap_retries_despite_backup_failure(tmp_path,monkeypatch):
    config={"runpod_api_key":"test", "active_session":{"pod_id":"pod","started_at":(datetime.now(timezone.utc)-timedelta(hours=3)).isoformat(),"hours":1}}
    monkeypatch.setattr(guardian.runpod,"get_pods",Mock(return_value=[{"id":"pod"}]))
    monkeypatch.setattr(guardian,"archive_outputs",Mock(side_effect=OSError("network unavailable")))
    terminate=Mock(side_effect=RuntimeError("not verified"))
    monkeypatch.setattr(guardian,"terminate_verified",terminate)
    g=guardian.Guardian(lambda:config,lambda _:None,tmp_path)
    with pytest.raises(RuntimeError):g.tick()
    with pytest.raises(RuntimeError):g.tick()
    assert terminate.call_count==2
    assert config["active_session"]["state"]=="ending_now"


def test_archive_is_incremental_and_acknowledges_after_persistence(tmp_path,monkeypatch):
    item=job(status="complete")
    calls=[]
    def worker(session,path,method="GET"):
        calls.append((path,method))
        if path.startswith('/api/jobs?'):return {"jobs":[item]}
        assert (tmp_path/'pod'/f'{item["id"]}.mp4').exists()
        assert (tmp_path/'pod'/f'{item["id"]}.json').exists()
        return {"ok":True}
    monkeypatch.setattr(guardian,"worker_json",worker)
    download=Mock(side_effect=lambda *_,**__:io.BytesIO(b'video'*500))
    monkeypatch.setattr(guardian.urllib.request,"urlopen",download)
    session={"pod_id":"pod","session_token":"test"}
    guardian.archive_outputs(session,tmp_path)
    guardian.archive_outputs(session,tmp_path)
    assert download.call_count==1
    assert len([c for c in calls if c[1]=='POST'])==1


def test_archive_failure_never_acknowledges(tmp_path,monkeypatch):
    item=job(status="complete")
    request=Mock(return_value={"jobs":[item]})
    monkeypatch.setattr(guardian,"worker_json",request)
    monkeypatch.setattr(guardian.urllib.request,"urlopen",Mock(return_value=io.BytesIO(b'bad')))
    with pytest.raises(ValueError):guardian.archive_outputs({"pod_id":"pod","session_token":"test"},tmp_path)
    assert request.call_count==1
    assert not list(tmp_path.rglob('*.mp4'))
    assert not list(tmp_path.rglob('*.part'))


def test_launcher_does_not_infer_readiness_from_uptime(monkeypatch):
    session={"pod_id":"pod","dashboard_url":"https://pod-8000.proxy.runpod.net","started_at":datetime.now(timezone.utc).isoformat()}
    monkeypatch.setattr(onboarding,"_recover_active_session",lambda:session)
    monkeypatch.setattr(onboarding,"_probe_workspace",lambda _:False)
    monkeypatch.setattr(onboarding,"_read_config",lambda:{})
    monkeypatch.setattr(onboarding,"_progress_snapshot",lambda *args:{"runtime_reported":True,"container_uptime_seconds":999})
    assert not onboarding._session_status_payload()["ready"]


def test_unknown_rate_is_not_free(database,monkeypatch):
    from app.metrics import snapshot
    monkeypatch.setattr(settings,"session_hourly_rate_usd",0)
    assert snapshot()["estimated_session_cost_usd"] is None
    assert snapshot()["estimated_cost_per_completed_clip_usd"] is None


def test_h3_license_no_mock_bypass(monkeypatch):
    from app.renderers import get_renderer
    monkeypatch.setattr(settings,"h3_enabled",False)
    monkeypatch.setattr(settings,"ugc_renderer_mode","mock")
    with pytest.raises(ValueError,match="authorization"):get_renderer("h3-fl2va")


def test_command_timeout_does_not_hang_queue(database,monkeypatch):
    import shlex
    from app.renderers.command import CommandRenderer
    monkeypatch.setattr(settings,"render_timeout_seconds",1)
    cmd=f'{shlex.quote(sys.executable)} -c "import time; time.sleep(30)"'
    with pytest.raises(TimeoutError):
        CommandRenderer("test",cmd).render(RenderRequest("test","p",4,1,None,None,database/"out.mp4"))


def test_h3_connection_failure_blocks_ambiguous_replay(database,monkeypatch):
    import httpx
    import app.renderers.h3 as h3
    item=job(renderer="h3-fl2va")
    db.create_job(item)
    def handler(request):raise httpx.ReadTimeout("lost submit reply",request=request)
    client=httpx.Client(base_url="http://127.0.0.1:30010",transport=httpx.MockTransport(handler))
    monkeypatch.setattr(h3,"require_h3",lambda:None)
    monkeypatch.setattr(h3.httpx,"Client",lambda **_:client)
    with pytest.raises(httpx.ReadTimeout):
        h3.H3Renderer().render(RenderRequest(item["id"],"open box",5,1,None,None,database/"video.mp4"))
    assert db.get_kv("worker_blocked")


def test_dev_payload_is_opt_in_and_contains_no_weights(monkeypatch):
    import base64, tarfile
    import lifecycle_test
    monkeypatch.delenv('UGC_LIFECYCLE_TEST', raising=False)
    with pytest.raises(ValueError): lifecycle_test.pod_options()
    monkeypatch.setenv('UGC_LIFECYCLE_TEST', '1')
    options, env = lifecycle_test.pod_options()
    # RunPod SDK interpolates this inside a GraphQL string without escaping.
    command = json.loads('"' + options['docker_args'] + '"')
    assert command.startswith('bash -lc ')
    assert env['UGC_RENDERER_MODE'] == 'mock'
    assert env['IDLE_TIMEOUT_SECONDS'] == '75'
    assert env['HF_TOKEN'] == ''
    with tarfile.open(fileobj=io.BytesIO(base64.b64decode(env['UGC_TEST_SOURCE']))) as tar:
        names = tar.getnames()
    assert 'app/main.py' in names and 'static/index.html' in names
    assert not any('.env' in n or 'safetensors' in n or '__pycache__' in n for n in names)


def test_worker_proxy_headers_preserve_auth():
    request = guardian.worker_request({'pod_id':'validpod','session_token':'test-token'}, '/api/session')
    assert request.get_header('X-access-token') == 'test-token'
    assert 'AppleWebKit/605.1.15' in request.get_header('User-agent')
    assert request.full_url == 'https://validpod-8000.proxy.runpod.net/api/session'


def test_http_duplicate_launch_gate_and_startup_end(tmp_path, monkeypatch):
    import threading, urllib.request, urllib.error, time
    monkeypatch.setattr(onboarding, 'CONFIG_PATH', tmp_path/'config.json')
    monkeypatch.setattr(onboarding, 'CONFIG_DIR', tmp_path)
    monkeypatch.setattr(onboarding, 'STATE', {'launching':False, 'pod_id':'', 'error':''})
    monkeypatch.setattr(onboarding, 'lifecycle_test_enabled', lambda:False)
    monkeypatch.setattr(settings, 'h3_enabled', False)
    onboarding._write_config({'runpod_api_key':'fake','hf_token':'fake'})
    monkeypatch.setattr(onboarding,'_validate_hf_token',lambda _:None)
    live=[]
    monkeypatch.setattr(onboarding.runpod, 'get_pods', lambda **_:list(live))
    monkeypatch.setattr(onboarding, '_discover_gpu_offers', lambda _:[{'gpu_id':'testgpu','cloud':'COMMUNITY','price_per_hour':0.1,'vram_gb':24}])
    monkeypatch.setattr(onboarding, '_check_container_image_pullable', lambda _:None)
    def create(**kwargs):
        kwargs['on_creating']({'session_name':'ugc-factory-test'})
        time.sleep(0.05)
        live.append({'id':'one','name':'ugc-factory-test'})
        return {'pod_id':'one','session_name':'ugc-factory-test','access_token':'test','dashboard_url':'https://one.example','workspace_url':'https://one.example'}
    allocate=Mock(side_effect=create)
    monkeypatch.setattr(onboarding,'launch_pod',allocate)
    monkeypatch.setattr(onboarding,'_probe_workspace',lambda _:False)
    monkeypatch.setattr(onboarding,'archive_outputs',Mock(side_effect=OSError('not ready')))
    terminate=Mock(side_effect=lambda *args:live.clear())
    monkeypatch.setattr(onboarding,'terminate_verified',terminate)
    server=onboarding.ThreadingHTTPServer(('127.0.0.1',0),onboarding.Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    def post(path,payload):
        req=urllib.request.Request(f'http://127.0.0.1:{server.server_port}'+path,
            data=json.dumps(payload).encode(),headers={'X-Launcher-Token':onboarding.LOCAL_TOKEN,'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(req) as response:return response.status,json.load(response)
        except urllib.error.HTTPError as error:return error.code,json.load(error)
    payload={'gpu':'testgpu','cloud':'COMMUNITY','vram':24,'price':0.1,'hours':1,'disk':100}
    try:
        assert post('/api/launch',{**payload,'model':'h3-fl2va'})[0]==400
        assert post('/api/launch',{**payload,'model':'invalid'})[0]==400
        assert post('/api/launch',{**payload,'model':'wan22','vram':80,'disk':180})[0]==400
        assert allocate.call_count==0
        with ThreadPoolExecutor(max_workers=4) as pool:
            replies=list(pool.map(lambda _:post('/api/launch',payload),range(4)))
        assert sorted(r[0] for r in replies)==[200,409,409,409]
        assert allocate.call_count==1
        assert onboarding._read_config()['active_session']['idle_timeout_seconds']==600
        assert post('/api/end-active',{})[1]['termination_verified']
        assert post('/api/end-active',{})[1]['termination_verified']
        assert terminate.call_count==1
        assert 'active_session' not in onboarding._read_config()
    finally:
        server.shutdown();server.server_close();thread.join(timeout=2)


def test_ltx_command_uses_valid_two_stage_resolution(tmp_path, monkeypatch):
    import os, subprocess
    names=['diffusion_models/ltx-2.5-22b-distilled-transformer-bf16.safetensors',
           'text_encoders/gemma4-12b-with-proj-ltx-2.5-bf16.safetensors',
           'vae/ltx-2.5-video-vae-bf16.safetensors','vae/ltx-2.5-audio-vae-bf16.safetensors',
           'latent_upscale_models/ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors']
    for name in names:
        path=tmp_path/'models'/'LTX-2.5'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'fixture')
    bindir=tmp_path/'bin';bindir.mkdir()
    fake=bindir/'python'
    fake.write_text(f'#!{sys.executable}\nimport sys,json,os\nif "-m" in sys.argv: open(os.environ["CAPTURE"],"w").write(json.dumps(sys.argv))\n')
    fake.chmod(0o755)
    capture=tmp_path/'args.json'
    env={**os.environ,'PATH':str(bindir)+os.pathsep+os.environ['PATH'],'MODEL_ROOT':str(tmp_path/'models'),
         'UGC_OUTPUT':str(tmp_path/'out.mp4'),'UGC_PROMPT':'test','UGC_DURATION':'4','UGC_SEED':'1',
         'UGC_START_FRAME':'start.png','UGC_END_FRAME':'end.png','CAPTURE':str(capture)}
    subprocess.run(['bash','scripts/run_ltx.sh'],env=env,check=True,capture_output=True)
    args=json.loads(capture.read_text())
    assert int(args[args.index('--width')+1]) % 64 == 0
    assert int(args[args.index('--height')+1]) % 64 == 0
    assert args[args.index('--num-frames')+1]=='97'
    assert args[-4:]==['--image','end.png','96','1.0']


def test_real_legacy_launch_reserves_host_memory(monkeypatch):
    import runpod_launcher
    monkeypatch.delenv('UGC_LIFECYCLE_TEST',raising=False)
    create=Mock(return_value={'id':'fakepod'})
    monkeypatch.setattr(runpod_launcher.runpod,'create_pod',create)
    runpod_launcher.launch_pod(api_key='fake',image='fake',gpu='NVIDIA L40',cloud='COMMUNITY')
    assert create.call_args.kwargs['min_memory_in_gb']==128
    assert create.call_args.kwargs['min_vcpu_count']==8
    assert create.call_args.kwargs['env']['UGC_RENDERER_MODE']=='real'


def test_wan_launch_reserves_quality_resources(monkeypatch):
    import runpod_launcher
    monkeypatch.delenv('UGC_LIFECYCLE_TEST',raising=False)
    create=Mock(return_value={'id':'fakepod'})
    monkeypatch.setattr(runpod_launcher.runpod,'create_pod',create)
    runpod_launcher.launch_pod(api_key='fake',image='fake',gpu='NVIDIA H100 80GB HBM3',cloud='COMMUNITY',model='wan22')
    assert create.call_args.kwargs['min_memory_in_gb']==160
    assert create.call_args.kwargs['env']['SESSION_MODEL']=='wan22'
