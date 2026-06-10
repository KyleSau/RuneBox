"""Asset profiles for RS-style reconstruction and icon readability."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class AssetProfile:
    name: str
    max_faces_default: int
    target_extent: float
    target_colors: int
    max_axis_ratio: float
    min_thickness_ratio: float
    icon_min_contrast: float = 0.25
    prefer_flat_colors: bool = True
    force_medium_metal: bool = False
    force_medium_wood: bool = False
    force_clear_magazine: bool = False
    force_large_ornament: bool = False
    force_large_head: bool = False
    stub: bool = False
    note: str = ""


BASE_PROFILES: dict[str, AssetProfile] = {
    "weapon": AssetProfile(
        "weapon",
        max_faces_default=300,
        target_extent=80.0,
        target_colors=12,
        max_axis_ratio=8.0,
        min_thickness_ratio=0.08,
        note="Inventory/ground weapon scale.",
    ),
    "object": AssetProfile(
        "object",
        max_faces_default=400,
        target_extent=120.0,
        target_colors=16,
        max_axis_ratio=3.0,
        min_thickness_ratio=0.10,
        note="Static ground object scale.",
    ),
    "shield": AssetProfile("shield", 250, 90.0, 10, 2.0, 0.10, stub=True),
    "helmet": AssetProfile("helmet", 200, 64.0, 8, 1.8, 0.10, stub=True),
    "body": AssetProfile("body", 600, 180.0, 20, 2.2, 0.10, stub=True),
    "legs": AssetProfile("legs", 400, 160.0, 16, 2.5, 0.10, stub=True),
    "npc": AssetProfile("npc", 800, 200.0, 24, 3.5, 0.08, stub=True),
    "mount": AssetProfile("mount", 900, 240.0, 24, 4.0, 0.08, stub=True),
}

ARCHETYPE_PROFILES: dict[str, AssetProfile] = {
    "musket": AssetProfile(
        "musket",
        max_faces_default=180,
        target_extent=80.0,
        target_colors=8,
        max_axis_ratio=6.0,
        min_thickness_ratio=0.12,
        force_medium_metal=True,
        force_medium_wood=True,
    ),
    "handgonne": AssetProfile(
        "handgonne",
        max_faces_default=180,
        target_extent=80.0,
        target_colors=8,
        max_axis_ratio=6.0,
        min_thickness_ratio=0.12,
        force_medium_metal=True,
        force_medium_wood=True,
    ),
    "blunderbuss": AssetProfile(
        "blunderbuss",
        max_faces_default=200,
        target_extent=80.0,
        target_colors=8,
        max_axis_ratio=5.5,
        min_thickness_ratio=0.14,
        force_medium_metal=True,
        force_medium_wood=True,
    ),
    "ak47": AssetProfile(
        "ak47",
        max_faces_default=180,
        target_extent=80.0,
        target_colors=8,
        max_axis_ratio=7.0,
        min_thickness_ratio=0.11,
        force_medium_metal=True,
        force_medium_wood=True,
        force_clear_magazine=True,
    ),
    "rifle": AssetProfile(
        "rifle",
        max_faces_default=180,
        target_extent=80.0,
        target_colors=8,
        max_axis_ratio=7.0,
        min_thickness_ratio=0.11,
        force_medium_metal=True,
        force_medium_wood=True,
        force_clear_magazine=True,
    ),
    "greatsword": AssetProfile(
        "greatsword",
        max_faces_default=120,
        target_extent=80.0,
        target_colors=8,
        max_axis_ratio=7.0,
        min_thickness_ratio=0.10,
        force_medium_metal=True,
    ),
    "sword": AssetProfile(
        "sword",
        max_faces_default=100,
        target_extent=80.0,
        target_colors=8,
        max_axis_ratio=7.0,
        min_thickness_ratio=0.10,
        force_medium_metal=True,
    ),
    "dagger": AssetProfile("dagger", 80, 64.0, 6, 4.0, 0.12, force_medium_metal=True),
    "axe": AssetProfile(
        "axe",
        max_faces_default=160,
        target_extent=80.0,
        target_colors=8,
        max_axis_ratio=7.0,
        min_thickness_ratio=0.10,
        force_medium_metal=True,
        force_medium_wood=True,
        force_large_head=True,
    ),
    "halberd": AssetProfile(
        "halberd",
        max_faces_default=160,
        target_extent=90.0,
        target_colors=8,
        max_axis_ratio=6.0,
        min_thickness_ratio=0.10,
        force_medium_metal=True,
        force_medium_wood=True,
        force_large_head=True,
    ),
    "staff": AssetProfile(
        "staff",
        max_faces_default=160,
        target_extent=90.0,
        target_colors=8,
        max_axis_ratio=8.0,
        min_thickness_ratio=0.08,
        force_medium_wood=True,
        force_large_ornament=True,
    ),
    "bow": AssetProfile("bow", 100, 80.0, 8, 6.0, 0.08, force_medium_wood=True),
    "shield": AssetProfile("shield", 120, 90.0, 10, 2.0, 0.12, force_medium_metal=True),
    "generic_weapon": AssetProfile(
        "generic_weapon",
        max_faces_default=200,
        target_extent=80.0,
        target_colors=10,
        max_axis_ratio=8.0,
        min_thickness_ratio=0.08,
    ),
}

WEAPON_ARCHETYPES = frozenset(ARCHETYPE_PROFILES.keys())


def get_asset_profile(target: str, archetype: str | None = None) -> AssetProfile:
    if archetype and archetype in ARCHETYPE_PROFILES:
        return ARCHETYPE_PROFILES[archetype]
    key = target.lower().strip()
    if key not in BASE_PROFILES:
        return BASE_PROFILES["object"]
    return BASE_PROFILES[key]


def profile_to_target_profile(asset: AssetProfile):
    """Bridge to legacy TargetProfile used by normalize_geometry."""
    from src.mesh.normalize import TargetProfile

    return TargetProfile(
        name=asset.name if asset.name in BASE_PROFILES else "weapon",
        max_faces_default=asset.max_faces_default,
        target_extent=asset.target_extent,
        stub=asset.stub,
        note=asset.note,
    )
