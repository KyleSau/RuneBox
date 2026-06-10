"""Manual concept backend — copy an existing image into the pipeline."""

from __future__ import annotations

import shutil
from pathlib import Path

from src.ai.concept_backend import ConceptBackend, ConceptBackendNotConfiguredError, ConceptResult


class ManualConceptBackend(ConceptBackend):
    name = "manual"

    def __init__(self, image_path: Path | None = None) -> None:
        self.image_path = image_path

    def generate(self, prompt: str, output_dir: Path) -> ConceptResult:
        if self.image_path is None or not self.image_path.is_file():
            raise ConceptBackendNotConfiguredError(
                "Manual concept backend requires an image.\n"
                "Use --from-image path/to/concept.png with gen model, or pass --from-image to gen concept."
            )

        output_dir.mkdir(parents=True, exist_ok=True)
        dest = output_dir / "concept.png"
        shutil.copy2(self.image_path, dest)

        return ConceptResult(
            image_path=dest,
            backend=self.name,
            prompt=prompt,
            metadata={
                "sourceImage": str(self.image_path.resolve()),
                "note": "Copied from user-provided concept image.",
            },
        )
