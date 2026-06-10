"""Decode cache model → encode → write roundtrip bytes."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.cache.cache_locator import CacheReader
from src.config import DEFAULT_CACHE_DIR, resolve_cache_dir
from src.rs2.model_compare import compare_models
from src.rs2.model_decoder import decode_model
from src.rs2.model_encoder import encode_model


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Encode a cache model and optionally validate roundtrip.")
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE_DIR, help="Path to cache directory")
    parser.add_argument("--model-id", type=int, required=True, help="Model file id in idx1")
    parser.add_argument("--out", type=Path, required=True, help="Output decompressed .dat path")
    parser.add_argument("--report", type=Path, help="Optional text report path")
    parser.add_argument("--no-compare", action="store_true", help="Skip structural compare")
    args = parser.parse_args(argv)

    cache = CacheReader(resolve_cache_dir(args.cache))
    raw = cache.read_model(args.model_id)
    if raw is None:
        print(f"Model {args.model_id} not found in cache.", file=sys.stderr)
        return 1

    original = decode_model(args.model_id, raw)
    if original is None:
        print(f"Model {args.model_id} could not be decoded.", file=sys.stderr)
        return 1

    encoded = encode_model(original)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(encoded)
    print(f"Wrote {args.out} ({len(encoded)} bytes decompressed)")

    if args.no_compare:
        return 0

    candidate = decode_model(args.model_id, encoded)
    if candidate is None:
        print("Encoded bytes could not be re-decoded.", file=sys.stderr)
        return 1

    report = compare_models(original, candidate)
    text = report.format_text()
    print()
    print(text)

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text + "\n", encoding="utf-8")
        print(f"Wrote {args.report}")

    return 0 if report.passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
