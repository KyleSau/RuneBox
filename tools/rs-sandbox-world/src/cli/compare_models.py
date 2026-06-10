"""Compare a cache model against encoded candidate bytes."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.cache.cache_locator import CacheReader
from src.config import DEFAULT_CACHE_DIR, discover_cache_dir
from src.rs2.model_compare import compare_models
from src.rs2.model_decoder import decode_model


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare original cache model vs encoded candidate.")
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE_DIR, help="Path to cache directory")
    parser.add_argument("--model-id", type=int, required=True, help="Original model id in idx1")
    parser.add_argument("--candidate", type=Path, required=True, help="Encoded model .dat or .dat.gz")
    parser.add_argument("--report", type=Path, help="Optional text report path")
    args = parser.parse_args(argv)

    cache = CacheReader(discover_cache_dir(args.cache))
    raw = cache.read_model(args.model_id)
    if raw is None:
        print(f"Model {args.model_id} not found in cache.", file=sys.stderr)
        return 1

    original = decode_model(args.model_id, raw)
    if original is None:
        print(f"Model {args.model_id} could not be decoded.", file=sys.stderr)
        return 1

    if not args.candidate.exists():
        print(f"Candidate not found: {args.candidate}", file=sys.stderr)
        return 1

    candidate_bytes = args.candidate.read_bytes()
    decoded = decode_model(args.model_id, candidate_bytes)
    if decoded is None:
        print("Candidate could not be decoded.", file=sys.stderr)
        return 1

    report = compare_models(original, decoded)
    text = report.format_text()
    print(text)

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text + "\n", encoding="utf-8")
        print(f"Wrote {args.report}")

    return 0 if report.passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
