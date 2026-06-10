"""Weapon-specific primitive reconstruction for RS 317 readability."""

from __future__ import annotations

import numpy as np
import trimesh

from src.mesh.color_repair import PALETTE
from src.mesh.primitives import (
    blade_center_ridge,
    box_prism,
    crossguard,
    faceted_blade_tip,
    merge_meshes,
    octagonal_cylinder,
    pommel_faceted,
    ring_band,
    segmented_magazine,
    tapered_box_prism,
    trigger_guard,
    wedge_blade,
)

FIREARM_ARCHETYPES = frozenset({"ak47", "rifle", "handgonne", "musket", "blunderbuss"})
ICON_ORIENT_ARCHETYPES = FIREARM_ARCHETYPES | frozenset({"greatsword"})


def is_firearm_archetype(archetype: str | None) -> bool:
    return archetype is not None and archetype in FIREARM_ARCHETYPES


def orient_weapon_for_icon(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    """Slight 3/4 angle for inventory icon readability."""
    work = mesh.copy()
    center = work.centroid
    work.apply_translation(-center)
    yaw = trimesh.transformations.rotation_matrix(np.radians(22), [0, 1, 0])
    pitch = trimesh.transformations.rotation_matrix(np.radians(-10), [0, 0, 1])
    work.apply_transform(yaw @ pitch)
    work.apply_translation(center)
    return work

# Order of keywords does not matter — infer_archetype picks longest matching keyword.
ARCHETYPE_KEYWORDS: dict[str, list[str]] = {
    "ak47": ["ak47", "ak-47", "ak 47", "ak themed", "rs-themed ak", "kalashnikov"],
    "rifle": ["assault rifle", "modern rifle", "machine gun", "submachine gun", "automatic rifle"],
    "blunderbuss": ["blunderbuss", "blunder bus"],
    "handgonne": ["handgonne", "hand gonne", "hand cannon", "hand-cannon"],
    "musket": [
        "musket",
        "arquebus",
        "flintlock",
        "matchlock",
        "blackpowder",
        "primitive firearm",
        "black powder",
    ],
    "greatsword": ["greatsword", "great sword", "two hand sword", "two-handed sword", "buster sword", "claymore"],
    "sword": ["sword", "longsword", "long sword", "scimitar", "katana"],
    "dagger": ["dagger", "knife", "dirk"],
    "axe": ["axe", "hatchet", "battleaxe", "battle axe"],
    "halberd": ["halberd", "poleaxe", "pole axe", "glaive"],
    "staff": ["staff", "wand", "sceptre", "scepter"],
    "bow": ["bow", "longbow", "shortbow"],
    "shield": ["shield", "kite shield", "buckler"],
}

REBUILD_ARCHETYPES = frozenset(
    {
        "musket",
        "handgonne",
        "blunderbuss",
        "ak47",
        "rifle",
        "greatsword",
        "sword",
        "dagger",
        "axe",
        "halberd",
        "staff",
        "bow",
        "shield",
        "generic_weapon",
    }
)


def infer_archetype(prompt: str, explicit: str | None = None) -> str | None:
    if explicit and explicit not in ("auto", ""):
        return explicit.lower().strip()
    text = prompt.lower()
    # Explicit model names beat generic class keywords (e.g. ak47 vs assault rifle).
    for name in ("ak47", "ak-47", "handgonne", "blunderbuss", "musket", "greatsword", "halberd"):
        if name in text:
            return name.replace("-", "")
    matches: list[tuple[int, str]] = []
    for archetype, keywords in ARCHETYPE_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                matches.append((len(kw), archetype))
    if not matches:
        return None
    matches.sort(key=lambda x: (-x[0], x[1]))
    return matches[0][1]


def can_rebuild(archetype: str | None) -> bool:
    return archetype is not None and archetype in REBUILD_ARCHETYPES


def build_weapon(archetype: str, reference: trimesh.Trimesh | None = None) -> trimesh.Trimesh:
    builders = {
        "musket": _build_musket,
        "handgonne": _build_handgonne,
        "blunderbuss": _build_blunderbuss,
        "ak47": _build_ak47,
        "rifle": _build_rifle,
        "greatsword": _build_greatsword,
        "sword": _build_sword,
        "dagger": _build_dagger,
        "axe": _build_axe,
        "halberd": _build_halberd,
        "staff": _build_staff,
        "bow": _build_bow,
        "shield": _build_shield,
        "generic_weapon": _build_generic_weapon,
    }
    fn = builders.get(archetype, _build_generic_weapon)
    mesh = fn(reference)
    if archetype in ICON_ORIENT_ARCHETYPES:
        mesh = orient_weapon_for_icon(mesh)
    return mesh


def _build_ak47(_reference: trimesh.Trimesh | None) -> trimesh.Trimesh:
    """Deterministic readable low-poly AK — medium gray/brown, exaggerated magazine."""
    wood = PALETTE["wood"]
    handguard = PALETTE["light_wood"]
    steel = PALETTE["steel"]
    cover = PALETTE["light_steel"]
    mag = PALETTE["magazine"]
    grip = PALETTE["grip_wood"]
    accent = PALETTE["charcoal"]
    bronze = PALETTE["bronze"]

    parts = [
        # Stock — chunky tapered brown prism (rear)
        tapered_box_prism(0.26, 0.18, 0.16, 0.14, 0.12, x_start=-0.44, color=wood),
        # Receiver — large central medium-gray box
        box_prism(0.20, 0.16, 0.12, center=(-0.16, 0.0, 0.0), color=steel),
        # Top cover — lighter gray tapered box
        tapered_box_prism(0.14, 0.10, 0.06, 0.08, 0.05, x_start=-0.20, color=cover),
        # Pistol grip — dark-brown angled chunk
        box_prism(0.08, 0.09, 0.12, center=(-0.10, -0.08, -0.04), color=grip),
        # Handguard — brown block in front of receiver
        box_prism(0.16, 0.12, 0.10, center=(0.02, 0.0, -0.01), color=handguard),
        # Barrel — short thick octagonal (not dominant length)
        octagonal_cylinder(0.18, 0.055, x_start=0.10, color=steel),
        # Muzzle ring — lighter widened tip
        octagonal_cylinder(0.04, 0.07, x_start=0.28, color=cover),
        # Barrel band
        ring_band(0.12, 0.06, 0.04, 0.025, color=steel),
        # Segmented exaggerated magazine — darker gray, distinct from receiver steel
        segmented_magazine(5, 0.045, 0.11, 0.07, start_center=(0.0, -0.08, -0.08), tilt_deg=24.0, color=mag),
        # Trigger guard — thick blocky U (bronze accent, visible vs steel)
        trigger_guard(0.11, 0.09, 0.05, center=(0.0, -0.03, -0.05), color=bronze),
        # Front sight — oversized blocky wedge
        wedge_blade(0.05, 0.06, 0.08, x_start=0.22, color=accent),
        box_prism(0.03, 0.04, 0.05, center=(0.24, 0.0, 0.06), color=cover),
    ]
    return merge_meshes(*parts)


def _build_rifle(reference: trimesh.Trimesh | None) -> trimesh.Trimesh:
    return _build_ak47(reference)


def _build_musket(_reference: trimesh.Trimesh | None) -> trimesh.Trimesh:
    wood = PALETTE["wood"]
    metal = PALETTE["steel"]
    dark = PALETTE["dark_steel"]

    parts = [
        tapered_box_prism(0.38, 0.22, 0.16, 0.18, 0.14, x_start=-0.42, color=wood),
        octagonal_cylinder(0.52, 0.07, x_start=-0.06, color=metal),
        octagonal_cylinder(0.06, 0.095, x_start=0.46, color=metal),
        box_prism(0.08, 0.10, 0.06, center=(0.02, 0.08, 0.0), color=dark),
        box_prism(0.05, 0.08, 0.04, center=(0.0, 0.14, 0.0), color=dark),
        trigger_guard(0.08, 0.07, 0.04, center=(0.04, -0.08, -0.02), color=dark),
        ring_band(0.08, 0.075, 0.055, 0.025, color=metal),
        ring_band(0.30, 0.075, 0.055, 0.025, color=metal),
    ]
    return merge_meshes(*parts)


def _build_handgonne(reference: trimesh.Trimesh | None) -> trimesh.Trimesh:
    return _build_musket(reference)


def _build_blunderbuss(reference: trimesh.Trimesh | None) -> trimesh.Trimesh:
    wood = PALETTE["wood"]
    metal = PALETTE["steel"]
    dark = PALETTE["dark_steel"]

    parts = [
        tapered_box_prism(0.32, 0.24, 0.18, 0.20, 0.16, x_start=-0.40, color=wood),
        octagonal_cylinder(0.38, 0.08, x_start=-0.08, color=metal),
        octagonal_cylinder(0.10, 0.13, x_start=0.30, color=metal),
        box_prism(0.08, 0.11, 0.07, center=(0.0, 0.09, 0.0), color=dark),
        box_prism(0.05, 0.09, 0.05, center=(0.0, 0.15, 0.0), color=dark),
        trigger_guard(0.09, 0.08, 0.04, center=(0.02, -0.10, -0.02), color=dark),
        ring_band(0.06, 0.085, 0.06, 0.03, color=metal),
    ]
    return merge_meshes(*parts)


def _build_greatsword(_reference: trimesh.Trimesh | None) -> trimesh.Trimesh:
    """Chunky RS 2005-style two-handed sword — primitives only, ~60–120 faces, 6–10 colors."""
    blade = PALETTE["light_steel"]
    blade_edge = PALETTE["steel"]
    ridge = PALETTE["dark_steel"]
    guard = PALETTE["steel"]
    guard_dark = PALETTE["charcoal"]
    grip = PALETTE["grip_wood"]
    grip_wrap = PALETTE["light_wood"]
    pommel = PALETTE["dark_steel"]
    pommel_accent = PALETTE["bronze"]

    parts = [
        # Pommel + end cap (visible at icon scale)
        pommel_faceted(0.11, center=(-0.38, 0.0, 0.0), color=pommel),
        box_prism(0.04, 0.09, 0.09, center=(-0.44, 0.0, 0.0), color=pommel_accent),
        # Long two-handed grip — three dark-brown segments
        box_prism(0.11, 0.058, 0.058, center=(-0.29, 0.0, 0.0), color=grip),
        box_prism(0.11, 0.062, 0.062, center=(-0.18, 0.0, 0.0), color=grip),
        box_prism(0.11, 0.058, 0.058, center=(-0.07, 0.0, 0.0), color=grip),
        # Wrap band (lighter wood accent)
        box_prism(0.035, 0.068, 0.072, center=(-0.135, 0.0, 0.0), color=grip_wrap),
        # Chunky crossguard — wide arms + thick center block
        crossguard(0.30, 0.07, 0.08, -0.01, color=guard),
        box_prism(0.06, 0.24, 0.09, center=(-0.01, 0.0, 0.0), color=guard),
        box_prism(0.05, 0.10, 0.06, center=(-0.01, 0.0, 0.045), color=guard_dark),
        # Ricasso (blade root) — steel-gray shoulder
        box_prism(0.07, 0.15, 0.10, center=(0.04, 0.0, 0.0), color=blade_edge),
        # Broad tapered blade body (wedge + tapered prism for extra facets)
        wedge_blade(0.40, 0.22, 0.10, x_start=0.07, color=blade),
        tapered_box_prism(0.40, 0.20, 0.14, 0.06, 0.05, x_start=0.07, color=blade_edge),
        # Center ridge (darker strip along blade top)
        blade_center_ridge(0.36, 0.04, 0.025, x_start=0.09, z_offset=0.03, color=ridge),
        # Side edge highlights (lighter steel bevels)
        box_prism(0.34, 0.028, 0.035, center=(0.24, 0.095, 0.0), color=blade),
        box_prism(0.34, 0.028, 0.035, center=(0.24, -0.095, 0.0), color=blade),
        # Faceted tip
        faceted_blade_tip(0.14, 0.14, 0.09, x_start=0.46, color=blade_edge),
    ]
    return merge_meshes(*parts)


def _build_sword(_reference: trimesh.Trimesh | None) -> trimesh.Trimesh:
    steel = PALETTE["steel"]
    grip = PALETTE["wood"]
    dark = PALETTE["dark_steel"]

    parts = [
        wedge_blade(0.48, 0.12, 0.05, x_start=0.04, color=steel),
        crossguard(0.16, 0.05, 0.05, 0.04, color=steel),
        box_prism(0.14, 0.05, 0.05, center=(-0.08, 0.0, 0.0), color=grip),
        box_prism(0.05, 0.07, 0.07, center=(-0.17, 0.0, 0.0), color=dark),
    ]
    return merge_meshes(*parts)


def _build_dagger(_reference: trimesh.Trimesh | None) -> trimesh.Trimesh:
    steel = PALETTE["steel"]
    grip = PALETTE["wood"]
    parts = [
        wedge_blade(0.28, 0.08, 0.04, x_start=0.02, color=steel),
        crossguard(0.10, 0.04, 0.04, 0.02, color=steel),
        box_prism(0.10, 0.04, 0.04, center=(-0.06, 0.0, 0.0), color=grip),
    ]
    return merge_meshes(*parts)


def _build_axe(_reference: trimesh.Trimesh | None) -> trimesh.Trimesh:
    wood = PALETTE["wood"]
    steel = PALETTE["steel"]
    parts = [
        octagonal_cylinder(0.55, 0.04, x_start=-0.30, color=wood),
        box_prism(0.16, 0.22, 0.08, center=(0.18, 0.08, 0.0), color=steel),
        wedge_blade(0.12, 0.20, 0.06, x_start=0.24, color=steel),
    ]
    return merge_meshes(*parts)


def _build_halberd(_reference: trimesh.Trimesh | None) -> trimesh.Trimesh:
    wood = PALETTE["wood"]
    steel = PALETTE["steel"]
    parts = [
        octagonal_cylinder(0.65, 0.035, x_start=-0.35, color=wood),
        wedge_blade(0.22, 0.18, 0.05, x_start=0.22, color=steel),
        box_prism(0.10, 0.08, 0.05, center=(0.18, -0.08, 0.0), color=steel),
        wedge_blade(0.08, 0.06, 0.04, x_start=0.20, color=steel),
    ]
    return merge_meshes(*parts)


def _build_staff(_reference: trimesh.Trimesh | None) -> trimesh.Trimesh:
    wood = PALETTE["wood"]
    gold = PALETTE["gold"]
    cream = PALETTE["cream"]
    parts = [
        octagonal_cylinder(0.68, 0.045, x_start=-0.34, color=wood),
        box_prism(0.14, 0.16, 0.16, center=(0.38, 0.0, 0.0), color=gold),
        box_prism(0.08, 0.20, 0.08, center=(0.46, 0.0, 0.0), color=cream),
        box_prism(0.06, 0.12, 0.12, center=(0.52, 0.0, 0.0), color=gold),
    ]
    return merge_meshes(*parts)


def _build_bow(_reference: trimesh.Trimesh | None) -> trimesh.Trimesh:
    wood = PALETTE["light_wood"]
    parts = []
    for y in np.linspace(-0.18, 0.18, 5):
        x = 0.08 * (1 - abs(y) / 0.2)
        parts.append(box_prism(0.04, 0.04, 0.08, center=(x, y, 0.0), color=wood))
    return merge_meshes(*parts)


def _build_shield(_reference: trimesh.Trimesh | None) -> trimesh.Trimesh:
    steel = PALETTE["steel"]
    wood = PALETTE["wood"]
    parts = [
        box_prism(0.06, 0.32, 0.40, center=(0.0, 0.0, 0.0), color=steel),
        box_prism(0.08, 0.10, 0.10, center=(-0.04, 0.0, 0.0), color=wood),
    ]
    return merge_meshes(*parts)


def _build_generic_weapon(_reference: trimesh.Trimesh | None) -> trimesh.Trimesh:
    return _build_sword(_reference)
