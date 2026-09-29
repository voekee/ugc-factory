from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


@dataclass
class RenderRequest:
    job_id: str
    prompt: str
    duration: int
    seed: int
    start_frame: Path | None
    end_frame: Path | None
    output_path: Path


class Renderer(ABC):
    id: str

    @abstractmethod
    def render(self, req: RenderRequest) -> None:
        raise NotImplementedError
