from __future__ import annotations

from dataclasses import dataclass, asdict
from enum import StrEnum
from typing import Any


class JobStatus(StrEnum):
    QUEUED = "queued"
    RENDERING = "rendering"
    CLEANING = "cleaning"
    COMPLETE = "complete"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class RendererCapabilities:
    id: str
    name: str
    description: str
    recommended_for: str
    supports_start_frame: bool
    supports_end_frame: bool
    supports_audio: bool
    supported_durations: list[int]
    resolution: str = "720p"
    aspect_ratio: str = "9:16"
    notes: str = ""
    requires_start_frame: bool = True

    def dict(self) -> dict[str, Any]:
        return asdict(self)


RENDERERS: dict[str, RendererCapabilities] = {
    "h3-fl2va": RendererCapabilities(
        id="h3-fl2va", name="MiniMax H3", description="Self-hosted FL2VA with native first and last keyframes and audio.",
        recommended_for="Start + End Frame", supports_start_frame=True, supports_end_frame=True,
        supports_audio=True, supported_durations=list(range(4,16)), resolution="768p",
        requires_start_frame=False, notes="Experimental local SGLang adapter. License authorization and GPU validation required.",
    ),
    "ltx25": RendererCapabilities(
        id="ltx25",
        name="LTX-2.5",
        description="Fast local UGC renderer with native first/last-frame control.",
        recommended_for="Fast UGC iteration, controlled motion, first/last frame",
        supports_start_frame=True,
        supports_end_frame=True,
        supports_audio=True,
        supported_durations=list(range(4, 11)),
        notes="Default engine. End frame is native. Fastest starting point; first use downloads the LTX weights.",
    ),
    "wan22": RendererCapabilities(
        id="wan22",
        name="Wan 2.2 Lightning",
        description="720p image-to-video all-rounder with strong fidelity and motion.",
        recommended_for="Product shots, natural motion, higher-fidelity alternates",
        supports_start_frame=True,
        supports_end_frame=False,
        supports_audio=False,
        supported_durations=list(range(4, 11)),
        notes="Accelerated preset: BF16 Wan with trained four-step Lightning adapters, 720p. Requires 80 GB GPU. First use downloads ~126 GB; repeat jobs reuse weights. Silent video; no native end frame.",
    ),
    "skyreelsv3": RendererCapabilities(
        id="skyreelsv3",
        name="SkyReels V3",
        description="Reference-to-video renderer focused on keeping subjects and products consistent.",
        recommended_for="Reference fidelity, people, products, identity consistency",
        supports_start_frame=True,
        supports_end_frame=False,
        supports_audio=False,
        supported_durations=[5],
        notes="V1 uses the official 5-second 720p reference-to-video path and Python 3.12 runtime.",
    ),
}
