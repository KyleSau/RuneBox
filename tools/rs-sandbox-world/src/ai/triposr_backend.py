"""TripoSR command-wrapper backend (lighter fallback)."""

from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path

from src.ai.generator_backend import BackendNotConfiguredError, GenerationResult, GeneratorBackend
from src.config import resolve_triposr_command

MESH_SUFFIXES = (".obj", ".glb", ".ply", ".stl")


class TripoSRBackend(GeneratorBackend):
    name = "triposr"

    def generate(
        self,
        prompt: str,
        output_dir: Path,
        *,
        image_path: Path | None = None,
    ) -> GenerationResult:
        command = resolve_triposr_command()
        if not command:
            raise BackendNotConfiguredError(
                "TripoSR backend is not configured.\n"
                "Set RS_TRIPOSR_COMMAND or config.TRIPOSR_COMMAND.\n"
                "Example:\n"
                '  python path/to/triposr_generate.py --prompt "<prompt>" --output "<output_dir>"\n'
                "See tools/ai-backends/triposr/README.md"
            )

        output_dir.mkdir(parents=True, exist_ok=True)
        raw_dir = output_dir / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)

        cmd = _format_command(command, prompt, raw_dir)
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            stderr = (result.stderr or result.stdout or "").strip()
            raise RuntimeError(f"TripoSR command failed (exit {result.returncode}): {stderr}")

        mesh_path = _find_generated_mesh(raw_dir)
        if mesh_path is None:
            mesh_path = _find_generated_mesh(output_dir)
        if mesh_path is None:
            raise FileNotFoundError(
                f"TripoSR command completed but no mesh found under {output_dir}. "
                f"Expected one of: {', '.join(MESH_SUFFIXES)}"
            )

        return GenerationResult(
            raw_mesh_path=mesh_path,
            backend=self.name,
            prompt=prompt,
            metadata={
                "command": command,
                "stdout": (result.stdout or "")[-4000:],
                "stderr": (result.stderr or "")[-4000:],
            },
        )


def _format_command(command: str, prompt: str, output_dir: Path) -> list[str]:
    if "{prompt}" in command or "{output}" in command:
        formatted = command.format(prompt=prompt, output=str(output_dir))
        return shlex.split(formatted, posix=os.name != "nt")

    parts = shlex.split(command, posix=os.name != "nt")
    return parts + ["--prompt", prompt, "--output", str(output_dir)]


def _find_generated_mesh(root: Path) -> Path | None:
    candidates: list[Path] = []
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in MESH_SUFFIXES:
            candidates.append(path)
    if not candidates:
        return None
    candidates.sort(key=lambda p: (p.suffix.lower() != ".obj", p.stat().st_mtime))
    return candidates[0]
