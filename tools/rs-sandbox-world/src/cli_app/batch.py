"""Batch generation from a prompt file."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from src.ai.concept_backend import ConceptBackendNotConfiguredError
from src.ai.generator_backend import BackendNotConfiguredError
from src.config import DEFAULT_BACKEND, DEFAULT_CONCEPT_BACKEND, OUTPUT_ROOT, PIPELINE_ROOT
from src.mesh.reconstruct import StylerOptions
from src.pipeline.candidate import slugify
from src.pipeline.concept_candidate import generate_model_candidate
from src.pipeline.styler_options import build_styler_options
from src.quality.metrics import load_prompt_lines
from src.cli_app.gallery import build_gallery


def run_batch(
    target: str,
    prompts_file: Path,
    *,
    backend: str = DEFAULT_BACKEND,
    variants: int = 1,
    max_faces: int | None = None,
    out_dir: Path | None = None,
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
) -> Path:
    if concept_first:
        cb = concept_backend or DEFAULT_CONCEPT_BACKEND
        if cb in ("manual", "local"):
            raise ConceptBackendNotConfiguredError(
                "Concept-first batch requires --concept-backend openai or a configured local image backend.\n"
                "Alternatively use --from-image for single-candidate manual concept mode."
            )

    prompts_path = prompts_file.resolve()
    if not prompts_path.is_file():
        prompts_path = (PIPELINE_ROOT / prompts_file).resolve()
    if not prompts_path.is_file():
        raise FileNotFoundError(f"Prompt file not found: {prompts_file}")

    prompts = load_prompt_lines(prompts_path)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    batch_dir = (out_dir or (OUTPUT_ROOT / "generated_batch" / timestamp)).resolve()
    candidates_dir = batch_dir / "candidates"
    prompts_dir = batch_dir / "prompts"
    gallery_dir = batch_dir / "gallery"
    candidates_dir.mkdir(parents=True, exist_ok=True)
    prompts_dir.mkdir(parents=True, exist_ok=True)

    prompts_dir.joinpath(prompts_path.name).write_text(
        prompts_path.read_text(encoding="utf-8"), encoding="utf-8"
    )

    cb = concept_backend or (DEFAULT_CONCEPT_BACKEND if concept_first else None)
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

    batch_meta: dict = {
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "target": target,
        "backend": backend,
        "variants": variants,
        "maxFaces": max_faces,
        "conceptFirst": concept_first,
        "conceptBackend": cb,
        "archetype": archetype if archetype != "auto" else None,
        "reconstruct": reconstruct,
        "promptsFile": str(prompts_path),
        "batchDir": str(batch_dir),
        "candidates": [],
    }

    errors: list[str] = []
    for prompt in prompts:
        base_slug = slugify(prompt)
        for v in range(1, variants + 1):
            name = f"{base_slug}__v{v:03d}"
            run_dir = candidates_dir / name
            print(f"[batch] {name}: {prompt[:60]}...", file=sys.stderr)
            try:
                result = generate_model_candidate(
                    prompt,
                    target,
                    backend,
                    run_dir,
                    max_faces=max_faces,
                    skip_dev_smoke=True,
                    variant_index=v,
                    concept_first=concept_first,
                    concept_backend=cb,
                    score=True,
                    styler=styler,
                )
                from src.quality.metrics import compute_metrics
                from src.quality.style_score import score_metrics

                metrics = compute_metrics(run_dir)
                style = score_metrics(metrics)
                qpath = run_dir / "quality_score.json"
                icon_score = None
                if qpath.is_file():
                    icon_score = json.loads(qpath.read_text(encoding="utf-8")).get("iconScore", {}).get("score")
                batch_meta["candidates"].append(
                    {
                        "name": name,
                        "dir": str(run_dir),
                        "prompt": prompt,
                        "styleScore": style.score,
                        "iconScore": icon_score,
                        "vertexCount": metrics.vertex_count,
                        "faceCount": metrics.face_count,
                        "uniqueColors": metrics.unique_face_colors,
                        "archetype": result.metadata.get("archetype"),
                        "preview": result.metadata.get("preview"),
                        "previewRaw": result.metadata.get("previewRaw"),
                        "conceptImage": result.metadata.get("conceptImage"),
                        "conceptBackend": result.metadata.get("conceptBackend"),
                    }
                )
                print(
                    f"  -> style {style.score}/100, icon {icon_score or '?'}/100, {metrics.face_count} faces",
                    file=sys.stderr,
                )
            except BackendNotConfiguredError:
                raise
            except ConceptBackendNotConfiguredError:
                raise
            except Exception as exc:
                msg = f"{name}: {exc}"
                errors.append(msg)
                print(f"  -> FAIL: {exc}", file=sys.stderr)

    batch_meta["errors"] = errors
    (batch_dir / "batch_metadata.json").write_text(json.dumps(batch_meta, indent=2), encoding="utf-8")

    index_path = gallery_dir / "index.html"
    build_gallery(batch_dir, index_path)
    print(f"Batch complete: {batch_dir}", file=sys.stderr)
    print(f"Gallery: {index_path}", file=sys.stderr)
    if errors:
        print(f"{len(errors)} candidate(s) failed.", file=sys.stderr)
    return batch_dir
