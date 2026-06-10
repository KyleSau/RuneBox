"""OpenAI text-to-image concept generation."""

from __future__ import annotations

import base64
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

from src.ai.concept_backend import ConceptBackend, ConceptBackendNotConfiguredError, ConceptResult
from src.config import OPENAI_API_KEY, OPENAI_IMAGE_MODEL


class OpenAIConceptBackend(ConceptBackend):
    name = "openai"

    def generate(self, prompt: str, output_dir: Path) -> ConceptResult:
        if not OPENAI_API_KEY:
            raise ConceptBackendNotConfiguredError(
                "OpenAI concept backend is not configured.\n"
                "Set OPENAI_API_KEY in .env.local or your environment.\n"
                "See .env.example for setup."
            )

        output_dir.mkdir(parents=True, exist_ok=True)
        dest = output_dir / "concept.png"

        try:
            from openai import OpenAI
        except ImportError as exc:
            raise ConceptBackendNotConfiguredError(
                "OpenAI package not installed. Run: pip install openai"
            ) from exc

        client = OpenAI(api_key=OPENAI_API_KEY)
        model = OPENAI_IMAGE_MODEL

        try:
            response = client.images.generate(
                model=model,
                prompt=prompt,
                size="1024x1024",
            )
        except Exception as exc:
            raise RuntimeError(f"OpenAI image generation failed: {exc}") from exc

        image_data = _extract_image_bytes(response)
        dest.write_bytes(image_data)

        return ConceptResult(
            image_path=dest,
            backend=self.name,
            prompt=prompt,
            metadata={
                "imageModel": model,
                "createdAt": datetime.now(timezone.utc).isoformat(),
            },
        )


def _extract_image_bytes(response) -> bytes:
    if not response.data:
        raise RuntimeError("OpenAI returned no image data.")

    item = response.data[0]
    b64 = getattr(item, "b64_json", None)
    if b64:
        return base64.b64decode(b64)

    url = getattr(item, "url", None)
    if url:
        with urlopen(url, timeout=120) as resp:
            return resp.read()

    raise RuntimeError(
        "OpenAI response contained neither base64 image data nor a downloadable URL. "
        "Try a different OPENAI_IMAGE_MODEL."
    )
