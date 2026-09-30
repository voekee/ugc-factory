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
    duration = int(os.environ['UGC_DURATION'])
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
    pipe.enable_model_cpu_offload()
    pipe.vae.enable_tiling()
    image = ImageOps.fit(Image.open(os.environ['UGC_START_FRAME']).convert('RGB'), (720,1280), method=Image.Resampling.LANCZOS)
    negative = ('blurry face, waxy skin, plastic skin, distorted face, deformed hands, extra fingers, fused fingers, '
                'duplicate product, changing bottle shape, changing logo, flickering, jitter, sudden cuts, subtitles, watermark, cartoon, illustration')
    loaded = time.monotonic()
    print('[WAN] Generating 720p video: 4 trained Lightning steps, BF16, native attention', flush=True)
    frames = pipe(image=image, prompt=os.environ['UGC_PROMPT'], negative_prompt=negative,
                  width=720, height=1280, num_frames=duration*16+1,
                  num_inference_steps=4, guidance_scale=1.0, guidance_scale_2=1.0,
                  generator=torch.Generator(device='cpu').manual_seed(int(os.environ['UGC_SEED']))).frames[0]
    print('[WAN] Encoding video', flush=True)
    export_to_video(frames, os.environ['UGC_OUTPUT'], fps=16)
    print('[WAN] Timings '+json.dumps({'download_seconds':round(downloaded-started,2),
          'load_seconds':round(loaded-downloaded,2),'generate_encode_seconds':round(time.monotonic()-loaded,2),
          'total_seconds':round(time.monotonic()-started,2)}), flush=True)


if __name__ == '__main__':
    main()
