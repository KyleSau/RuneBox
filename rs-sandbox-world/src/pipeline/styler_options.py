"""Pipeline styler option helpers."""

from __future__ import annotations

from src.mesh.reconstruct import StylerOptions


def build_styler_options(
    *,
    reconstruct: str = "auto",
    archetype: str = "auto",
    repair_colors: bool = True,
    repair_silhouette: bool = True,
    icon_check: bool = True,
    target_colors: int | None = None,
    min_thickness_ratio: float = 0.08,
    max_axis_ratio: float = 8.0,
    ai_generated: bool = True,
    force_readable_icon: bool = False,
) -> StylerOptions:
    return StylerOptions(
        reconstruct=reconstruct,
        archetype=archetype,
        repair_colors=repair_colors,
        repair_silhouette=repair_silhouette,
        icon_check=icon_check,
        target_colors=target_colors,
        min_thickness_ratio=min_thickness_ratio,
        max_axis_ratio=max_axis_ratio,
        ai_generated=ai_generated,
        force_readable_icon=force_readable_icon,
    )
