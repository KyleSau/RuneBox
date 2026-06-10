"""Shap-E backend stub."""

from __future__ import annotations

from pathlib import Path

from src.ai.generator_backend import BackendNotConfiguredError, GenerationResult, GeneratorBackend
from src.config import SHAPE_E_ENABLED, SHAPE_E_COMMAND


class ShapEBackend(GeneratorBackend):
    name = "shap-e"

    def generate(
        self,
        prompt: str,
        output_dir: Path,
        *,
        image_path: Path | None = None,
    ) -> GenerationResult:
        if not SHAPE_E_ENABLED and not SHAPE_E_COMMAND:
            raise BackendNotConfiguredError(
                "Shap-E backend is not configured.\n"
                "Set SHAPE_E_ENABLED = True and SHAPE_E_COMMAND in src/config.py, or use --backend mock."
            )
        raise BackendNotConfiguredError(
            "Shap-E backend stub is present but not wired yet. "
            "Use --backend mock or --backend hunyuan3d for now."
        )
