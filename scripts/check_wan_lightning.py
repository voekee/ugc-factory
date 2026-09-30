"""CPU build check against real adapter tensors and a metadata-only Wan model."""
import gc
import json
import tempfile
from pathlib import Path
import torch
from huggingface_hub import hf_hub_download
from diffusers import WanTransformer3DModel, WanImageToVideoPipeline, FlowMatchEulerDiscreteScheduler

with tempfile.TemporaryDirectory() as root:
    config = hf_hub_download('Wan-AI/Wan2.2-I2V-A14B-Diffusers', 'transformer/config.json',
        revision='596658fd9ca6b7b71d5057529bbf319ecbc61d74', local_dir=root)
    with torch.device('meta'):
        model = WanTransformer3DModel.from_config(json.loads(Path(config).read_text()))
    for name in ['high_noise_model.safetensors', 'low_noise_model.safetensors']:
        path = hf_hub_download('lightx2v/Wan2.2-Lightning',
            'Wan2.2-I2V-A14B-4steps-lora-rank64-Seko-V1/'+name,
            revision='18bccf8884ec0a078eed79785eb4ef13ea16ce1e',local_dir=root)
        weights = WanImageToVideoPipeline.lora_state_dict(path)
        assert len(weights) > 100
        for key, tensor in weights.items():
            local = key.removeprefix('transformer.')
            target, kind = local.split('.lora_',1)
            module = model.get_submodule(target)
            if kind == 'A.weight':
                assert tensor.shape[1] == module.weight.shape[1], key
            elif kind in {'B.weight','B.bias'}:
                assert tensor.shape[0] == module.weight.shape[0], key
            else:
                raise AssertionError(key)
        print('Validated real adapter keys and shapes:', name, len(weights), flush=True)
        del weights
        gc.collect()
        Path(path).unlink()
    scheduler = FlowMatchEulerDiscreteScheduler(num_train_timesteps=1000, shift=5.0)
    scheduler.set_timesteps(4,sigmas=[1.0,0.75,0.5,0.25])
    assert (scheduler.timesteps >= 900).sum().item() == 2
    assert (scheduler.timesteps < 900).sum().item() == 2
    print('Validated 2 high-noise + 2 low-noise Euler steps', flush=True)
