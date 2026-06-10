"""Normalize generic mesh files into RS2 candidate JSON."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.mesh.encode_pipeline import encode_rs_model, print_validation_report
from src.mesh.reconstruct import StylerOptions
from src.mesh.rs_style import mesh_to_rs_model, save_rs2model_json
from src.pipeline.styler_options import build_styler_options


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Normalize OBJ/PLY/GLB into RS2 candidate JSON.")
    parser.add_argument("--input", type=Path, required=True, help="Input mesh (.obj, .ply, .glb)")
    parser.add_argument(
        "--target",
        type=str,
        default="object",
        choices=["weapon", "shield", "helmet", "body", "legs", "object", "npc", "mount"],
        help="Target profile for scale/orientation",
    )
    parser.add_argument("--max-faces", type=int, help="Face budget (default from target profile)")
    parser.add_argument("--out", type=Path, help="Output rs2model JSON path")
    parser.add_argument("--encode", type=Path, help="Also encode to decompressed .dat")
    parser.add_argument("--gzip-out", type=Path, help="Also write gzip-wrapped .dat.gz")
    parser.add_argument("--preview", type=Path, help="Also render PNG preview")
    parser.add_argument("--obj", type=Path, help="Optional OBJ export of encoded model")
    parser.add_argument(
        "--reconstruct",
        choices=["auto", "off", "weapon", "primitive"],
        default="off",
        help="RS reconstruction (default off for manual mesh roundtrip)",
    )
    parser.add_argument("--archetype", default="auto")
    parser.add_argument("--repair-colors", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--repair-silhouette", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--icon-check", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--target-colors", type=int)
    parser.add_argument("--prompt", type=str, default="", help="Prompt text for archetype inference")
    args = parser.parse_args(argv)

    if not args.input.exists():
        print(f"Input not found: {args.input}", file=sys.stderr)
        return 1

    if args.out is None and args.encode is None:
        parser.error("Provide --out and/or --encode")

    styler = (
        build_styler_options(
            reconstruct=args.reconstruct,
            archetype=args.archetype,
            repair_colors=args.repair_colors,
            repair_silhouette=args.repair_silhouette,
            icon_check=args.icon_check,
            target_colors=args.target_colors,
            ai_generated=args.reconstruct != "off",
        )
        if args.reconstruct != "off" or args.repair_colors or args.repair_silhouette or args.icon_check
        else StylerOptions.for_roundtrip()
    )

    previews_dir = args.preview.parent if args.preview else None

    try:
        result = mesh_to_rs_model(
            args.input,
            args.target,
            args.max_faces,
            styler=styler,
            user_prompt=args.prompt,
            previews_dir=previews_dir,
        )
    except Exception as exc:
        print(f"Normalization failed: {exc}", file=sys.stderr)
        return 1

    if args.out:
        save_rs2model_json(args.out, result.model, result.metadata)
        print(f"Wrote {args.out} ({result.metadata['vertexCount']} verts, {result.metadata['faceCount']} faces)")

    if result.warnings:
        print("\nWarnings:")
        for warning in result.warnings:
            print(f"  - {warning}")

    if args.encode:
        enc = encode_rs_model(
            result.model,
            args.encode,
            gzip_out=args.gzip_out,
            preview_path=args.preview,
            obj_path=args.obj,
        )
        print()
        print_validation_report(enc, args.encode, args.gzip_out)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
