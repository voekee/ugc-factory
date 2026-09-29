"""Trim unused upstream tasks from the pinned single-GPU reference runtime.

SkyReels imports avatar and multi-GPU dependencies even for reference generation.
Its CLIP also calls flash_attention directly, so use the same PyTorch SDPA fallback
that upstream already uses for transformer attention when flash-attn is absent.
"""

from pathlib import Path
import sys


root = Path(sys.argv[1])


def replace(relative: str, old: str, new: str) -> None:
    path = root / relative
    source = path.read_text()
    if old not in source:
        raise SystemExit(f"SkyReels pinned source changed: {relative}: {old[:60]!r}")
    path.write_text(source.replace(old, new, 1))


replace(
    "skyreels_v3/pipelines/__init__.py",
    "from .shot_switching_extension_pipeline import ShotSwitchingExtensionPipeline\n"
    "from .single_shot_extension_pipeline import SingleShotExtensionPipeline\n"
    "from .talking_avatar_pipeline import TalkingAvatarPipeline\n",
    "",
)
replace(
    "generate_video.py",
    "    ShotSwitchingExtensionPipeline,\n"
    "    SingleShotExtensionPipeline,\n"
    "    TalkingAvatarPipeline,\n",
    "",
)
replace("generate_video.py", "from skyreels_v3.utils.avatar_preprocess import preprocess_audio\n", "")
replace(
    "generate_video.py",
    '"reference_to_video": "Skywork/SkyReels-V3-Reference2Video"',
    '"reference_to_video": "Skywork/SkyReels-V3-R2V-14B"',
)
replace(
    "skyreels_v3/modules/attention.py",
    "    # params\n    b, lq, lk, _ = q.size(0), q.size(1), k.size(1), q.dtype\n",
    """    # CLIP calls this helper directly. The transformer already has an SDPA fallback.
    if not FLASH_ATTN_2_AVAILABLE and not FLASH_ATTN_3_AVAILABLE:
        query = q.transpose(1, 2).to(dtype)
        key = k.transpose(1, 2).to(dtype)
        value = v.transpose(1, 2).to(dtype)
        output = torch.nn.functional.scaled_dot_product_attention(
            query, key, value, dropout_p=dropout_p, is_causal=causal,
            scale=softmax_scale,
        )
        return output.transpose(1, 2).contiguous()

    # params
    b, lq, lk, _ = q.size(0), q.size(1), k.size(1), q.dtype
""",
)
