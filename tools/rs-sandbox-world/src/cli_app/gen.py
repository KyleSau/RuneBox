"""Single model / concept generation commands."""

from __future__ import annotations

import sys
from pathlib import Path

from src.ai.concept_backend import ConceptBackendNotConfiguredError
from src.ai.generator_backend import BackendNotConfiguredError, ImageInputNotSupportedError
from src.config import DEFAULT_BACKEND, DEFAULT_CLIENT_DIR, DEFAULT_CONCEPT_BACKEND, DEFAULT_DEV_MODEL_ID, GENERATED_DIR
from src.mesh.reconstruct import StylerOptions
from src.pipeline.candidate import slugify
from src.pipeline.concept_candidate import generate_model_candidate
from src.pipeline.styler_options import build_styler_options
from src.quality.icon_score import IconScore
from src.quality.report import print_report, score_candidate_dir


def run_model(
    target: str,
    description: str,
    *,
    backend: str = DEFAULT_BACKEND,
    max_faces: int | None = None,
    out: Path | None = None,
    model_id: int | None = None,
    client_dir: Path | None = None,
    client_dev: bool = False,
    skip_dev_smoke: bool = False,
    from_image: Path | None = None,
    concept_first: bool = False,
    concept_backend: str | None = None,
    reconstruct: str = "auto",
    archetype: str = "auto",
    repair_colors: bool = True,
    repair_silhouette: bool = True,
    icon_check: bool = True,
    target_colors: int | None = None,
    min_thickness_ratio: float = 0.08,
    max_axis_ratio: float = 8.0,
    force_readable_icon: bool = False,
) -> int:
    run_dir = (out or (GENERATED_DIR / slugify(description))).resolve()

    if client_dev:
        model_id = model_id if model_id is not None else DEFAULT_DEV_MODEL_ID
        client_dir = client_dir if client_dir is not None else DEFAULT_CLIENT_DIR

    cb = concept_backend
    if concept_first and cb is None:
        cb = DEFAULT_CONCEPT_BACKEND

    styler = build_styler_options(
        reconstruct=reconstruct,
        archetype=archetype,
        repair_colors=repair_colors,
        repair_silhouette=repair_silhouette,
        icon_check=icon_check,
        target_colors=target_colors,
        min_thickness_ratio=min_thickness_ratio,
        max_axis_ratio=max_axis_ratio,
        ai_generated=True,
        force_readable_icon=force_readable_icon,
    )

    try:
        result = generate_model_candidate(
            description,
            target,
            backend,
            run_dir,
            max_faces=max_faces,
            model_id=model_id,
            client_dir=client_dir,
            copy_to_client=bool(client_dir and model_id is not None),
            skip_dev_smoke=skip_dev_smoke,
            from_image=from_image.resolve() if from_image else None,
            concept_first=concept_first or from_image is not None,
            concept_backend=cb,
            score=True,
            styler=styler,
        )
    except (BackendNotConfiguredError, ConceptBackendNotConfiguredError, ImageInputNotSupportedError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Generation failed: {exc}", file=sys.stderr)
        return 1

    enc = result.encode
    colors_ok = len(enc.decoded.face_colors) == len(enc.decoded.faces)
    print("Generated model validation")
    print(f"Prompt: {result.user_prompt}")
    print(f"Backend: {result.backend}")
    if result.metadata.get("conceptBackend"):
        print(f"Concept backend: {result.metadata['conceptBackend']}")
    if result.metadata.get("archetype"):
        print(f"Archetype: {result.metadata['archetype']}")
    if result.metadata.get("primitiveReconstruction"):
        print("Primitive reconstruction: TRUE")
        print("Raw AI mesh used as geometry: FALSE")
    print(f"Target: {result.target}")
    if result.metadata.get("rawMesh"):
        print(f"Raw mesh: {result.metadata['rawMesh']}")
    print(f"Vertices: {len(enc.decoded.vertices)}")
    print(f"Faces: {len(enc.decoded.faces)}")
    print(f"Colors: {'OK' if colors_ok else 'FAIL'}")
    print("Encode/decode: PASS")
    print(f"Output: {result.metadata['encodedDat']}")
    print(f"Gzip output: {result.metadata['encodedGzip']}")
    if result.client_dev_path:
        print(f"Client dev model: {result.client_dev_path}")
    print(f"Preview: {result.metadata['preview']}")
    if result.metadata.get("conceptImage"):
        print(f"Concept: {result.metadata['conceptImage']}")
    if result.metadata.get("repairActions"):
        print("\nRepair actions:")
        for action in result.metadata["repairActions"]:
            print(f"- {action}")
    if result.metadata.get("iconScoreAfter") is not None:
        before = result.metadata.get("iconScoreBefore")
        after = result.metadata.get("iconScoreAfter")
        if before is not None and after is not None and before != after:
            print(f"Icon readability: {before} -> {after}")
        else:
            print(f"Icon readability: {after}/100")

    qpath = run_dir / "quality_score.json"
    if qpath.is_file():
        import json

        q = json.loads(qpath.read_text(encoding="utf-8"))
        from src.quality.metrics import compute_metrics
        from src.quality.style_score import score_metrics

        metrics = compute_metrics(run_dir)
        style = score_metrics(metrics)
        icon_data = q.get("iconScore")
        icon_score_obj = IconScore(**icon_data) if icon_data else None
        print()
        print_report(metrics, style, icon_score=icon_score_obj)

    if result.client_dev_path and not skip_dev_smoke:
        from src.pipeline.candidate import run_dev_model_smoke

        smoke_ok = run_dev_model_smoke(client_dir, model_id)
        if not smoke_ok:
            print("DevModelSmoke: FAIL (client may still work if compiled)", file=sys.stderr)
        else:
            print("DevModelSmoke: PASS")

    return 0
