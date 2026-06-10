"""Generate RS2 candidates purely from procedural weapon primitives (no AI mesh)."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from src.ai.concept_backend import get_concept_backend, write_concept_artifacts
from src.ai.prompt_templates import build_concept_prompt, build_prompt
from src.config import DEFAULT_DEV_MODEL_ID
from src.mesh.encode_pipeline import encode_rs_model
from src.mesh.profiles import get_asset_profile
from src.mesh.reconstruct import StylerOptions, save_reconstructed_preview
from src.mesh.rs_style import trimesh_to_rs_model, save_rs2model_json
from src.mesh.weapon_rebuilder import can_rebuild, infer_archetype
from src.pipeline.candidate import CandidateResult, ensure_layout, run_dev_model_smoke, slugify
from src.quality.report import score_candidate_dir


def generate_primitive_candidate(
    target: str,
    archetype: str,
    run_dir: Path,
    *,
    user_prompt: str = "",
    max_faces: int | None = None,
    model_id: int | None = None,
    client_dir: Path | None = None,
    copy_to_client: bool = False,
    skip_dev_smoke: bool = True,
    from_image: Path | None = None,
    score: bool = True,
) -> CandidateResult:
    archetype = archetype.lower().strip()
    if not can_rebuild(archetype):
        raise ValueError(f"Unknown or unsupported primitive archetype: {archetype!r}")

    run_dir = run_dir.resolve()
    run_dir.mkdir(parents=True, exist_ok=True)

    user_prompt = user_prompt.strip() or f"procedural {archetype} weapon"
    full_prompt = build_prompt(user_prompt, target)

    (run_dir / "prompt.txt").write_text(user_prompt + "\n", encoding="utf-8")
    (run_dir / "full_prompt.txt").write_text(full_prompt + "\n", encoding="utf-8")

    concept_image: Path | None = None
    if from_image is not None:
        concept_dir = run_dir / "concept"
        concept_prompt = build_concept_prompt(user_prompt, target)
        backend = get_concept_backend("manual", image_path=from_image.resolve())
        concept_result = backend.generate(concept_prompt, concept_dir)
        concept_image = write_concept_artifacts(
            concept_dir, concept_result, user_prompt=user_prompt, target=target
        )

    layout = ensure_layout(run_dir, _write_primitive_stub(run_dir, archetype))
    previews_dir = layout["previews"]
    intermediate = layout["intermediate"]

    styler = StylerOptions.for_primitive(archetype)
    profile = get_asset_profile(target, archetype)
    face_budget = max_faces if max_faces is not None else profile.max_faces_default

    normalized = trimesh_to_rs_model(
        target,
        face_budget,
        styler=styler,
        user_prompt=user_prompt,
        previews_dir=previews_dir,
        archetype=archetype,
    )
    save_reconstructed_preview(
        _load_primitive_glb(layout["raw"] / f"primitive_{archetype}.glb"),
        intermediate / "reconstructed.glb",
    )

    json_path = intermediate / "normalized.rs2model.json"
    save_rs2model_json(json_path, normalized.model, normalized.metadata)

    encoded_name = f"model_{model_id}.dat" if model_id is not None else "model.dat"
    gzip_name = f"model_{model_id}.dat.gz" if model_id is not None else "model.dat.gz"
    dat_path = layout["encoded"] / encoded_name
    gzip_path = layout["encoded"] / gzip_name
    preview_path = previews_dir / "preview.png"

    enc = encode_rs_model(normalized.model, dat_path, gzip_out=gzip_path, preview_path=preview_path)

    client_dev_path: Path | None = None
    dev_smoke_pass: bool | None = None
    if copy_to_client and client_dir is not None and model_id is not None:
        client_dev_path = client_dir.resolve() / "dev-models" / gzip_name
        client_dev_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(gzip_path, client_dev_path)
        if not skip_dev_smoke:
            dev_smoke_pass = run_dev_model_smoke(client_dir, model_id)

    report = normalized.styler_report
    metadata = {
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "userPrompt": user_prompt,
        "fullPrompt": full_prompt,
        "target": target,
        "backend": "primitive",
        "conceptBackend": "manual" if concept_image else None,
        "conceptImage": str(concept_image.resolve()) if concept_image else None,
        "archetype": archetype,
        "maxFaces": face_budget,
        "modelId": model_id,
        "normalizedJson": str(json_path.resolve()),
        "encodedDat": str(dat_path.resolve()),
        "encodedGzip": str(gzip_path.resolve()),
        "preview": str(preview_path.resolve()),
        "clientDevModel": str(client_dev_path.resolve()) if client_dev_path else None,
        "normalizationWarnings": normalized.warnings,
        "repairActions": normalized.metadata.get("repairActions", []),
        "primitiveReconstruction": True,
        "rawAiMeshUsedAsGeometry": False,
        "iconScoreBefore": normalized.metadata.get("iconScoreBefore"),
        "iconScoreAfter": normalized.metadata.get("iconScoreAfter"),
        "vertexCount": len(enc.decoded.vertices),
        "faceCount": len(enc.decoded.faces),
        "encodeDecodePass": True,
        "devSmokePass": dev_smoke_pass,
        "styler": normalized.metadata.get("styler"),
    }
    (run_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    result = CandidateResult(
        run_dir=run_dir,
        user_prompt=user_prompt,
        full_prompt=full_prompt,
        target=target,
        backend="primitive",
        metadata=metadata,
        encode=enc,
        client_dev_path=client_dev_path,
        dev_smoke_pass=dev_smoke_pass,
    )
    if score:
        score_candidate_dir(run_dir)
    return result


def _write_primitive_stub(run_dir: Path, archetype: str) -> Path:
    """Write a placeholder GLB documenting the procedural source (not used as geometry)."""
    from src.mesh.reconstruct import build_primitive_weapon

    raw_dir = run_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / f"primitive_{archetype}.glb"
    mesh, _, _ = build_primitive_weapon(archetype)
    mesh.export(path)
    (raw_dir / "SOURCE.txt").write_text(
        "Geometry from procedural primitives only. AI/Hunyuan mesh not used.\n",
        encoding="utf-8",
    )
    return path


def _load_primitive_glb(path: Path):
    import trimesh

    return trimesh.load(path, force="mesh")
