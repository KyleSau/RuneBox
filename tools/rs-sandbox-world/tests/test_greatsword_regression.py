"""Greatsword primitive reconstruction — deterministic two-handed sword."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from src.mesh.encode_pipeline import encode_rs_model
from src.mesh.reconstruct import StylerOptions
from src.mesh.rs_style import mesh_to_rs_model, save_rs2model_json
from src.mesh.weapon_rebuilder import build_weapon, infer_archetype
from src.pipeline.primitive_candidate import generate_primitive_candidate
from src.quality.report import score_candidate_dir

PIPELINE_ROOT = Path(__file__).resolve().parents[1]

REGRESSION_PROMPT = (
    "a large powerful two hand sword, greatsword, chunky low-poly blade, "
    "dark brown two-handed grip, steel crossguard, old RuneScape 2005 style"
)


@pytest.fixture
def greatsword_mesh() -> "object":
    return build_weapon("greatsword")


def test_greatsword_primitive_mesh_stats(greatsword_mesh) -> None:
    colors = {tuple(int(x) for x in c[:3]) for c in greatsword_mesh.visual.face_colors}
    assert len(greatsword_mesh.faces) >= 60
    assert 6 <= len(colors) <= 10


def test_greatsword_archetype_inference() -> None:
    assert infer_archetype(REGRESSION_PROMPT) == "greatsword"
    assert infer_archetype("a large powerful two hand sword", "greatsword") == "greatsword"


def test_greatsword_primitive_pipeline(greatsword_mesh, tmp_path: Path) -> None:
    glb = tmp_path / "greatsword.glb"
    greatsword_mesh.export(glb)
    previews = tmp_path / "previews"
    result = mesh_to_rs_model(
        glb,
        "weapon",
        max_faces=120,
        styler=StylerOptions.for_primitive("greatsword"),
        user_prompt=REGRESSION_PROMPT,
        previews_dir=previews,
    )
    assert result.metadata.get("archetype") == "greatsword"
    assert result.metadata.get("primitiveReconstruction") is True
    assert result.metadata.get("rawAiMeshUsedAsGeometry") is False
    for size in (128, 64, 32):
        assert (previews / f"icon_{size}.png").is_file()


def test_greatsword_quality_scores(greatsword_mesh, tmp_path: Path) -> None:
    previews = tmp_path / "previews"
    previews.mkdir()
    glb = tmp_path / "src.glb"
    greatsword_mesh.export(glb)
    result = mesh_to_rs_model(
        glb,
        "weapon",
        max_faces=120,
        styler=StylerOptions.for_primitive("greatsword"),
        user_prompt=REGRESSION_PROMPT,
        previews_dir=previews,
    )
    encode_rs_model(result.model, tmp_path / "encoded" / "model.dat", preview_path=previews / "preview.png")
    (tmp_path / "metadata.json").write_text(
        json.dumps(
            {
                "userPrompt": REGRESSION_PROMPT,
                "target": "weapon",
                "backend": "primitive",
                "archetype": "greatsword",
                "primitiveReconstruction": True,
                "rawAiMeshUsedAsGeometry": False,
                "vertexCount": len(result.model.vertices),
                "faceCount": len(result.model.faces),
                "encodeDecodePass": True,
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "intermediate").mkdir(exist_ok=True)
    save_rs2model_json(tmp_path / "intermediate" / "normalized.rs2model.json", result.model, result.metadata)

    metrics, style = score_candidate_dir(tmp_path)
    report = (tmp_path / "quality_report.txt").read_text(encoding="utf-8")
    assert "greatsword" in report.lower()
    assert metrics.icon_readability_score is not None
    assert metrics.icon_readability_score >= 70
    assert style.score >= 70
    assert 6 <= metrics.unique_face_colors <= 12
    assert 60 <= metrics.face_count <= 120


def test_gen_primitive_greatsword_candidate(tmp_path: Path) -> None:
    run_dir = tmp_path / "greatsword_candidate"
    result = generate_primitive_candidate(
        "weapon",
        "greatsword",
        run_dir,
        user_prompt=REGRESSION_PROMPT,
        max_faces=120,
        skip_dev_smoke=True,
        score=True,
    )
    assert result.backend == "primitive"
    assert result.metadata.get("archetype") == "greatsword"
    assert result.metadata.get("primitiveReconstruction") is True
    assert result.metadata.get("rawAiMeshUsedAsGeometry") is False
    assert (run_dir / "previews" / "preview.png").is_file()
    for size in (128, 64, 32):
        assert (run_dir / "previews" / f"icon_{size}.png").is_file()
    assert (run_dir / "raw" / "SOURCE.txt").is_file()
    assert result.metadata.get("iconScoreAfter", 0) >= 70
    assert 60 <= result.metadata.get("faceCount", 0) <= 120


def test_gen_primitive_cli_greatsword(tmp_path: Path) -> None:
    out = tmp_path / "cli_greatsword"
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.text2rs",
            "gen",
            "primitive",
            "weapon",
            "greatsword",
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
    assert meta.get("archetype") == "greatsword"
    report = (out / "quality_report.txt").read_text(encoding="utf-8")
    assert "greatsword" in report.lower()
