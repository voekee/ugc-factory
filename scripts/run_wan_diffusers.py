"""Pinned Wan 2.2 image-to-video, full BF16 weights and native SDPA attention."""
import json
import os
import time
from pathlib import Path

MODEL_ID = 'Wan-AI/Wan2.2-I2V-A14B-Diffusers'
REVISION = '596658fd9ca6b7b71d5057529bbf319ecbc61d74'


def main():
    import torch
    from PIL import Image, ImageOps
    from huggingface_hub import snapshot_download
    from diffusers import AutoencoderKLWan, WanImageToVideoPipeline
    from diffusers.utils import export_to_video

    started = time.monotonic()
    if not torch.cuda.is_available():
        raise RuntimeError('Wan requires a CUDA GPU')
    memory = torch.cuda.get_device_properties(0).total_memory / 2**30
    if memory < 75:
        raise RuntimeError('Wan quality preset needs an 80 GB or larger GPU; choose a suitable session')
    torch.backends.cuda.matmul.allow_tf32 = True
    duration = int(os.environ['UGC_DURATION'])
    root = Path(os.environ.get('MODEL_ROOT', '/workspace/models')) / 'Wan2.2-I2V-Diffusers'
    print('[WAN] Downloading or checking model files', flush=True)
    snapshot_download(MODEL_ID, revision=REVISION, local_dir=root,
                      allow_patterns=['model_index.json','scheduler/*','tokenizer/*','text_encoder/*','transformer/*','transformer_2/*','vae/*'])
    downloaded = time.monotonic()
    print('[WAN] Loading full-quality BF16 model', flush=True)
    vae = AutoencoderKLWan.from_pretrained(root, subfolder='vae', torch_dtype=torch.float32)
    pipe = WanImageToVideoPipeline.from_pretrained(root, vae=vae, torch_dtype=torch.bfloat16)
    pipe.enable_model_cpu_offload()
    pipe.vae.enable_tiling()
    image = ImageOps.fit(Image.open(os.environ['UGC_START_FRAME']).convert('RGB'), (720,1280), method=Image.Resampling.LANCZOS)
    negative = ('blurry face, waxy skin, plastic skin, distorted face, deformed hands, extra fingers, fused fingers, '
                'duplicate product, changing bottle shape, changing logo, flickering, jitter, sudden cuts, subtitles, watermark, cartoon, illustration')
    loaded = time.monotonic()
    print('[WAN] Generating 720p video: 40 steps, BF16, native attention', flush=True)
    frames = pipe(image=image, prompt=os.environ['UGC_PROMPT'], negative_prompt=negative,
                  width=720, height=1280, num_frames=duration*16+1,
                  num_inference_steps=40, guidance_scale=3.5, guidance_scale_2=3.5,
                  generator=torch.Generator(device='cpu').manual_seed(int(os.environ['UGC_SEED']))).frames[0]
    print('[WAN] Encoding video', flush=True)
    export_to_video(frames, os.environ['UGC_OUTPUT'], fps=16)
    print('[WAN] Timings '+json.dumps({'download_seconds':round(downloaded-started,2),
          'load_seconds':round(loaded-downloaded,2),'generate_encode_seconds':round(time.monotonic()-loaded,2),
          'total_seconds':round(time.monotonic()-started,2)}), flush=True)


if __name__ == '__main__':
    main()
