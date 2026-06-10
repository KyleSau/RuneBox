"""Mock backend — copies a local test OBJ for end-to-end pipeline testing."""

from __future__ import annotations

import shutil
from pathlib import Path

from src.ai.generator_backend import GenerationResult, GeneratorBackend
from src.config import MOCK_MESH_SOURCE


class MockBackend(GeneratorBackend):
    name = "mock"
    supports_image_input = True

    def __init__(self, source_mesh: Path | None = None) -> None:
        self.source_mesh = source_mesh or MOCK_MESH_SOURCE

    def generate(
        self,
        prompt: str,
        output_dir: Path,
        *,
        image_path: Path | None = None,
    ) -> GenerationResult:
        if image_path is not None:
            # Mock ignores concept image; still produces fixture mesh for pipeline testing.
            pass
        if not self.source_mesh.exists():
            raise FileNotFoundError(f"Mock source mesh not found: {self.source_mesh}")

        raw_dir = output_dir / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        suffix = self.source_mesh.suffix.lower() or ".obj"
        dest = raw_dir / f"raw_model{suffix}"
        shutil.copy2(self.source_mesh, dest)

        # Copy sidecar MTL if present (OBJ materials).
        mtl = self.source_mesh.with_suffix(".mtl")
        if mtl.exists():
            shutil.copy2(mtl, raw_dir / mtl.name)

        return GenerationResult(
            raw_mesh_path=dest,
            backend=self.name,
            prompt=prompt,
            image_input=str(image_path.resolve()) if image_path else None,
            metadata={
                "mockSource": str(self.source_mesh.resolve()),
                "note": "Mock backend copies a local fixture; no AI inference performed.",
                "conceptImageIgnored": image_path is not None,
            },
        )
