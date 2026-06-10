"""Musket/handgonne icon readability regression tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.mesh.encode_pipeline import encode_rs_model
from src.mesh.reconstruct import StylerOptions
from src.mesh.rs_style import mesh_to_rs_model, save_rs2model_json
from src.mesh.weapon_rebuilder import build_weapon, infer_archetype
from src.quality.report import score_candidate_dir
from src.quality.style_score import score_metrics
from src.quality.metrics import compute_metrics


REGRESSION_PROMPT = (
    "a chunky medieval handgonne musket, short thick barrel, oversized brown wooden stock, "
    "light gray metal barrel, large flintlock hammer, large trigger guard, "
    "exaggerated readable silhouette, old RuneScape 2005 style"
)


@pytest.fixture
def handgonne_glb(tmp_path: Path) -> Path:
    mesh = build_weapon("handgonne")
    path = tmp_path / "handgonne.glb"
    mesh.export(path)
    return path


def test_handgonne_primitive_reconstruction(handgonne_glb: Path, tmp_path: Path) -> None:
    previews = tmp_path / "previews"
    styler = StylerOptions(
        reconstruct="weapon",
        archetype="handgonne",
        repair_colors=True,
        repair_silhouette=True,
        icon_check=True,
        ai_generated=True,
    )
    result = mesh_to_rs_model(
        handgonne_glb,
        "weapon",
        max_faces=180,
        styler=styler,
        user_prompt=REGRESSION_PROMPT,
        previews_dir=previews,
    )

    assert result.model.vertices
    assert len(result.model.faces) <= 180
    assert result.metadata.get("archetype") == "handgonne"
    assert result.metadata.get("iconScoreAfter", 0) >= 70

    for size in (128, 64, 32):
        assert (previews / f"icon_{size}.png").is_file()

    enc_path = tmp_path / "model.dat"
    enc = encode_rs_model(result.model, enc_path, preview_path=previews / "preview.png")
    assert enc.decoded.vertices


def test_handgonne_quality_scores(handgonne_glb: Path, tmp_path: Path) -> None:
    previews = tmp_path / "previews"
    previews.mkdir()

    result = mesh_to_rs_model(
        handgonne_glb,
        "weapon",
        max_faces=180,
        styler=StylerOptions(reconstruct="weapon", archetype="handgonne", icon_check=True, ai_generated=True),
        user_prompt=REGRESSION_PROMPT,
        previews_dir=previews,
    )

    encode_rs_model(result.model, tmp_path / "encoded" / "model.dat", preview_path=previews / "preview.png")
    meta = {
        "userPrompt": REGRESSION_PROMPT,
        "target": "weapon",
        "backend": "primitive",
        "archetype": "handgonne",
        "vertexCount": len(result.model.vertices),
        "faceCount": len(result.model.faces),
        "encodeDecodePass": True,
        "repairActions": result.metadata.get("repairActions", []),
        "iconScoreBefore": result.metadata.get("iconScoreBefore"),
        "iconScoreAfter": result.metadata.get("iconScoreAfter"),
        "normalizationWarnings": result.warnings,
    }
    (tmp_path / "metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    (tmp_path / "intermediate").mkdir(exist_ok=True)
    save_rs2model_json(tmp_path / "intermediate" / "normalized.rs2model.json", result.model, result.metadata)

    metrics, style = score_candidate_dir(tmp_path)
    assert metrics.dark_pixel_ratio < 0.55
    assert metrics.longest_axis_ratio <= 8.0
    assert style.score >= 70
    assert metrics.icon_readability_score is not None
    assert metrics.icon_readability_score >= 70


def test_archetype_inference() -> None:
    assert infer_archetype(REGRESSION_PROMPT) in {"handgonne", "musket", "blunderbuss"}
    assert infer_archetype("a large powerful two hand sword", "greatsword") == "greatsword"
