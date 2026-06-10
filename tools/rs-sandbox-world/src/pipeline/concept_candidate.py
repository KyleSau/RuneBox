"""Concept-first model candidate generation."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from src.ai.concept_backend import (
    ConceptBackendNotConfiguredError,
    ConceptResult,
    get_concept_backend,
    write_concept_artifacts,
)
from src.ai.generator_backend import (
    BackendNotConfiguredError,
    GenerationResult,
    ImageInputNotSupportedError,
    get_backend,
)
from src.ai.prompt_templates import build_concept_prompt, build_prompt
from src.config import DEFAULT_CONCEPT_BACKEND
from src.pipeline.candidate import (
    CandidateResult,
    _save_raw_ai_preview,
    ensure_layout,
    generate_candidate,
    run_dev_model_smoke,
)
from src.mesh.encode_pipeline import encode_rs_model
from src.mesh.reconstruct import StylerOptions
from src.mesh.rs_style import mesh_to_rs_model, save_rs2model_json
from src.mesh.weapon_rebuilder import infer_archetype, is_firearm_archetype
from src.pipeline.styler_options import build_styler_options
from src.quality.report import score_candidate_dir


def generate_standalone_concept(
    description: str,
    target: str,
    backend_name: str,
    out_dir: Path,
    *,
    from_image: Path | None = None,
) -> ConceptResult:
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    concept_prompt = build_concept_prompt(description, target)

    backend = get_concept_backend(
        backend_name,
        image_path=from_image.resolve() if from_image else None,
    )
    result = backend.generate(concept_prompt, out_dir)
    write_concept_artifacts(out_dir, result, user_prompt=description, target=target)
    return result


def generate_model_candidate(
    user_prompt: str,
    target: str,
    backend_name: str,
    run_dir: Path,
    *,
    max_faces: int | None = None,
    model_id: int | None = None,
    client_dir: Path | None = None,
    copy_to_client: bool = False,
    skip_dev_smoke: bool = True,
    variant_index: int | None = None,
    from_image: Path | None = None,
    concept_first: bool = False,
    concept_backend: str | None = None,
    score: bool = True,
    styler: StylerOptions | None = None,
) -> CandidateResult:
    run_dir = run_dir.resolve()
    user_prompt = user_prompt.strip()
    full_prompt = build_prompt(user_prompt, target)

    styler_opts = styler or build_styler_options(ai_generated=True)
    effective_archetype = (
        styler_opts.archetype
        if styler_opts.archetype not in ("auto", "")
        else infer_archetype(user_prompt, None)
    )
    use_primitive_firearm = is_firearm_archetype(effective_archetype) and styler_opts.reconstruct != "off"

    if styler_opts.primitive_only or use_primitive_firearm:
        from src.pipeline.primitive_candidate import generate_primitive_candidate

        if not effective_archetype:
            raise ValueError("Firearm/primitive generation requires --archetype (e.g. ak47, handgonne)")
        result = generate_primitive_candidate(
            target,
            effective_archetype,
            run_dir,
            user_prompt=user_prompt,
            max_faces=max_faces,
            model_id=model_id,
            client_dir=client_dir,
            copy_to_client=copy_to_client,
            skip_dev_smoke=skip_dev_smoke,
            from_image=from_image.resolve() if from_image else None,
            score=score,
        )
        return CandidateResult(
            run_dir=result.run_dir,
            user_prompt=result.user_prompt,
            full_prompt=result.full_prompt,
            target=result.target,
            backend=result.backend,
            metadata=result.metadata,
            encode=result.encode,
            client_dev_path=result.client_dev_path,
            dev_smoke_pass=result.dev_smoke_pass,
        )

    concept_image: Path | None = None
    concept_backend_used: str | None = None
    concept_meta: dict | None = None
    concept_prompt_text: str | None = None

    if from_image is not None:
        concept_dir = run_dir / "concept"
        concept_prompt_text = build_concept_prompt(user_prompt, target)
        backend = get_concept_backend("manual", image_path=from_image.resolve())
        concept_result = backend.generate(concept_prompt_text, concept_dir)
        concept_image = write_concept_artifacts(
            concept_dir, concept_result, user_prompt=user_prompt, target=target
        )
        concept_backend_used = "manual"
        concept_meta = concept_result.metadata
    elif concept_first:
        cb = concept_backend or DEFAULT_CONCEPT_BACKEND
        if cb == "manual":
            raise ConceptBackendNotConfiguredError(
                "Concept-first with manual backend requires --from-image.\n"
                "Use --concept-backend openai or set TEXT2RS_CONCEPT_BACKEND=openai in .env.local."
            )
        concept_dir = run_dir / "concept"
        concept_prompt_text = build_concept_prompt(user_prompt, target)
        backend = get_concept_backend(cb)
        concept_result = backend.generate(concept_prompt_text, concept_dir)
        concept_image = write_concept_artifacts(
            concept_dir, concept_result, user_prompt=user_prompt, target=target
        )
        concept_backend_used = cb
        concept_meta = concept_result.metadata

    # Text-only path — delegate to existing candidate generator.
    if concept_image is None:
        return generate_candidate(
            user_prompt,
            target,
            backend_name,
            run_dir,
            max_faces=max_faces,
            model_id=model_id,
            client_dir=client_dir,
            copy_to_client=copy_to_client,
            skip_dev_smoke=skip_dev_smoke,
            variant_index=variant_index,
            styler=styler_opts,
            score=score,
        )

    # Concept + image-to-3D path.
    raw_work_dir = run_dir / "_generation"
    raw_work_dir.mkdir(parents=True, exist_ok=True)

    mesh_backend = get_backend(backend_name)
    if concept_image and not mesh_backend.supports_image_input:
        raise ImageInputNotSupportedError(
            f"Backend {backend_name!r} does not support image input.\n"
            "Use --backend hunyuan3d for concept-first generation."
        )

    try:
        gen: GenerationResult = mesh_backend.generate(
            full_prompt, raw_work_dir, image_path=concept_image
        )
    except ImageInputNotSupportedError:
        raise
    except BackendNotConfiguredError:
        raise

    layout = ensure_layout(run_dir, gen.raw_mesh_path)
    raw_mesh = layout["raw"] / gen.raw_mesh_path.name

    (run_dir / "prompt.txt").write_text(user_prompt + "\n", encoding="utf-8")
    (run_dir / "full_prompt.txt").write_text(full_prompt + "\n", encoding="utf-8")
    if concept_prompt_text and not (run_dir / "concept" / "concept_prompt.txt").is_file():
        (run_dir / "concept" / "concept_prompt.txt").write_text(concept_prompt_text + "\n", encoding="utf-8")

    raw_preview = _save_raw_ai_preview(raw_mesh, layout["previews"]) if styler_opts.ai_generated else None

    normalized = mesh_to_rs_model(
        raw_mesh,
        target,
        max_faces,
        styler=styler_opts,
        user_prompt=user_prompt,
        previews_dir=layout["previews"],
    )
    json_path = layout["intermediate"] / "normalized.rs2model.json"
    save_rs2model_json(json_path, normalized.model, normalized.metadata)

    encoded_name = f"model_{model_id}.dat" if model_id is not None else "model.dat"
    gzip_name = f"model_{model_id}.dat.gz" if model_id is not None else "model.dat.gz"
    dat_path = layout["encoded"] / encoded_name
    gzip_path = layout["encoded"] / gzip_name
    preview_path = layout["previews"] / "preview.png"

    enc = encode_rs_model(
        normalized.model,
        dat_path,
        gzip_out=gzip_path,
        preview_path=preview_path,
    )

    client_dev_path: Path | None = None
    dev_smoke_pass: bool | None = None
    if copy_to_client and client_dir is not None and model_id is not None:
        import shutil

        client_dev_path = client_dir.resolve() / "dev-models" / gzip_name
        client_dev_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(gzip_path, client_dev_path)
        if not skip_dev_smoke:
            dev_smoke_pass = run_dev_model_smoke(client_dir, model_id)

    metadata = {
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "userPrompt": user_prompt,
        "fullPrompt": full_prompt,
        "target": target,
        "backend": gen.backend,
        "conceptBackend": concept_backend_used,
        "conceptFirst": concept_first or from_image is not None,
        "conceptImage": str(concept_image.resolve()) if concept_image else None,
        "maxFaces": max_faces,
        "modelId": model_id,
        "variantIndex": variant_index,
        "rawMesh": str(raw_mesh.resolve()),
        "normalizedJson": str(json_path.resolve()),
        "encodedDat": str(dat_path.resolve()),
        "encodedGzip": str(gzip_path.resolve()),
        "preview": str(preview_path.resolve()),
        "previewRaw": raw_preview,
        "clientDevModel": str(client_dev_path.resolve()) if client_dev_path else None,
        "generation": gen.metadata,
        "conceptGeneration": concept_meta,
        "normalizationWarnings": normalized.warnings,
        "repairActions": normalized.metadata.get("repairActions", []),
        "archetype": normalized.metadata.get("archetype"),
        "iconScoreBefore": normalized.metadata.get("iconScoreBefore"),
        "iconScoreAfter": normalized.metadata.get("iconScoreAfter"),
        "styler": normalized.metadata.get("styler"),
        "vertexCount": len(enc.decoded.vertices),
        "faceCount": len(enc.decoded.faces),
        "encodeDecodePass": True,
        "devSmokePass": dev_smoke_pass,
    }
    (run_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    result = CandidateResult(
        run_dir=run_dir,
        user_prompt=user_prompt,
        full_prompt=full_prompt,
        target=target,
        backend=gen.backend,
        metadata=metadata,
        encode=enc,
        client_dev_path=client_dev_path,
        dev_smoke_pass=dev_smoke_pass,
    )
    if score:
        score_candidate_dir(run_dir)
    return result
