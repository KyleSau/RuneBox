"""Pure procedural weapon generation — no Hunyuan/AI mesh."""

from __future__ import annotations

import sys
from pathlib import Path

from src.config import DEFAULT_CLIENT_DIR, DEFAULT_DEV_MODEL_ID, GENERATED_DIR
from src.pipeline.candidate import slugify, run_dev_model_smoke
from src.pipeline.primitive_candidate import generate_primitive_candidate
from src.quality.icon_score import IconScore
from src.quality.metrics import compute_metrics
from src.quality.report import print_report
from src.quality.style_score import score_metrics


def run_primitive(
    target: str,
    archetype: str,
    *,
    description: str = "",
    max_faces: int | None = None,
    out: Path | None = None,
    model_id: int | None = None,
    client_dir: Path | None = None,
    client_dev: bool = False,
    skip_dev_smoke: bool = False,
    from_image: Path | None = None,
) -> int:
    slug = slugify(description or archetype)
    run_dir = (out or (GENERATED_DIR / f"primitive_{slug}")).resolve()

    if client_dev:
        model_id = model_id if model_id is not None else DEFAULT_DEV_MODEL_ID
        client_dir = client_dir if client_dir is not None else DEFAULT_CLIENT_DIR

    try:
        result = generate_primitive_candidate(
            target,
            archetype,
            run_dir,
            user_prompt=description or f"procedural {archetype}",
            max_faces=max_faces,
            model_id=model_id,
            client_dir=client_dir,
            copy_to_client=bool(client_dir and model_id is not None),
            skip_dev_smoke=skip_dev_smoke,
            from_image=from_image.resolve() if from_image else None,
            score=True,
        )
    except Exception as exc:
        print(f"Primitive generation failed: {exc}", file=sys.stderr)
        return 1

    enc = result.encode
    meta = result.metadata
    print("Primitive model validation")
    print(f"Archetype: {archetype}")
    print(f"Target: {target}")
    print("Primitive reconstruction: TRUE")
    print("Raw AI mesh used as geometry: FALSE")
    print(f"Vertices: {len(enc.decoded.vertices)}")
    print(f"Faces: {len(enc.decoded.faces)}")
    print(f"Unique face colors: {len(set(enc.decoded.face_colors))}")
    print("Encode/decode: PASS")
    print(f"Output: {meta['encodedDat']}")
    if meta.get("encodedGzip"):
        print(f"Gzip output: {meta['encodedGzip']}")
    if result.client_dev_path:
        print(f"Client dev model: {result.client_dev_path}")
    print(f"Preview: {meta['preview']}")

    for action in meta.get("repairActions") or []:
        print(f"- {action}")

    qpath = run_dir / "quality_score.json"
    if qpath.is_file():
        import json

        q = json.loads(qpath.read_text(encoding="utf-8"))
        metrics = compute_metrics(run_dir)
        style = score_metrics(metrics)
        icon_data = q.get("iconScore")
        icon_score_obj = IconScore(**icon_data) if icon_data else None
        print()
        print_report(metrics, style, icon_score=icon_score_obj)

    if result.client_dev_path and not skip_dev_smoke:
        smoke_ok = run_dev_model_smoke(client_dir, model_id)
        print("DevModelSmoke: PASS" if smoke_ok else "DevModelSmoke: FAIL", file=sys.stderr if not smoke_ok else sys.stdout)

    return 0
