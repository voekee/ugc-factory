"""Build-time isolation: no avatar/video-extension dependencies in reference runtime."""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.run_skyreels_resident import CODE_REVISION, MODEL_REVISION, RUNTIME_FILE

root = Path('/opt/ugc-models/SkyReels-V3/skyreels_v3')
# Upstream package initializers eagerly import unused avatar/extension pipelines.
# Narrow only their exports; retain the unmodified official reference transformer,
# pipeline, scheduler, SDPA attention and license. No FlashAttention installation.
(root / 'pipelines/__init__.py').write_text('from .reference_to_video_pipeline import ReferenceToVideoPipeline\n')
(root / 'modules/__init__.py').write_text('# Reference-only runtime. Submodules are imported explicitly.\n')
RUNTIME_FILE.write_text(json.dumps({'code_revision': CODE_REVISION,
                                   'model_revision': MODEL_REVISION,
                                   'scope': 'reference_to_video', 'weights_downloaded': False}))
