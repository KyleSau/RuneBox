"""Local image generation backend (stub)."""

from __future__ import annotations

from pathlib import Path

from src.ai.concept_backend import ConceptBackend, ConceptBackendNotConfiguredError, ConceptResult


class LocalImageConceptBackend(ConceptBackend):
    name = "local"

    def generate(self, prompt: str, output_dir: Path) -> ConceptResult:
        raise ConceptBackendNotConfiguredError(
            "Local image backend is not configured yet.\n"
            "Use --concept-backend openai or --from-image path/to/concept.png."
        )
