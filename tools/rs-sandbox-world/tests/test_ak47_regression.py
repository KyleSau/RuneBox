"""AK47 firearm icon readability regression — primary firearm validation case."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from src.mesh.encode_pipeline import encode_rs_model
from src.mesh.reconstruct import StylerOptions
from src.mesh.rs_style import mesh_to_rs_model, save_rs2model_json, trimesh_to_rs_model
from src.mesh.weapon_rebuilder import build_weapon, infer_archetype
from src.pipeline.concept_candidate import generate_model_candidate
from src.pipeline.primitive_candidate import generate_primitive_candidate
from src.quality.report import score_candidate_dir

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PIPELINE_ROOT = Path(__file__).resolve().parents[1]
AK47_CONCEPT = PROJECT_ROOT / "concepts" / "ak47.png"

REGRESSION_PROMPT = (
    "an rs-themed ak47, chunky low-poly assault rifle, brown wooden stock and handguard, "
    "medium gray metal receiver and barrel, exaggerated curved magazine, readable silhouette, "
    "old RuneScape 2005 style"
)


@pytest.fixture
def ak47_glb(tmp_path: Path) -> Path:
    mesh = build_weapon("ak47")
    path = tmp_path / "ak47.glb"
    mesh.export(path)
    return path


def test_ak47_concept_image_exists() -> None:
    assert AK47_CONCEPT.is_file(), f"Expected AK47 concept at {AK47_CONCEPT}"


def test_ak47_primitive_reconstruction(ak47_glb: Path, tmp_path: Path) -> None:
    previews = tmp_path / "previews"
    result = mesh_to_rs_model(
        ak47_glb,
        "weapon",
        max_faces=180,
        styler=StylerOptions(
            reconstruct="primitive",
            archetype="ak47",
            repair_colors=True,
            repair_silhouette=True,
            icon_check=True,
            ai_generated=True,
        ),
        user_prompt=REGRESSION_PROMPT,
        previews_dir=previews,
    )

    assert result.metadata.get("archetype") == "ak47"
    assert result.metadata.get("primitiveReconstruction") is True
    assert result.metadata.get("rawAiMeshUsedAsGeometry") is False
    assert len(set(result.model.face_colors)) >= 4
    assert len(result.model.faces) <= 180
    assert result.metadata.get("iconScoreAfter", 0) >= 70
    for size in (128, 64, 32):
        assert (previews / f"icon_{size}.png").is_file()
    assert any("Primitive reconstruction: TRUE" in a for a in result.metadata.get("repairActions", []))


def test_ak47_quality_scores(ak47_glb: Path, tmp_path: Path) -> None:
    previews = tmp_path / "previews"
    previews.mkdir()

    result = mesh_to_rs_model(
        ak47_glb,
        "weapon",
        max_faces=180,
        styler=StylerOptions(reconstruct="primitive", archetype="ak47", icon_check=True, ai_generated=True),
        user_prompt=REGRESSION_PROMPT,
        previews_dir=previews,
    )

    encode_rs_model(result.model, tmp_path / "encoded" / "model.dat", preview_path=previews / "preview.png")
    meta = {
        "userPrompt": REGRESSION_PROMPT,
        "target": "weapon",
        "backend": "primitive",
        "archetype": "ak47",
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
    assert metrics.unique_face_colors >= 4
    assert metrics.dark_pixel_ratio < 0.55
    assert metrics.longest_axis_ratio <= 8.0
    assert style.score >= 70
    assert metrics.icon_readability_score is not None
    assert metrics.icon_readability_score >= 70


def test_ak47_archetype_inference() -> None:
    assert infer_archetype(REGRESSION_PROMPT) == "ak47"
    assert infer_archetype("modern assault rifle") == "rifle"


def test_ak47_from_concept_mock(tmp_path: Path) -> None:
    """Concept image + firearm archetype skips Hunyuan/mock mesh — pure primitives."""
    if not AK47_CONCEPT.is_file():
        pytest.skip("AK47 concept image not present")

    run_dir = tmp_path / "ak47_candidate"
    result = generate_model_candidate(
        REGRESSION_PROMPT,
        "weapon",
        "mock",
        run_dir,
        max_faces=180,
        skip_dev_smoke=True,
        from_image=AK47_CONCEPT,
        concept_first=True,
        score=True,
        styler=StylerOptions(reconstruct="primitive", archetype="ak47", ai_generated=True),
    )

    assert result.backend == "primitive"
    assert result.metadata.get("archetype") == "ak47"
    assert result.metadata.get("primitiveReconstruction") is True
    assert result.metadata.get("rawAiMeshUsedAsGeometry") is False
    assert not (run_dir / "_generation").exists()
    assert (run_dir / "concept" / "concept.png").is_file()
    assert (run_dir / "previews" / "icon_64.png").is_file()
    assert len(set(result.encode.decoded.face_colors)) >= 4
    assert result.metadata.get("iconScoreAfter", 0) >= 70


def test_gen_primitive_ak47_no_hunyuan(tmp_path: Path) -> None:
    """Direct primitive path — no AI mesh backend."""
    run_dir = tmp_path / "primitive_ak47"
    result = generate_primitive_candidate(
        "weapon",
        "ak47",
        run_dir,
        user_prompt=REGRESSION_PROMPT,
        max_faces=180,
        skip_dev_smoke=True,
        score=True,
    )
    assert result.backend == "primitive"
    assert result.metadata.get("primitiveReconstruction") is True
    assert result.metadata.get("rawAiMeshUsedAsGeometry") is False
    assert len(set(result.encode.decoded.face_colors)) >= 4
    assert (run_dir / "raw" / "SOURCE.txt").is_file()
    assert result.metadata.get("iconScoreAfter", 0) >= 70


def test_gen_primitive_cli_ak47(tmp_path: Path) -> None:
    """CLI: python -m src.text2rs gen primitive weapon ak47"""
    out = tmp_path / "cli_primitive_ak47"
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.text2rs",
            "gen",
            "primitive",
            "weapon",
            "ak47",
            "--out",
            str(out),
            "--skip-dev-smoke",
        ],
        cwd=str(PIPELINE_ROOT),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "Primitive reconstruction: TRUE" in proc.stdout
    assert "Raw AI mesh used as geometry: FALSE" in proc.stdout
    meta = json.loads((out / "metadata.json").read_text(encoding="utf-8"))
    assert meta.get("primitiveReconstruction") is True
    assert meta.get("rawAiMeshUsedAsGeometry") is False


def test_trimesh_to_rs_model_primitive(tmp_path: Path) -> None:
    previews = tmp_path / "previews"
    previews.mkdir()
    result = trimesh_to_rs_model(
        "weapon",
        max_faces=180,
        styler=StylerOptions.for_primitive("ak47"),
        user_prompt=REGRESSION_PROMPT,
        previews_dir=previews,
        archetype="ak47",
    )
    assert result.metadata.get("primitiveReconstruction") is True
    assert result.metadata.get("rawAiMeshUsedAsGeometry") is False
    assert len(set(result.model.face_colors)) >= 4
