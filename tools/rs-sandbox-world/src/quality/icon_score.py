"""0–100 icon readability score for RS 317 inventory thumbnails."""

from __future__ import annotations

from dataclasses import dataclass, field

from src.mesh.icon_readability import IconMetrics
from src.mesh.profiles import AssetProfile


@dataclass
class IconScore:
    score: int
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"score": self.score, "warnings": self.warnings}


def score_icon_metrics(metrics: IconMetrics, profile: AssetProfile | None = None) -> IconScore:
    score = 100
    warnings = list(metrics.warnings)

    if metrics.dark_pixel_ratio > 0.70:
        score -= 35
    elif metrics.dark_pixel_ratio > 0.50:
        score -= 20
    elif metrics.dark_pixel_ratio > 0.35:
        score -= 10

    min_contrast = profile.icon_min_contrast if profile else 0.25
    if metrics.contrast_score < min_contrast:
        score -= 15
        if "low contrast at 64x64" not in warnings:
            warnings.append("low contrast at 64x64")

    if metrics.thinness_score < 0.10:
        score -= 15
    elif metrics.thinness_score < 0.15:
        score -= 8

    max_ratio = profile.max_axis_ratio if profile else 8.0
    if metrics.longest_axis_ratio > max_ratio:
        score -= 12

    if metrics.bounding_box_fill_ratio > 0.95 and metrics.edge_detail_score < 0.06:
        score -= 20

    if metrics.silhouette_area_ratio < 0.25:
        score -= 10

    if metrics.color_clusters_32 <= 1:
        score -= 15

    score = max(0, min(100, score))
    return IconScore(score=score, warnings=warnings)
