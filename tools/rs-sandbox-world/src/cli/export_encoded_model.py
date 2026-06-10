"""Export gzip-wrapped encoded model bytes suitable for idx1 storage."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.cache.cache_locator import CacheReader
from src.config import DEFAULT_CACHE_DIR, discover_cache_dir
from src.rs2.model_decoder import decode_model
from src.rs2.model_encoder import encode_model, wrap_model_gzip


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Encode cache model and write gzip-wrapped idx1 bytes.")
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE_DIR, help="Path to cache directory")
    parser.add_argument("--model-id", type=int, required=True, help="Model file id in idx1")
    parser.add_argument("--out", type=Path, required=True, help="Output .dat.gz path")
    parser.add_argument("--raw-out", type=Path, help="Optional decompressed .dat path")
    args = parser.parse_args(argv)

    cache = CacheReader(discover_cache_dir(args.cache))
    raw = cache.read_model(args.model_id)
    if raw is None:
        print(f"Model {args.model_id} not found in cache.", file=sys.stderr)
        return 1

    model = decode_model(args.model_id, raw)
    if model is None:
        print(f"Model {args.model_id} could not be decoded.", file=sys.stderr)
        return 1

    encoded = encode_model(model)
    gz = wrap_model_gzip(encoded)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(gz)
    print(f"Wrote {args.out} ({len(gz)} bytes gzip, {len(encoded)} bytes decompressed)")

    if args.raw_out:
        args.raw_out.parent.mkdir(parents=True, exist_ok=True)
        args.raw_out.write_bytes(encoded)
        print(f"Wrote {args.raw_out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
