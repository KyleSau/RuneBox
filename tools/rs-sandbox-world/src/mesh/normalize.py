"""Scale, orient, center, and snap meshes to RS integer coordinates.

Target scale/orientation uses profiles from `src.mesh.profiles` via `profile_to_target_profile`.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import trimesh

# Jagex models use small integer vertex coords; stay well inside signed 16-bit range.
MAX_COORD = 16000
SAFE_EXTENT = 32000


@dataclass(frozen=True)
class TargetProfile:
    name: str
    max_faces_default: int
    target_extent: float
    stub: bool = False
    note: str = ""


TARGET_PROFILES: dict[str, TargetProfile] = {
    "weapon": TargetProfile("weapon", 300, 80.0, note="Inventory/ground weapon scale."),
    "object": TargetProfile("object", 400, 120.0, note="Static ground object scale."),
    "shield": TargetProfile("shield", 250, 90.0, stub=True, note="Stub profile — weapon-like defaults."),
    "helmet": TargetProfile("helmet", 200, 64.0, stub=True, note="Stub profile — centered head gear."),
    "body": TargetProfile("body", 600, 180.0, stub=True, note="Stub profile — torso armor scale."),
    "legs": TargetProfile("legs", 400, 160.0, stub=True, note="Stub profile — leg armor scale."),
    "npc": TargetProfile("npc", 800, 200.0, stub=True, note="Stub profile — humanoid NPC scale."),
    "mount": TargetProfile("mount", 900, 240.0, stub=True, note="Stub profile — large mount scale."),
}


def get_target_profile(name: str) -> TargetProfile:
    key = name.lower().strip()
    if key not in TARGET_PROFILES:
        supported = ", ".join(sorted(TARGET_PROFILES))
        raise ValueError(f"Unknown target {name!r}. Supported: {supported}")
    return TARGET_PROFILES[key]


def normalize_geometry(
    mesh: trimesh.Trimesh,
    target: TargetProfile,
) -> tuple[trimesh.Trimesh, list[str]]:
    warnings: list[str] = []
    if target.stub:
        warnings.append(f"Target profile {target.name!r} is a stub; using documented default scale/orientation.")

    work = mesh.copy()
    work.apply_transform(_target_rotation(target.name))

    vertices = np.asarray(work.vertices, dtype=np.float64)
    center = (vertices.min(axis=0) + vertices.max(axis=0)) / 2.0
    vertices -= center

    extent = float(np.max(vertices.max(axis=0) - vertices.min(axis=0)))
    if extent < 1e-8:
        raise ValueError("Mesh has zero extent after centering.")

    scale = target.target_extent / extent
    vertices *= scale

    snapped = np.rint(vertices).astype(np.int32)
    if np.any(np.abs(snapped) > MAX_COORD):
        shrink = MAX_COORD / float(np.max(np.abs(snapped)))
        snapped = np.rint(snapped.astype(np.float64) * shrink).astype(np.int32)
        warnings.append(f"Clamped coordinates to ±{MAX_COORD} RS units.")

    if np.max(np.abs(snapped)) > SAFE_EXTENT:
        warnings.append("Coordinates exceed recommended RS safe range; model may render incorrectly.")

    out = trimesh.Trimesh(vertices=snapped.astype(np.float64), faces=work.faces.copy(), process=False)
    if hasattr(work.visual, "face_colors") and work.visual.face_colors is not None:
        out.visual.face_colors = work.visual.face_colors
    elif hasattr(work.visual, "vertex_colors") and work.visual.vertex_colors is not None:
        out.visual.vertex_colors = work.visual.vertex_colors
    if hasattr(out.visual, "material") and getattr(work.visual, "material", None) is not None:
        out.visual.material = work.visual.material
    if hasattr(out.visual, "uv") and getattr(work.visual, "uv", None) is not None:
        out.visual.uv = work.visual.uv

    return out, warnings


def _target_rotation(target: str) -> np.ndarray:
    """Target-specific orientation (Y-up RS-style). MVP: identity except minor tweaks."""
    if target == "weapon":
        # Many OBJ weapons lie flat on XZ; rotate upright for RS inventory axis.
        return trimesh.transformations.rotation_matrix(np.radians(-90), [1, 0, 0])
    if target in {"helmet", "shield"}:
        return trimesh.transformations.rotation_matrix(np.radians(-90), [1, 0, 0])
    return np.eye(4)
