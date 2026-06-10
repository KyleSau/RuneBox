"""Hunyuan3D command-wrapper backend."""

from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path

from src.ai.generator_backend import (
    BackendNotConfiguredError,
    GenerationResult,
    GeneratorBackend,
    ImageInputNotSupportedError,
)
from src.config import resolve_hunyuan3d_command

MESH_SUFFIXES = (".obj", ".glb", ".ply", ".stl")


class Hunyuan3DBackend(GeneratorBackend):
    name = "hunyuan3d"
    supports_image_input = True

    def generate(
        self,
        prompt: str,
        output_dir: Path,
        *,
        image_path: Path | None = None,
    ) -> GenerationResult:
        command = resolve_hunyuan3d_command()
        if not command:
            raise BackendNotConfiguredError(
                "Hunyuan3D backend is not configured.\n"
                "Set RS_HUNYUAN3D_COMMAND or config.HUNYUAN3D_COMMAND.\n"
                "Example expected command:\n"
                '  python path/to/hunyuan_generate.py --prompt "<prompt>" --output "<output_dir>"'
            )

        output_dir.mkdir(parents=True, exist_ok=True)
        raw_dir = output_dir / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)

        cmd = _format_command(command, prompt, raw_dir, image_path=image_path)
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            stderr = (result.stderr or result.stdout or "").strip()
            if image_path is not None and _looks_like_missing_image_flag(stderr):
                raise ImageInputNotSupportedError(
                    "Hunyuan3D image input is not supported by this wrapper yet.\n"
                    "Text-only generation still works.\n"
                    f"Command error: {stderr}"
                )
            raise RuntimeError(f"Hunyuan3D command failed (exit {result.returncode}): {stderr}")

        mesh_path = _find_generated_mesh(raw_dir)
        if mesh_path is None:
            mesh_path = _find_generated_mesh(output_dir)
        if mesh_path is None:
            raise FileNotFoundError(
                f"Hunyuan3D command completed but no mesh found under {output_dir}. "
                f"Expected one of: {', '.join(MESH_SUFFIXES)}"
            )

        return GenerationResult(
            raw_mesh_path=mesh_path,
            backend=self.name,
            prompt=prompt,
            image_input=str(image_path.resolve()) if image_path else None,
            metadata={
                "command": command,
                "imageInput": str(image_path.resolve()) if image_path else None,
                "stdout": (result.stdout or "")[-4000:],
                "stderr": (result.stderr or "")[-4000:],
            },
        )


def _looks_like_missing_image_flag(stderr: str) -> bool:
    lower = stderr.lower()
    return "unrecognized arguments: --image" in lower or "unknown option" in lower and "image" in lower


def _format_command(
    command: str,
    prompt: str,
    output_dir: Path,
    *,
    image_path: Path | None = None,
) -> list[str]:
    if "{prompt}" in command or "{output}" in command:
        kwargs = {"prompt": prompt, "output": str(output_dir)}
        if image_path is not None:
            kwargs["image"] = str(image_path)
        formatted = command.format(**kwargs)
        return shlex.split(formatted, posix=os.name != "nt")

    parts = shlex.split(command, posix=os.name != "nt")
    cmd = parts + ["--prompt", prompt, "--output", str(output_dir)]
    if image_path is not None:
        cmd.extend(["--image", str(image_path)])
    return cmd


def _find_generated_mesh(root: Path) -> Path | None:
    candidates: list[Path] = []
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in MESH_SUFFIXES:
            candidates.append(path)
    if not candidates:
        return None
    candidates.sort(key=lambda p: (p.suffix.lower() != ".obj", p.stat().st_mtime))
    return candidates[0]
