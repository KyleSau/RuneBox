"""RS-style reconstruction and repair orchestrator."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path

import trimesh

from src.mesh.color_repair import repair_mesh_colors
from src.mesh.profiles import AssetProfile, get_asset_profile
from src.mesh.silhouette import analyze_silhouette, thicken_silhouette
from src.mesh.weapon_rebuilder import (
    build_weapon,
    can_rebuild,
    infer_archetype,
    is_firearm_archetype,
)


@dataclass
class StylerOptions:
    reconstruct: str = "off"  # auto | off | weapon | primitive
    archetype: str = "auto"
    repair_colors: bool = True
    repair_silhouette: bool = True
    icon_check: bool = True
    target_colors: int | None = None
    min_thickness_ratio: float = 0.08
    max_axis_ratio: float = 8.0
    ai_generated: bool = False
    force_readable_icon: bool = False
    primitive_only: bool = False

    @classmethod
    def for_primitive(cls, archetype: str, **overrides) -> StylerOptions:
        opts = cls(
            reconstruct="primitive",
            archetype=archetype,
            ai_generated=False,
            primitive_only=True,
            repair_colors=True,
            repair_silhouette=False,
            icon_check=True,
        )
        for k, v in overrides.items():
            if hasattr(opts, k):
                setattr(opts, k, v)
        return opts

    @classmethod
    def for_ai_generation(cls, **overrides) -> StylerOptions:
        opts = cls(reconstruct="auto", ai_generated=True)
        for k, v in overrides.items():
            if hasattr(opts, k):
                setattr(opts, k, v)
        return opts

    @classmethod
    def for_roundtrip(cls) -> StylerOptions:
        return cls(reconstruct="off", repair_colors=False, repair_silhouette=False, icon_check=False)


@dataclass
class StylerReport:
    archetype: str | None = None
    reconstructed: bool = False
    used_primitive: bool = False
    primitive_reconstruction: bool = False
    raw_ai_mesh_used_as_geometry: bool = True
    repair_actions: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    icon_score_before: int | None = None
    icon_score_after: int | None = None

    def to_dict(self) -> dict:
        return {
            "archetype": self.archetype,
            "reconstructed": self.reconstructed,
            "usedPrimitive": self.used_primitive,
            "primitiveReconstruction": self.primitive_reconstruction,
            "rawAiMeshUsedAsGeometry": self.raw_ai_mesh_used_as_geometry,
            "repairActions": self.repair_actions,
            "warnings": self.warnings,
            "iconScoreBefore": self.icon_score_before,
            "iconScoreAfter": self.icon_score_after,
        }


def build_primitive_weapon(
    archetype: str,
    target: str = "weapon",
    *,
    options: StylerOptions | None = None,
) -> tuple[trimesh.Trimesh, AssetProfile, StylerReport]:
    """Build geometry purely from procedural primitives — no AI mesh."""
    opts = options or StylerOptions.for_primitive(archetype)
    report = StylerReport(
        archetype=archetype,
        reconstructed=True,
        used_primitive=True,
        primitive_reconstruction=True,
        raw_ai_mesh_used_as_geometry=False,
    )
    profile = get_asset_profile(target, archetype)
    mesh = build_weapon(archetype, reference=None)
    mesh, color_w = repair_mesh_colors(mesh, profile, preserve_distinct=True)
    report.repair_actions.append(f"rebuilt as archetype: {archetype}")
    report.repair_actions.extend(color_w)
    report.repair_actions.append("Primitive reconstruction: TRUE")
    report.repair_actions.append("Raw AI mesh used as geometry: FALSE")
    return mesh, profile, report


def apply_pre_normalize_stylizer(
    mesh: trimesh.Trimesh,
    target: str,
    options: StylerOptions,
    user_prompt: str = "",
) -> tuple[trimesh.Trimesh, AssetProfile, StylerReport]:
    """Run reconstruction and silhouette repair before decimation/normalize."""
    report = StylerReport()
    archetype = infer_archetype(user_prompt, None if options.archetype == "auto" else options.archetype)
    report.archetype = archetype
    profile = get_asset_profile(target, archetype)

    if options.min_thickness_ratio != 0.08:
        profile = _override_profile(profile, min_thickness_ratio=options.min_thickness_ratio)
    if options.max_axis_ratio != 8.0:
        profile = _override_profile(profile, max_axis_ratio=options.max_axis_ratio)

    mode = options.reconstruct
    if options.primitive_only:
        mode = "primitive"
    elif mode == "auto" and options.ai_generated:
        mode = "weapon"
    if options.force_readable_icon and target == "weapon" and can_rebuild(archetype):
        mode = "primitive"
    # Firearms always use procedural geometry when reconstructing.
    if is_firearm_archetype(archetype) and mode in {"auto", "weapon", "primitive"}:
        mode = "primitive"

    should_rebuild = mode in {"weapon", "primitive"} and target == "weapon" and can_rebuild(archetype)

    if should_rebuild:
        work, profile, prim_report = build_primitive_weapon(archetype, target, options=options)
        report.reconstructed = prim_report.reconstructed
        report.used_primitive = prim_report.used_primitive
        report.primitive_reconstruction = prim_report.primitive_reconstruction
        report.raw_ai_mesh_used_as_geometry = False
        report.repair_actions.extend(prim_report.repair_actions)
        return work, profile, report

    work = mesh.copy()
    report.raw_ai_mesh_used_as_geometry = True
    if options.repair_silhouette:
        stats = analyze_silhouette(work)
        if stats["thickness_ratio"] < profile.min_thickness_ratio or stats["longest_axis_ratio"] > profile.max_axis_ratio:
            work, sil_w = thicken_silhouette(
                work,
                min_thickness_ratio=profile.min_thickness_ratio,
                max_axis_ratio=profile.max_axis_ratio,
            )
            report.repair_actions.extend(sil_w)

    return work, profile, report


def _override_profile(profile: AssetProfile, **kwargs) -> AssetProfile:
    return replace(profile, **kwargs)


def save_reconstructed_preview(mesh: trimesh.Trimesh, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mesh.export(path)
