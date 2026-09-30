"""Dedicated resident reference-to-video engine; never shares a loaded Wan session."""
from app.config import settings
from app.renderers.wan import WanRenderer


class SkyReelsRenderer(WanRenderer):
    id = "skyreelsv3"
    result_prefix = "@@SKYREELS_RESULT@@"

    @property
    def command(self):
        return settings.skyreels_runner_cmd

    def payload(self, req):
        payload = super().payload(req)
        payload["reference_frames"] = [str(path) for path in req.reference_frames]
        return payload


skyreels_renderer = SkyReelsRenderer()
