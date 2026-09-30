"""Pinned Wan 2.2 image-to-video, full BF16 weights and native SDPA attention."""
import json
import os
import time
import sys
from pathlib import Path
from collections import OrderedDict

MODEL_ID = 'Wan-AI/Wan2.2-I2V-A14B-Diffusers'
REVISION = '596658fd9ca6b7b71d5057529bbf319ecbc61d74'


class PromptCache:
    """Small CPU LRU; reuses exact embeddings, never a previous seed or latent."""
    def __init__(self, capacity=8):
        self.capacity = capacity
        self.values = OrderedDict()

    def get(self, key, encode):
        hit = key in self.values
        if not hit:
            # Detach from model state, retain exact dtype, bound CPU memory.
            self.values[key] = tuple(value.detach().cpu() if value is not None else None
                                     for value in encode())
            while len(self.values) > self.capacity:
                self.values.popitem(last=False)
        self.values.move_to_end(key)
        return self.values[key], hit


def load_pipeline():
    import torch
    from PIL import Image, ImageOps
    from huggingface_hub import snapshot_download, hf_hub_download
    from diffusers import AutoencoderKLWan, WanImageToVideoPipeline, FlowMatchEulerDiscreteScheduler
    from diffusers.utils import export_to_video

    started = time.monotonic()
    if not torch.cuda.is_available():
        raise RuntimeError('Wan requires a CUDA GPU')
    memory = torch.cuda.get_device_properties(0).total_memory / 2**30
    if memory < 75:
        raise RuntimeError('Wan quality preset needs an 80 GB or larger GPU; choose a suitable session')
    torch.backends.cuda.matmul.allow_tf32 = True
    root = Path(os.environ.get('MODEL_ROOT', '/workspace/models')) / 'Wan2.2-I2V-Diffusers'
    print('[WAN] Downloading or checking model files', flush=True)
    snapshot_download(MODEL_ID, revision=REVISION, local_dir=root,
                      allow_patterns=['model_index.json','scheduler/*','tokenizer/*','text_encoder/*','transformer/*','transformer_2/*','vae/*'])
    downloaded = time.monotonic()
    print('[WAN] Loading full-quality BF16 model', flush=True)
    vae = AutoencoderKLWan.from_pretrained(root, subfolder='vae', torch_dtype=torch.float32)
    pipe = WanImageToVideoPipeline.from_pretrained(root, vae=vae, torch_dtype=torch.bfloat16)
    # Match the publisher's Euler/simple, shift-5, 2-high/2-low four-step recipe.
    class LightningScheduler(FlowMatchEulerDiscreteScheduler):
        def set_timesteps(self, num_inference_steps=None, device=None, **kwargs):
            if num_inference_steps != 4:
                raise ValueError('Wan Lightning requires its trained four-step schedule')
            return super().set_timesteps(4, device=device, sigmas=[1.0, 0.75, 0.5, 0.25])
    pipe.scheduler = LightningScheduler(num_train_timesteps=1000, shift=5.0)
    print('[WAN] Loading trained Lightning adapters', flush=True)
    for stage, name in [('high', 'high_noise_model.safetensors'), ('low', 'low_noise_model.safetensors')]:
        lora = hf_hub_download('lightx2v/Wan2.2-Lightning',
            'Wan2.2-I2V-A14B-4steps-lora-rank64-Seko-V1/'+name,
            revision='18bccf8884ec0a078eed79785eb4ef13ea16ce1e', local_dir=root/'lightning')
        pipe.load_lora_weights(lora, adapter_name=stage, load_into_transformer_2=stage=='low')
        pipe.fuse_lora(components=['transformer_2' if stage=='low' else 'transformer'], adapter_names=[stage], lora_scale=1.0)
    pipe.unload_lora_weights()
    # Both BF16 experts fit on 96 GB GPUs. Smaller supported GPUs retain offload.
    mode = os.environ.get('WAN_MEMORY_MODE', 'auto')
    if mode not in {'auto', 'gpu', 'offload'}:
        raise ValueError('WAN_MEMORY_MODE must be auto, gpu, or offload')
    if mode == 'gpu' or (mode == 'auto' and memory >= 90):
        print('[WAN] Keeping both BF16 experts on GPU between videos', flush=True)
        pipe.to('cuda')
    else:
        print('[WAN] Keeping model resident in RAM with GPU offload', flush=True)
        pipe.enable_model_cpu_offload()
    pipe.vae.enable_tiling()
    loaded = time.monotonic()
    print('[WAN] Load timings '+json.dumps({'download_seconds': round(downloaded-started,2),
          'load_seconds': round(loaded-downloaded,2)}), flush=True)
    return pipe


def generate(pipe, req):
    import torch
    from PIL import Image, ImageOps
    from diffusers.utils import export_to_video
    started = time.monotonic()
    torch.cuda.reset_peak_memory_stats()
    with Image.open(req['start_frame']) as source:
        image = ImageOps.fit(source.convert('RGB'), (720,1280), method=Image.Resampling.LANCZOS)
    negative = ('blurry face, waxy skin, plastic skin, distorted face, deformed hands, extra fingers, fused fingers, '
                'duplicate product, changing bottle shape, changing logo, flickering, jitter, sudden cuts, subtitles, watermark, cartoon, illustration')
    print('[WAN] Generating 720p video: 4 trained Lightning steps, BF16, native attention', flush=True)
    prompt_args = {'prompt': req['prompt'], 'negative_prompt': negative}
    cache_hit = False
    if os.environ.get('WAN_PROMPT_CACHE', '1') == '1':
        if not hasattr(pipe, '_ugc_prompt_cache'):
            pipe._ugc_prompt_cache = PromptCache()
        device = pipe._execution_device
        with torch.inference_mode():
            embeddings, cache_hit = pipe._ugc_prompt_cache.get((req['prompt'], negative), lambda:
                pipe.encode_prompt(prompt=req['prompt'], negative_prompt=negative,
                    do_classifier_free_guidance=False, num_videos_per_prompt=1,
                    max_sequence_length=512, device=device))
        prompt_args = {'prompt_embeds': embeddings[0].to(device),
                       'negative_prompt_embeds': embeddings[1].to(device) if embeddings[1] is not None else None}
        print('[WAN] Prompt embeddings '+('reused' if cache_hit else 'encoded and cached'), flush=True)
    torch.cuda.synchronize()
    prompted = time.monotonic()
    frames = pipe(image=image, **prompt_args,
                  width=720, height=1280, num_frames=int(req['duration'])*16+1,
                  num_inference_steps=4, guidance_scale=1.0, guidance_scale_2=1.0,
                  generator=torch.Generator(device='cpu').manual_seed(int(req['seed']))).frames[0]
    torch.cuda.synchronize()
    generated = time.monotonic()
    print('[WAN] Encoding video', flush=True)
    export_to_video(frames, req['output'], fps=16)
    print('[WAN] Timings '+json.dumps({'inference_seconds':round(generated-started,2),
          'prompt_seconds':round(prompted-started,2), 'prompt_cache_hit':cache_hit,
          'encode_seconds':round(time.monotonic()-generated,2),
          'total_seconds':round(time.monotonic()-started,2),
          'peak_gpu_memory_gb':round(torch.cuda.max_memory_allocated()/2**30,2)}), flush=True)


def main():
    if '--resident' not in sys.argv:
        generate(load_pipeline(), {'prompt':os.environ['UGC_PROMPT'],
            'start_frame':os.environ['UGC_START_FRAME'], 'duration':os.environ['UGC_DURATION'],
            'seed':os.environ['UGC_SEED'], 'output':os.environ['UGC_OUTPUT']})
        return
    pipe = None
    for line in sys.stdin:
        req = json.loads(line)
        try:
            if not req.get('start_frame'):
                raise ValueError('Wan needs a Start Frame')
            if int(req['duration']) not in range(4, 11):
                raise ValueError('Wan supports clips from 4 to 10 seconds')
            if pipe is None:
                pipe = load_pipeline()
            else:
                print('[WAN] Reusing loaded model; no download or adapter merge', flush=True)
            generate(pipe, req)
            result = {'job_id':req['job_id'], 'ok':True}
        except Exception as exc:
            import traceback
            traceback.print_exc()
            message = ('GPU memory was insufficient. End this session and choose a larger GPU.'
                       if 'out of memory' in str(exc).lower() else
                       'Video generation failed. The model process will reset; you can retry.')
            result = {'job_id':req.get('job_id'), 'ok':False, 'error':message}
        print('@@WAN_RESULT@@'+json.dumps(result), flush=True)
        if not result['ok']:
            return


if __name__ == '__main__':
    main()
