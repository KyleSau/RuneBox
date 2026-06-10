"""Write quality score JSON and human-readable reports."""

from __future__ import annotations

import json
from pathlib import Path

from src.mesh.icon_readability import compute_icon_metrics
from src.mesh.profiles import get_asset_profile
from src.mesh.rs_style import load_rs2model_json
from src.quality.icon_score import score_icon_metrics
from src.quality.metrics import ModelMetrics, _apply_icon_metrics, compute_metrics
from src.quality.style_score import StyleScore, score_metrics


def score_candidate_dir(candidate_dir: Path) -> tuple[ModelMetrics, StyleScore]:
    metrics = compute_metrics(candidate_dir)
    style = score_metrics(metrics)
    icon_score, icon_metrics = _score_icons(candidate_dir, metrics)
    write_reports(candidate_dir, metrics, style, icon_score=icon_score, icon_metrics=icon_metrics)
    return metrics, style


def _score_icons(candidate_dir: Path, metrics: ModelMetrics):
    json_path = candidate_dir / "intermediate" / "normalized.rs2model.json"
    if not json_path.is_file():
        icon64 = candidate_dir / "previews" / "icon_64.png"
        if not icon64.is_file():
            return None, None
        from src.mesh.icon_readability import analyze_icon_image

        icon_m = analyze_icon_image(icon64)
        _apply_icon_metrics(metrics, icon_m)
        profile = get_asset_profile(metrics.target, metrics.archetype)
        return score_icon_metrics(icon_m, profile), icon_m

    model, _ = load_rs2model_json(json_path)
    icon_m = compute_icon_metrics(model, candidate_dir / "previews")
    _apply_icon_metrics(metrics, icon_m)
    profile = get_asset_profile(metrics.target, metrics.archetype)
    icon_score = score_icon_metrics(icon_m, profile)
    metrics.icon_readability_score = icon_score.score
    return icon_score, icon_m


def write_reports(
    candidate_dir: Path,
    metrics: ModelMetrics,
    style: StyleScore,
    *,
    icon_score=None,
    icon_metrics=None,
) -> None:
    candidate_dir = candidate_dir.resolve()
    payload = {
        "metrics": metrics.to_dict(),
        "styleScore": style.to_dict(),
    }
    if icon_score is not None:
        payload["iconScore"] = icon_score.to_dict()
    if icon_metrics is not None:
        payload["iconMetrics"] = icon_metrics.to_dict()
    (candidate_dir / "quality_score.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    (candidate_dir / "quality_report.txt").write_text(
        format_report(metrics, style, icon_score=icon_score, icon_metrics=icon_metrics), encoding="utf-8"
    )


def format_report(
    metrics: ModelMetrics,
    style: StyleScore,
    *,
    icon_score=None,
    icon_metrics=None,
) -> str:
    lines = [
        f"RS Style Score: {style.score}/100",
    ]
    icon_val = icon_score.score if icon_score is not None else metrics.icon_readability_score
    if icon_val is not None:
        lines.append(f"Icon Readability Score: {icon_val}/100")
    lines.extend(
        [
            "",
            f"Prompt: {metrics.user_prompt}",
            f"Target: {metrics.target}",
            f"Backend: {metrics.backend}",
        ]
    )
    if metrics.archetype:
        lines.append(f"Archetype: {metrics.archetype}")
    if metrics.primitive_reconstruction:
        lines.append("Primitive reconstruction: TRUE")
        lines.append("Raw AI mesh used as geometry: FALSE")
    lines.extend(
        [
            "",
            "Metrics:",
            f"  Vertices: {metrics.vertex_count}",
            f"  Faces: {metrics.face_count}",
            f"  Unique face colors: {metrics.unique_face_colors}",
            f"  Bbox (X,Y,Z): {', '.join(f'{v:.1f}' for v in metrics.bbox_size)}",
            f"  Longest axis ratio: {metrics.longest_axis_ratio:.2f}",
            f"  Degenerate removed: {metrics.degenerate_removed_pct:.1f}%",
            f"  Avg triangle area: {metrics.avg_triangle_area:.2f}",
            f"  Silhouette proxy: {metrics.silhouette_proxy:.2f}",
        ]
    )
    if metrics.dark_pixel_ratio or metrics.contrast_score or metrics.bounding_box_fill_ratio:
        lines.extend(
            [
                "",
                "Icon readability:",
                f"  dark_pixel_ratio: {metrics.dark_pixel_ratio:.4f}",
                f"  contrast_score: {metrics.contrast_score:.4f}",
                f"  bounding_box_fill_ratio: {metrics.bounding_box_fill_ratio:.4f}",
                f"  silhouette_area_ratio: {metrics.silhouette_area_ratio:.4f}",
                f"  longest_axis_ratio: {metrics.icon_longest_axis_ratio:.4f}",
                f"  visible_color_cluster_count: {metrics.visible_color_cluster_count}",
            ]
        )
    lines.extend(
        [
            f"  Encode/decode: {'PASS' if metrics.encode_decode_pass else 'FAIL'}",
            f"  DevModelSmoke: {_smoke_label(metrics.dev_smoke_pass)}",
        ]
    )
    if metrics.repair_actions:
        lines.extend(["", "Repair actions:"])
        for action in metrics.repair_actions:
            lines.append(f"- {action}")
        if metrics.icon_readability_score is not None:
            lines.append("Icon readability: see metadata iconScoreBefore -> iconScoreAfter")
    all_warnings = list(style.warnings)
    if metrics.icon_warnings:
        all_warnings.extend(metrics.icon_warnings)
    if icon_score is not None and icon_score.warnings:
        for w in icon_score.warnings:
            if w not in all_warnings:
                all_warnings.append(w)
    if all_warnings:
        lines.extend(["", "Warnings:"])
        for w in all_warnings:
            lines.append(f"- {w}")
    if style.notes:
        lines.extend(["", "Notes:"])
        for n in style.notes:
            lines.append(f"- {n}")
    lines.append("")
    return "\n".join(lines)


def _smoke_label(value: bool | None) -> str:
    if value is True:
        return "PASS"
    if value is False:
        return "FAIL"
    return "not run"


def print_report(metrics: ModelMetrics, style: StyleScore, *, icon_score=None) -> None:
    print(format_report(metrics, style, icon_score=icon_score))
