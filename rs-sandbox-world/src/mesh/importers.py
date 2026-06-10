"""Load OBJ / PLY / GLB meshes via trimesh."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import trimesh


SUPPORTED_SUFFIXES = {".obj", ".ply", ".glb", ".gltf"}


@dataclass
class ImportedMesh:
    mesh: trimesh.Trimesh
    source_path: str
    warnings: list[str] = field(default_factory=list)


def load_mesh(path: Path) -> ImportedMesh:
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise ValueError(f"Unsupported mesh format {suffix!r}. Supported: {sorted(SUPPORTED_SUFFIXES)}")

    warnings: list[str] = []
    loaded = trimesh.load(path, force="mesh", process=False)

    if isinstance(loaded, trimesh.Scene):
        geometries = [g for g in loaded.geometry.values() if isinstance(g, trimesh.Trimesh)]
        if not geometries:
            raise ValueError(f"No mesh geometry found in {path}")
        mesh = trimesh.util.concatenate(geometries)
        if len(geometries) > 1:
            warnings.append(f"Merged {len(geometries)} meshes from scene.")
    elif isinstance(loaded, trimesh.Trimesh):
        mesh = loaded
    else:
        raise ValueError(f"Could not load mesh from {path}")

    mesh = mesh.copy()
    _collect_visual_warnings(mesh, warnings)
    return ImportedMesh(mesh=mesh, source_path=str(path.resolve()), warnings=warnings)


def _collect_visual_warnings(mesh: trimesh.Trimesh, warnings: list[str]) -> None:
    visual = mesh.visual
    kind = getattr(visual, "kind", None)
    if kind == "texture":
        warnings.append("Textured mesh detected; texture detail will be approximated or dropped.")
    if kind == "vertex" and not hasattr(visual, "vertex_colors"):
        warnings.append("Vertex colors expected but missing; using default RS colors.")
    if hasattr(visual, "material") and visual.material is not None and kind != "face":
        mat = visual.material
        if getattr(mat, "image", None) is not None:
            warnings.append("Material texture image present; only diffuse/average color will be used.")
