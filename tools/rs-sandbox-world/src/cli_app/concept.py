"""Standalone concept image generation CLI."""

from __future__ import annotations

from pathlib import Path

from src.ai.concept_backend import ConceptBackendNotConfiguredError
from src.config import GENERATED_CONCEPTS_DIR
from src.pipeline.candidate import slugify
from src.pipeline.concept_candidate import generate_standalone_concept


def run_concept(
    target: str,
    description: str,
    *,
    backend: str,
    out: Path | None = None,
    from_image: Path | None = None,
) -> Path:
    slug = slugify(description)
    out_dir = (out or (GENERATED_CONCEPTS_DIR / slug)).resolve()

    if backend == "manual" and from_image is None:
        raise ConceptBackendNotConfiguredError(
            "Standalone concept generation with manual backend requires --from-image.\n"
            "Use --backend openai for automatic concept generation, or provide an image to copy."
        )

    result = generate_standalone_concept(
        description,
        target,
        backend,
        out_dir,
        from_image=from_image,
    )
    print(f"Concept: {result.image_path}")
    print(f"Output: {out_dir}")
    return out_dir
