"""Text2RS generation quality loop — batch, score, gallery, dev, concept."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.cli_app.batch import run_batch
from src.cli_app.concept import run_concept
from src.cli_app.dev import use_candidate
from src.cli_app.gallery import build_gallery
from src.cli_app.gen import run_model
from src.cli_app.primitive import run_primitive
from src.cli_app.score import run_score
from src.config import DEFAULT_BACKEND, DEFAULT_CONCEPT_BACKEND


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="text2rs", description="Text2RS quality loop")
    sub = parser.add_subparsers(dest="command", required=True)

    gen = sub.add_parser("gen", help="Generation commands")
    gen_sub = gen.add_subparsers(dest="gen_cmd", required=True)

    model = gen_sub.add_parser("model", help="Generate a single RS2 model candidate")
    model.add_argument("target", help="weapon, object, shield, …")
    model.add_argument("description", help="Short asset description")
    model.add_argument("--backend", default=DEFAULT_BACKEND)
    model.add_argument("--max-faces", type=int)
    model.add_argument("--out", type=Path)
    model.add_argument("--model-id", type=int)
    model.add_argument("--client-dir", type=Path)
    model.add_argument("--client-dev", action="store_true")
    model.add_argument("--skip-dev-smoke", action="store_true")
    model.add_argument("--from-image", type=Path)
    model.add_argument("--concept-first", action="store_true")
    model.add_argument("--concept-backend", type=str)
    model.add_argument(
        "--reconstruct",
        choices=["auto", "off", "weapon", "primitive"],
        default="auto",
        help="RS stylizer reconstruction mode (default: auto for AI generation)",
    )
    model.add_argument(
        "--archetype",
        default="auto",
        help="Weapon archetype: ak47, rifle, musket, handgonne, blunderbuss, greatsword, sword, axe, staff, halberd, auto",
    )
    model.add_argument("--repair-colors", action=argparse.BooleanOptionalAction, default=True)
    model.add_argument("--repair-silhouette", action=argparse.BooleanOptionalAction, default=True)
    model.add_argument("--icon-check", action=argparse.BooleanOptionalAction, default=True)
    model.add_argument("--force-readable-icon", action="store_true")
    model.add_argument("--target-colors", type=int)
    model.add_argument("--min-thickness-ratio", type=float, default=0.08)
    model.add_argument("--max-axis-ratio", type=float, default=8.0)

    concept = gen_sub.add_parser("concept", help="Generate RS concept image only")
    concept.add_argument("kind", choices=["model"])
    concept.add_argument("target")
    concept.add_argument("description")
    concept.add_argument("--backend", default=DEFAULT_CONCEPT_BACKEND)
    concept.add_argument("--out", type=Path)
    concept.add_argument("--from-image", type=Path)

    primitive = gen_sub.add_parser("primitive", help="Generate procedural weapon without AI mesh")
    primitive.add_argument("kind", choices=["weapon"])
    primitive.add_argument(
        "archetype",
        help="greatsword, sword, axe, staff, halberd, dagger, shield, bow (firearms: ak47, musket, …)",
    )
    primitive.add_argument("--description", default="", help="Optional label for output folder")
    primitive.add_argument("--max-faces", type=int)
    primitive.add_argument("--out", type=Path)
    primitive.add_argument("--model-id", type=int)
    primitive.add_argument("--client-dir", type=Path)
    primitive.add_argument("--client-dev", action="store_true")
    primitive.add_argument("--skip-dev-smoke", action="store_true")
    primitive.add_argument("--from-image", type=Path, help="Optional concept image (reference only)")

    batch = gen_sub.add_parser("batch", help="Batch generate from prompt file")
    batch.add_argument("kind", choices=["model"])
    batch.add_argument("target")
    batch.add_argument("prompts_file", type=Path)
    batch.add_argument("--backend", default=DEFAULT_BACKEND)
    batch.add_argument("--variants", type=int, default=1)
    batch.add_argument("--max-faces", type=int)
    batch.add_argument("--out", type=Path)
    batch.add_argument("--concept-first", action="store_true")
    batch.add_argument("--concept-backend", type=str)
    batch.add_argument("--reconstruct", choices=["auto", "off", "weapon", "primitive"], default="auto")
    batch.add_argument("--archetype", default="auto")
    batch.add_argument("--repair-colors", action=argparse.BooleanOptionalAction, default=True)
    batch.add_argument("--repair-silhouette", action=argparse.BooleanOptionalAction, default=True)
    batch.add_argument("--icon-check", action=argparse.BooleanOptionalAction, default=True)
    batch.add_argument("--force-readable-icon", action="store_true")
    batch.add_argument("--target-colors", type=int)
    batch.add_argument("--min-thickness-ratio", type=float, default=0.08)
    batch.add_argument("--max-axis-ratio", type=float, default=8.0)

    gallery = sub.add_parser("gallery", help="Build HTML gallery")
    gallery.add_argument("root", type=Path)
    gallery.add_argument("--out", type=Path, required=True)

    score = sub.add_parser("score", help="Score a candidate")
    score.add_argument("kind", choices=["model"])
    score.add_argument("candidate_dir", type=Path)

    dev = sub.add_parser("dev", help="Client dev-model helpers")
    dev_sub = dev.add_subparsers(dest="dev_cmd", required=True)
    use = dev_sub.add_parser("use-candidate", help="Copy candidate .dat.gz to client dev-models")
    use.add_argument("candidate_dir", type=Path)
    use.add_argument("--model-id", type=int, default=90000)
    use.add_argument("--client-dir", type=Path)
    use.add_argument("--skip-smoke", action="store_true")

    args = parser.parse_args(argv)

    if args.command == "gen" and args.gen_cmd == "model":
        return run_model(
            args.target,
            args.description,
            backend=args.backend,
            max_faces=args.max_faces,
            out=args.out,
            model_id=args.model_id,
            client_dir=args.client_dir,
            client_dev=args.client_dev,
            skip_dev_smoke=args.skip_dev_smoke,
            from_image=args.from_image,
            concept_first=args.concept_first,
            concept_backend=args.concept_backend,
            reconstruct=args.reconstruct,
            archetype=args.archetype,
            repair_colors=args.repair_colors,
            repair_silhouette=args.repair_silhouette,
            icon_check=args.icon_check,
            target_colors=args.target_colors,
            min_thickness_ratio=args.min_thickness_ratio,
            max_axis_ratio=args.max_axis_ratio,
            force_readable_icon=args.force_readable_icon,
        )

    if args.command == "gen" and args.gen_cmd == "primitive":
        return run_primitive(
            args.kind,
            args.archetype,
            description=args.description,
            max_faces=args.max_faces,
            out=args.out,
            model_id=args.model_id,
            client_dir=args.client_dir,
            client_dev=args.client_dev,
            skip_dev_smoke=args.skip_dev_smoke,
            from_image=args.from_image,
        )

    if args.command == "gen" and args.gen_cmd == "concept":
        try:
            run_concept(
                args.target,
                args.description,
                backend=args.backend,
                out=args.out,
                from_image=args.from_image,
            )
        except Exception as exc:
            print(str(exc), file=sys.stderr)
            return 1
        return 0

    if args.command == "gen" and args.gen_cmd == "batch":
        try:
            run_batch(
                args.target,
                args.prompts_file,
                backend=args.backend,
                variants=args.variants,
                max_faces=args.max_faces,
                out_dir=args.out,
                concept_first=args.concept_first,
                concept_backend=args.concept_backend,
                reconstruct=args.reconstruct,
                archetype=args.archetype,
                repair_colors=args.repair_colors,
                repair_silhouette=args.repair_silhouette,
                icon_check=args.icon_check,
                target_colors=args.target_colors,
                min_thickness_ratio=args.min_thickness_ratio,
                max_axis_ratio=args.max_axis_ratio,
                force_readable_icon=args.force_readable_icon,
            )
        except Exception as exc:
            print(str(exc), file=sys.stderr)
            return 1
        return 0

    if args.command == "gallery":
        build_gallery(args.root.resolve(), args.out.resolve())
        print(f"Gallery: {args.out.resolve()}")
        return 0

    if args.command == "score":
        return run_score(args.candidate_dir)

    if args.command == "dev" and args.dev_cmd == "use-candidate":
        return use_candidate(
            args.candidate_dir,
            model_id=args.model_id,
            client_dir=args.client_dir,
            run_smoke=not args.skip_smoke,
        )

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
