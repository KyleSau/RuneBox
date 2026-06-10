"""Concept image generation backends."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ConceptResult:
    image_path: Path
    backend: str
    prompt: str
    metadata: dict = field(default_factory=dict)


class ConceptBackend(ABC):
    name: str

    @abstractmethod
    def generate(self, prompt: str, output_dir: Path) -> ConceptResult:
        raise NotImplementedError


class ConceptBackendNotConfiguredError(RuntimeError):
    pass


def get_concept_backend(name: str, *, image_path: Path | None = None) -> ConceptBackend:
    key = name.lower().strip()
    if key == "manual":
        from src.ai.manual_concept_backend import ManualConceptBackend

        return ManualConceptBackend(image_path=image_path)
    if key == "openai":
        from src.ai.openai_concept_backend import OpenAIConceptBackend

        return OpenAIConceptBackend()
    if key == "local":
        from src.ai.local_image_backend import LocalImageConceptBackend

        return LocalImageConceptBackend()

    supported = "manual, openai, local"
    raise ValueError(f"Unknown concept backend {name!r}. Supported: {supported}")


def write_concept_artifacts(
    output_dir: Path,
    result: ConceptResult,
    *,
    user_prompt: str,
    target: str,
) -> Path:
    """Write concept.png, concept_prompt.txt, concept_metadata.json under output_dir."""
    output_dir.mkdir(parents=True, exist_ok=True)
    dest_image = output_dir / "concept.png"
    if result.image_path.resolve() != dest_image.resolve():
        import shutil

        shutil.copy2(result.image_path, dest_image)

    (output_dir / "concept_prompt.txt").write_text(result.prompt + "\n", encoding="utf-8")
    meta = {
        "backend": result.backend,
        "conceptBackend": result.backend,
        "userPrompt": user_prompt,
        "target": target,
        "imagePath": str(dest_image.resolve()),
        **{k: v for k, v in result.metadata.items() if "key" not in k.lower() and "api" not in k.lower()},
    }
    import json

    (output_dir / "concept_metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return dest_image
