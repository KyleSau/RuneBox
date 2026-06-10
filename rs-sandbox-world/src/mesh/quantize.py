"""Per-face color extraction, RS HSL quantization, and readable color repair."""

from __future__ import annotations

import numpy as np
import trimesh

from src.mesh.color_repair import repair_rgb
from src.mesh.profiles import AssetProfile, get_asset_profile
from src.rs2.color import DEFAULT_GREY, DEFAULT_OBJECT_COLOR, DEFAULT_WEAPON_COLOR, rgb_to_rs_hsl


def quantize_face_colors(
    mesh: trimesh.Trimesh,
    target: str,
    warnings: list[str],
    *,
    profile: AssetProfile | None = None,
    repair: bool = False,
    preserve_palette: bool = False,
) -> list[int]:
    default = _default_color(target)
    face_count = len(mesh.faces)
    colors: list[int] = []
    asset_profile = profile or get_asset_profile(target)

    face_rgba = _face_colors(mesh)
    vertex_rgba = _vertex_colors(mesh)
    material_rgb = _material_diffuse(mesh, warnings)
    texture_rgb = _sample_texture_face_colors(mesh, warnings)

    for face_idx in range(face_count):
        rgb = None
        if face_rgba is not None:
            rgb = _rgba_to_rgb(face_rgba[face_idx])
        elif vertex_rgba is not None:
            tri = mesh.faces[face_idx]
            rgb = _rgba_to_rgb(vertex_rgba[tri].mean(axis=0))
        elif texture_rgb is not None and face_idx < len(texture_rgb):
            rgb = texture_rgb[face_idx]
        elif material_rgb is not None:
            rgb = material_rgb

        if rgb is None:
            colors.append(default)
        else:
            if repair and not preserve_palette:
                rgb = repair_rgb(rgb, asset_profile)
            colors.append(rgb_to_rs_hsl(*rgb))

    unique = len(set(colors))
    if preserve_palette and unique >= 2:
        return colors

    if all(c == default for c in colors):
        if material_rgb is None and face_rgba is None and vertex_rgba is None and texture_rgb is None:
            warnings.append("No usable input colors found; applied default RS-style color.")

    return colors


def _default_color(target: str) -> int:
    if target == "weapon":
        return DEFAULT_WEAPON_COLOR
    if target == "object":
        return DEFAULT_OBJECT_COLOR
    return DEFAULT_GREY


def _face_colors(mesh: trimesh.Trimesh) -> np.ndarray | None:
    colors = getattr(mesh.visual, "face_colors", None)
    if colors is None or len(mesh.faces) == 0:
        return None
    arr = np.asarray(colors)
    if len(arr) < len(mesh.faces):
        return None
    return arr[: len(mesh.faces)]


def _vertex_colors(mesh: trimesh.Trimesh) -> np.ndarray | None:
    visual = mesh.visual
    if getattr(visual, "kind", None) != "vertex":
        return None
    colors = getattr(visual, "vertex_colors", None)
    if colors is None or len(colors) != len(mesh.vertices):
        return None
    return np.asarray(colors)


def _material_diffuse(mesh: trimesh.Trimesh, warnings: list[str]) -> tuple[int, int, int] | None:
    mat = getattr(mesh.visual, "material", None)
    if mat is None:
        return None
    for attr in ("main_color", "diffuse", "baseColorFactor"):
        value = getattr(mat, attr, None)
        if value is None:
            continue
        arr = np.asarray(value).flatten()
        if len(arr) >= 3:
            rgb = tuple(int(max(0, min(255, round(v * 255 if v <= 1.0 else v)))) for v in arr[:3])
            warnings.append(f"Using material {attr} as fallback color.")
            return rgb
    return None


def _sample_texture_face_colors(mesh: trimesh.Trimesh, warnings: list[str]) -> list[tuple[int, int, int]] | None:
    visual = mesh.visual
    if getattr(visual, "kind", None) != "texture":
        return None
    material = getattr(visual, "material", None)
    image = getattr(material, "image", None) if material else None
    uv = getattr(visual, "uv", None)
    if image is None or uv is None:
        warnings.append("Texture present but UV/image unavailable; cannot sample per-face color.")
        return None

    try:
        img = np.asarray(image.convert("RGB"))
    except Exception:
        warnings.append("Texture image could not be read; using default colors.")
        return None

    h, w = img.shape[:2]
    out: list[tuple[int, int, int]] = []
    for face in mesh.faces:
        uvs = uv[face]
        center_u = float(np.clip(uvs[:, 0].mean(), 0.0, 1.0))
        center_v = float(np.clip(uvs[:, 1].mean(), 0.0, 1.0))
        px = int(center_u * (w - 1))
        py = int((1.0 - center_v) * (h - 1))
        rgb = tuple(int(x) for x in img[py, px])
        out.append(rgb)

    warnings.append("Sampled approximate texture color at face UV centroid.")
    return out


def _rgba_to_rgb(rgba) -> tuple[int, int, int]:
    arr = np.asarray(rgba).flatten()
    if len(arr) >= 3:
        return int(arr[0]), int(arr[1]), int(arr[2])
    return 128, 128, 128
