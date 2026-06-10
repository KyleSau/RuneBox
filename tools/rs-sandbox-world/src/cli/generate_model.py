"""Text prompt → AI mesh → RS2 model → client dev preview."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.cli_app.gen import run_model
from src.config import DEFAULT_BACKEND, DEFAULT_CLIENT_DIR, DEFAULT_DEV_MODEL_ID, GENERATED_DIR
from src.pipeline.candidate import slugify


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate RS2 model from text prompt via AI backend.")
    parser.add_argument("--prompt", type=str, required=True, help="Short object/weapon description")
    parser.add_argument(
        "--target",
        type=str,
        default="weapon",
        choices=["weapon", "shield", "helmet", "body", "legs", "object", "npc", "mount", "item"],
    )
    parser.add_argument("--backend", type=str, default=DEFAULT_BACKEND, help="mock | hunyuan3d | shap-e | triposr")
    parser.add_argument("--max-faces", type=int, help="Face budget (default from target profile)")
    parser.add_argument("--model-id", type=int, help="Dev model id for encoded output filename")
    parser.add_argument("--client-dir", type=Path, help="Java client root (for dev-models copy)")
    parser.add_argument(
        "--client-dev",
        action="store_true",
        help=f"Copy to client dev-models (default id {DEFAULT_DEV_MODEL_ID}, client {DEFAULT_CLIENT_DIR.name})",
    )
    parser.add_argument("--out", type=Path, help="Output run directory (default: outputs/generated/<slug>)")
    parser.add_argument("--skip-dev-smoke", action="store_true", help="Skip DevModelSmoke subprocess check")
    parser.add_argument("--from-image", type=Path, help="Concept image for image-to-3D")
    parser.add_argument("--concept-first", action="store_true", help="Generate RS concept image first")
    parser.add_argument("--concept-backend", type=str, help="openai | manual | local")
    args = parser.parse_args(argv)

    return run_model(
        args.target,
        args.prompt,
        backend=args.backend,
        max_faces=args.max_faces,
        out=args.out or (GENERATED_DIR / slugify(args.prompt)),
        model_id=args.model_id,
        client_dir=args.client_dir,
        client_dev=args.client_dev,
        skip_dev_smoke=args.skip_dev_smoke,
        from_image=args.from_image,
        concept_first=args.concept_first,
        concept_backend=args.concept_backend,
    )


if __name__ == "__main__":
    raise SystemExit(main())
