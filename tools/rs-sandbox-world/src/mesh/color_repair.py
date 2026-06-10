"""RS-style color repair — brighten dark AI meshes and reduce palette."""

from __future__ import annotations

import numpy as np

from src.mesh.profiles import AssetProfile
from src.rs2.color import rgb_to_rs_hsl, rs_hsl_to_rgb

# Readable RS-ish material colors (sRGB).
PALETTE = {
    "steel": (150, 152, 158),
    "light_steel": (178, 180, 186),
    "dark_steel": (100, 102, 108),
    "wood": (140, 100, 62),
    "light_wood": (168, 128, 82),
    "grip_wood": (118, 82, 50),
    "magazine": (96, 98, 104),
    "bronze": (168, 118, 64),
    "gold": (186, 158, 72),
    "yellow": (210, 190, 48),
    "cream": (220, 210, 180),
    "charcoal": (82, 84, 90),
}

DARK_LUMINANCE = 55
NEAR_BLACK_LUMINANCE = 30


def _luminance(rgb: tuple[int, int, int]) -> float:
    r, g, b = rgb
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def brighten_rgb(rgb: tuple[int, int, int], min_lum: float = 80.0) -> tuple[int, int, int]:
    r, g, b = rgb
    lum = _luminance(rgb)
    if lum >= min_lum:
        return rgb
    if lum < 1e-3:
        return PALETTE["steel"]
    factor = min_lum / lum
    return (
        int(min(255, r * factor)),
        int(min(255, g * factor)),
        int(min(255, b * factor)),
    )


def classify_material(rgb: tuple[int, int, int]) -> str:
    r, g, b = rgb
    lum = _luminance(rgb)
    if lum < DARK_LUMINANCE:
        if b > r + 10:
            return "dark_steel"
        if r > g + 15:
            return "wood"
        return "dark_steel"
    if r > 150 and g > 120 and b < 100:
        return "wood" if g < 130 else "bronze"
    if r > 170 and g > 150:
        return "gold"
    if max(r, g, b) - min(r, g, b) < 20:
        return "steel" if lum > 100 else "dark_steel"
    return "steel"


def repair_rgb(
    rgb: tuple[int, int, int],
    profile: AssetProfile | None = None,
) -> tuple[int, int, int]:
    lum = _luminance(rgb)
    mat = classify_material(rgb)

    if profile and profile.force_medium_metal and mat in {"dark_steel", "steel"}:
        return PALETTE["steel"]
    if profile and profile.force_medium_wood and mat == "wood":
        return PALETTE["wood"]

    if lum < NEAR_BLACK_LUMINANCE:
        if mat == "wood":
            return PALETTE["wood"]
        return PALETTE["steel"]

    if lum < DARK_LUMINANCE:
        return brighten_rgb(PALETTE.get(mat, PALETTE["steel"]), min_lum=85.0)

    return brighten_rgb(rgb, min_lum=70.0)


def repair_face_colors(
    face_colors: list[int],
    *,
    profile: AssetProfile | None = None,
    target_colors: int | None = None,
) -> tuple[list[int], list[str]]:
    """Repair and optionally reduce RS HSL face colors."""
    warnings: list[str] = []
    if not face_colors:
        return face_colors, warnings

    rgb_list = [rs_hsl_to_rgb(c) for c in face_colors]
    dark_count = sum(1 for rgb in rgb_list if _luminance(rgb) < DARK_LUMINANCE)
    if dark_count > len(rgb_list) * 0.5:
        warnings.append(f"brightened {dark_count} dark material clusters")

    repaired = [repair_rgb(rgb, profile) for rgb in rgb_list]
    hsl = [rgb_to_rs_hsl(*rgb) for rgb in repaired]

    budget = target_colors or (profile.target_colors if profile else 16)
    if len(set(hsl)) > budget:
        hsl, merged = _reduce_palette(hsl, budget)
        if merged:
            warnings.append(f"reduced palette to {budget} face colors")

    return hsl, warnings


def repair_mesh_colors(mesh, profile: AssetProfile | None = None, *, preserve_distinct: bool = False):
    """Brighten per-face primitive colors; never collapse to a single default."""
    import trimesh

    work = mesh.copy()
    n_faces = len(work.faces)
    if n_faces == 0:
        return work, []

    fc = getattr(work.visual, "face_colors", None)
    if fc is not None and len(fc) >= n_faces:
        out = np.asarray(fc[:n_faces], dtype=np.uint8).copy()
        for i in range(n_faces):
            rgb = (int(out[i, 0]), int(out[i, 1]), int(out[i, 2]))
            if preserve_distinct:
                r, g, b = brighten_rgb(rgb, min_lum=72.0)
            else:
                r, g, b = repair_rgb(rgb, profile)
            out[i] = [r, g, b, 255]
        work.visual.face_colors = out
        unique = len({tuple(row[:3]) for row in out})
        verb = "preserved" if preserve_distinct else "brightened"
        return work, [f"{verb} {unique} primitive material region(s)"]

    default = PALETTE["steel"]
    colors = np.tile(np.array([*default, 255], dtype=np.uint8), (n_faces, 1))
    work.visual.face_colors = colors
    return work, ["applied RS readable default face colors to reconstructed mesh"]


def _reduce_palette(hsl: list[int], target: int) -> tuple[list[int], bool]:
    """Merge similar colors to stay within budget."""
    unique = list(dict.fromkeys(hsl))
    if len(unique) <= target:
        return hsl, False

    rgb_unique = [rs_hsl_to_rgb(c) for c in unique]
    clusters: list[list[int]] = [[i] for i in range(len(unique))]

    while len(clusters) > target:
        best_dist = float("inf")
        merge_a, merge_b = 0, 1
        for i in range(len(clusters)):
            for j in range(i + 1, len(clusters)):
                ri = rgb_unique[clusters[i][0]]
                rj = rgb_unique[clusters[j][0]]
                dist = sum((a - b) ** 2 for a, b in zip(ri, rj))
                if dist < best_dist:
                    best_dist = dist
                    merge_a, merge_b = i, j
        clusters[merge_a].extend(clusters[merge_b])
        del clusters[merge_b]

    mapping: dict[int, int] = {}
    for cluster in clusters:
        rep = cluster[0]
        rep_hsl = unique[rep]
        for idx in cluster:
            mapping[unique[idx]] = rep_hsl

    return [mapping.get(c, c) for c in hsl], True
