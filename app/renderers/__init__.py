from __future__ import annotations

from app.config import settings
from app.renderers.command import CommandRenderer
from app.renderers.mock import MockRenderer


def get_renderer(renderer_id: str):
    if renderer_id == "h3-fl2va":
        from app.h3 import require_h3
        from app.renderers.h3 import H3Renderer
        require_h3()
        return H3Renderer()
    if settings.ugc_renderer_mode.lower() == "mock":
        return MockRenderer()
    commands = {
        "ltx25": settings.ltx_runner_cmd,
        "wan22": settings.wan_runner_cmd,
        "skyreelsv3": settings.skyreels_runner_cmd,
    }
    if renderer_id not in commands:
        raise ValueError(f"Unknown renderer: {renderer_id}")
    return CommandRenderer(renderer_id, commands[renderer_id])
