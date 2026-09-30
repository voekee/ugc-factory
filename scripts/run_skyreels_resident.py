"""Pinned SkyReels Reference2Video, resident BF16, official eight-step recipe.

Importing this module does not import CUDA dependencies or download weights.
The container must prepare the isolated runtime before a paid session starts.
"""
import json
import os
import sys
import time
from pathlib import Path

CODE_REVISION = '28c771e8456341be6a213e3d1133ed1fd19bf75d'
MODEL_ID = 'Skywork/SkyReels-V3-Reference2Video'
MODEL_REVISION = '8df04fa97e062099633b366d19a6b0b2dabd5a69'
RUNTIME_FILE = Path('/opt/skyreels-runtime.json')


def runtime_ready():
    try:
        info = json.loads(RUNTIME_FILE.read_text())
        return (info.get('code_revision') == CODE_REVISION and
                info.get('model_revision') == MODEL_REVISION and
                Path('/opt/skyreels-venv/bin/python').is_file())
    except (OSError, ValueError):
        return False


def validate_request(req):
    paths = [req.get('start_frame')] + req.get('reference_frames', [])
    if not paths[0] or not 1 <= len(paths) <= 4 or not all(paths):
        raise ValueError('SkyReels needs one to four reference images')
    if int(req['duration']) != 5:
        raise ValueError('SkyReels supports five-second clips in this preset')
    return paths


def load_pipeline():
    if not runtime_ready():
        raise RuntimeError('SkyReels runtime must be prepared before starting a GPU')
    import torch
    from huggingface_hub import snapshot_download
    from skyreels_v3.pipelines import ReferenceToVideoPipeline
    if not torch.cuda.is_available():
        raise RuntimeError('SkyReels needs a CUDA GPU')
    memory = torch.cuda.get_device_properties(0).total_memory / 2**30
    if memory < 75:
        raise RuntimeError('Choose an 80 GB or larger GPU for the SkyReels quality preset')
    started = time.monotonic()
    print('[SKYREELS] Downloading or checking pinned model files', flush=True)
    root = Path(os.environ.get('MODEL_ROOT', '/workspace/models')) / 'SkyReels-V3-Reference2Video'
    snapshot_download(MODEL_ID, revision=MODEL_REVISION, local_dir=root,
                      allow_patterns=['model_index.json', 'scheduler/*', 'tokenizer/*',
                                      'text_encoder/*', 'transformer/*', 'vae/*'])
    downloaded = time.monotonic()
    print('[SKYREELS] Loading resident BF16 reference model; no weight quantization', flush=True)
    pipe = ReferenceToVideoPipeline(str(root), offload=memory < 90, low_vram=False)
    print('[SKYREELS] Load timings '+json.dumps({
        'download_seconds': round(downloaded-started, 2),
        'load_seconds': round(time.monotonic()-downloaded, 2)}), flush=True)
    return pipe


def generate(pipe, req):
    import torch
    import imageio
    from PIL import Image
    paths = validate_request(req)
    images = []
    for path in paths:
        with Image.open(path) as source:
            images.append(source.convert('RGB'))
    started = time.monotonic()
    torch.cuda.reset_peak_memory_stats()
    print(f'[SKYREELS] Generating with {len(images)} references; 8 official steps; 720p; 24 FPS', flush=True)
    frames = pipe.generate_video(images, req['prompt'], 5, int(req['seed']), resolution='720P')
    torch.cuda.synchronize()
    generated = time.monotonic()
    imageio.mimwrite(req['output'], frames, fps=24, quality=8,
                     codec='libx264', pixelformat='yuv420p',
                     output_params=['-movflags', '+faststart', '-loglevel', 'error'])
    print('[SKYREELS] Timings '+json.dumps({
        'inference_seconds': round(generated-started, 2),
        'encode_seconds': round(time.monotonic()-generated, 2),
        'total_seconds': round(time.monotonic()-started, 2),
        'peak_gpu_memory_gb': round(torch.cuda.max_memory_allocated()/2**30, 2)}), flush=True)


def main():
    if '--resident' not in sys.argv:
        req = {'job_id': os.environ['UGC_JOB_ID'], 'prompt': os.environ['UGC_PROMPT'],
               'start_frame': os.environ['UGC_START_FRAME'], 'duration': os.environ['UGC_DURATION'],
               'seed': os.environ['UGC_SEED'], 'output': os.environ['UGC_OUTPUT'],
               'reference_frames': json.loads(os.environ.get('UGC_REFERENCE_FRAMES', '[]'))}
        validate_request(req)
        generate(load_pipeline(), req)
        return
    pipe = None
    for line in sys.stdin:
        req = json.loads(line)
        try:
            validate_request(req)
            if pipe is None:
                pipe = load_pipeline()
            else:
                print('[SKYREELS] Reusing loaded model; no download or model reload', flush=True)
            generate(pipe, req)
            result = {'job_id': req['job_id'], 'ok': True}
        except Exception as exc:
            import traceback
            traceback.print_exc()
            message = ('GPU memory was insufficient. End this session and choose a larger GPU.'
                       if 'out of memory' in str(exc).lower() else
                       'SkyReels generation failed. The engine will reset; you can retry.')
            result = {'job_id': req.get('job_id'), 'ok': False, 'error': message}
        print('@@SKYREELS_RESULT@@'+json.dumps(result), flush=True)
        if not result['ok']:
            return


if __name__ == '__main__':
    main()
