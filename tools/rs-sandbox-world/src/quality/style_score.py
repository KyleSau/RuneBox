"""RS-style 0–100 quality score from model metrics."""

from __future__ import annotations

from dataclasses import dataclass, field

from src.mesh.normalize import get_target_profile
from src.quality.metrics import ModelMetrics, target_extent


@dataclass
class StyleScore:
    score: int
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"score": self.score, "warnings": self.warnings, "notes": self.notes}


# Per-target soft limits for RS 317 item models.
_LIMITS: dict[str, dict[str, float | int]] = {
    "weapon": {"max_faces": 300, "max_vertices": 900, "max_colors": 16, "max_height_ratio": 2.5, "min_silhouette": 0.35},
    "shield": {"max_faces": 250, "max_vertices": 750, "max_colors": 16, "max_height_ratio": 2.0, "min_silhouette": 0.4},
    "helmet": {"max_faces": 200, "max_vertices": 600, "max_colors": 12, "max_height_ratio": 1.8, "min_silhouette": 0.4},
    "object": {"max_faces": 400, "max_vertices": 1200, "max_colors": 20, "max_height_ratio": 3.0, "min_silhouette": 0.3},
    "body": {"max_faces": 600, "max_vertices": 1800, "max_colors": 24, "max_height_ratio": 2.2, "min_silhouette": 0.35},
    "legs": {"max_faces": 400, "max_vertices": 1200, "max_colors": 20, "max_height_ratio": 2.5, "min_silhouette": 0.35},
    "npc": {"max_faces": 800, "max_vertices": 2400, "max_colors": 32, "max_height_ratio": 3.5, "min_silhouette": 0.3},
    "mount": {"max_faces": 900, "max_vertices": 2700, "max_colors": 32, "max_height_ratio": 4.0, "min_silhouette": 0.3},
}


def score_metrics(metrics: ModelMetrics) -> StyleScore:
    target = metrics.target.lower()
    limits = _LIMITS.get(target, _LIMITS["object"])
    profile = get_target_profile(target)

    score = 100
    warnings: list[str] = []
    notes: list[str] = []

    if not metrics.encode_decode_pass:
        score -= 40
        warnings.append("encoded model failed decode validation")

    if metrics.dev_smoke_pass is False:
        score -= 25
        warnings.append("DevModelSmoke failed for client dev model copy")

    max_colors = int(limits["max_colors"])
    if metrics.unique_face_colors > max_colors:
        penalty = min(20, (metrics.unique_face_colors - max_colors) // 2)
        score -= penalty
        warnings.append(
            f"too many colors: {metrics.unique_face_colors} unique colors, target <= {max_colors}"
        )

    max_faces = int(limits["max_faces"])
    if metrics.face_count > max_faces:
        penalty = min(15, (metrics.face_count - max_faces) // 20)
        score -= penalty
        warnings.append(f"high face count for {target}: {metrics.face_count} faces, target <= {max_faces}")

    max_vertices = int(limits["max_vertices"])
    if metrics.vertex_count > max_vertices:
        penalty = min(10, (metrics.vertex_count - max_vertices) // 50)
        score -= penalty
        warnings.append(f"high vertex count for item model: {metrics.vertex_count} verts, target <= {max_vertices}")

    max_ratio = float(limits["max_height_ratio"])
    if metrics.longest_axis_ratio > max_ratio:
        score -= 10
        if target == "weapon":
            warnings.append("too tall for weapon profile")
        else:
            warnings.append(
                f"elongated silhouette: axis ratio {metrics.longest_axis_ratio:.2f}, target <= {max_ratio:.1f}"
            )

    min_sil = float(limits["min_silhouette"])
    if metrics.silhouette_proxy < min_sil:
        score -= 8
        warnings.append(
            f"weak silhouette/readability proxy: {metrics.silhouette_proxy:.2f}, target >= {min_sil:.2f}"
        )

    if metrics.degenerate_removed_pct > 5.0:
        score -= 5
        warnings.append(f"high degenerate face removal: {metrics.degenerate_removed_pct:.1f}%")

    if metrics.texture_detail_dropped:
        score -= 5
        warnings.append("texture detail was dropped")

    if profile.stub:
        notes.append(f"target profile {target!r} uses stub scale defaults")

    if metrics.icon_readability_score is not None and metrics.icon_readability_score < 70:
        penalty = min(20, 70 - metrics.icon_readability_score)
        score -= penalty
        warnings.append(f"low icon readability: {metrics.icon_readability_score}/100")

    if metrics.dark_pixel_ratio > 0.55:
        score -= 10
        warnings.append("icon too dark")

    if metrics.icon_warnings:
        for w in metrics.icon_warnings[:3]:
            if w not in warnings:
                warnings.append(w.replace("WARN: ", ""))

    extent = target_extent(target)
    max_dim = max(metrics.bbox_size) if metrics.bbox_size else 0.0
    if max_dim > extent * 1.25:
        score -= 5
        warnings.append(f"bounding box large for {target}: {max_dim:.0f} RS units (target extent ~{extent:.0f})")

    score = max(0, min(100, score))
    return StyleScore(score=score, warnings=warnings, notes=notes)
