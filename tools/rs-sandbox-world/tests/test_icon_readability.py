"""Icon thumbnail generation and readability scoring."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.mesh.encode_pipeline import encode_rs_model
from src.mesh.icon_readability import ICON_SIZES, compute_icon_metrics
from src.mesh.reconstruct import StylerOptions
from src.mesh.rs_style import mesh_to_rs_model, save_rs2model_json
from src.mesh.weapon_rebuilder import build_weapon
from src.quality.report import score_candidate_dir


@pytest.fixture
def sword_glb(tmp_path: Path) -> Path:
    mesh = build_weapon("sword")
    path = tmp_path / "sword.glb"
    mesh.export(path)
    return path


def test_icon_previews_created(sword_glb: Path, tmp_path: Path) -> None:
    previews = tmp_path / "previews"
    result = mesh_to_rs_model(
        sword_glb,
        "weapon",
        max_faces=120,
        styler=StylerOptions(reconstruct="off", icon_check=False, ai_generated=False),
        previews_dir=previews,
    )
    encode_rs_model(result.model, tmp_path / "model.dat", preview_path=previews / "preview.png")
    icon_m = compute_icon_metrics(result.model, previews)
    for size in ICON_SIZES:
        assert (previews / f"icon_{size}.png").is_file()
    assert 0.0 <= icon_m.dark_pixel_ratio <= 1.0
    assert icon_m.bounding_box_fill_ratio > 0.0
    assert icon_m.visible_color_cluster_count >= 1


def test_icon_metrics_in_quality_outputs(sword_glb: Path, tmp_path: Path) -> None:
    previews = tmp_path / "previews"
    previews.mkdir()
    result = mesh_to_rs_model(
        sword_glb,
        "weapon",
        max_faces=120,
        styler=StylerOptions(reconstruct="off", icon_check=False, ai_generated=False),
        previews_dir=previews,
    )
    encode_rs_model(result.model, tmp_path / "encoded" / "model.dat", preview_path=previews / "preview.png")
    (tmp_path / "metadata.json").write_text(
        json.dumps(
            {
                "userPrompt": "test sword",
                "target": "weapon",
                "backend": "mock",
                "vertexCount": len(result.model.vertices),
                "faceCount": len(result.model.faces),
                "encodeDecodePass": True,
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "intermediate").mkdir(exist_ok=True)
    save_rs2model_json(tmp_path / "intermediate" / "normalized.rs2model.json", result.model, result.metadata)

    metrics, _style = score_candidate_dir(tmp_path)
    report = (tmp_path / "quality_report.txt").read_text(encoding="utf-8")
    qjson = json.loads((tmp_path / "quality_score.json").read_text(encoding="utf-8"))

    assert metrics.icon_readability_score is not None
    assert 0 <= metrics.icon_readability_score <= 100
    assert metrics.bounding_box_fill_ratio > 0.0
    assert metrics.visible_color_cluster_count >= 1
    assert "Icon Readability Score:" in report
    assert "bounding_box_fill_ratio" in report
    assert qjson["iconMetrics"]["bounding_box_fill_ratio"] > 0.0
    assert "iconScore" in qjson
