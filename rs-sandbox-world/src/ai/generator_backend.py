"""Base types and backend registry for text → mesh generation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class GenerationResult:
    raw_mesh_path: Path
    backend: str
    prompt: str
    metadata: dict = field(default_factory=dict)
    image_input: str | None = None


class GeneratorBackend(ABC):
    name: str
    supports_image_input: bool = False

    @abstractmethod
    def generate(
        self,
        prompt: str,
        output_dir: Path,
        *,
        image_path: Path | None = None,
    ) -> GenerationResult:
        raise NotImplementedError


class BackendNotConfiguredError(RuntimeError):
    pass


class ImageInputNotSupportedError(RuntimeError):
    pass


def get_backend(name: str) -> GeneratorBackend:
    key = name.lower().strip()
    if key == "mock":
        from src.ai.mock_backend import MockBackend

        return MockBackend()
    if key in ("hunyuan3d", "hunyuan"):
        from src.ai.hunyuan3d_backend import Hunyuan3DBackend

        return Hunyuan3DBackend()
    if key in ("shap-e", "shap_e", "shapee"):
        from src.ai.shap_e_backend import ShapEBackend

        return ShapEBackend()
    if key in ("triposr", "tripo"):
        from src.ai.triposr_backend import TripoSRBackend

        return TripoSRBackend()

    supported = "mock, hunyuan3d, shap-e, triposr"
    raise ValueError(f"Unknown backend {name!r}. Supported: {supported}")
