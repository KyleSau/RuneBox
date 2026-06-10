"""Encode RS2 candidate JSON into model bytes."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.mesh.encode_pipeline import encode_rs_model, print_validation_report
from src.mesh.rs_style import load_rs2model_json


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Encode rs2model JSON to RS2 .dat bytes.")
    parser.add_argument("--input", type=Path, required=True, help="Input rs2model JSON")
    parser.add_argument("--out", type=Path, required=True, help="Output decompressed .dat")
    parser.add_argument("--gzip-out", type=Path, help="Optional gzip-wrapped output")
    parser.add_argument("--preview", type=Path, help="Optional PNG preview")
    parser.add_argument("--obj", type=Path, help="Optional OBJ export")
    args = parser.parse_args(argv)

    if not args.input.exists():
        print(f"Input not found: {args.input}", file=sys.stderr)
        return 1

    try:
        model, meta = load_rs2model_json(args.input)
    except Exception as exc:
        print(f"Failed to load JSON: {exc}", file=sys.stderr)
        return 1

    try:
        result = encode_rs_model(
            model,
            args.out,
            gzip_out=args.gzip_out,
            preview_path=args.preview,
            obj_path=args.obj,
        )
    except Exception as exc:
        print(f"Encode failed: {exc}", file=sys.stderr)
        return 1

    print_validation_report(result, args.out, args.gzip_out)

    if meta.get("warnings"):
        print("\nSource normalization warnings:")
        for warning in meta["warnings"]:
            print(f"  - {warning}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
