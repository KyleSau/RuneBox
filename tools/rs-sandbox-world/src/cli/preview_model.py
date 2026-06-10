"""Render a PNG preview of a cache model."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.cache.cache_locator import CacheReader
from src.config import DEFAULT_CACHE_DIR, resolve_cache_dir
from src.preview.render_preview import render_preview
from src.rs2.model_decoder import decode_model


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Preview a RS model from cache.")
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--model-id", type=int, required=True)
    parser.add_argument("--out", type=Path, required=True, help="Output PNG path")
    args = parser.parse_args(argv)

    cache = CacheReader(resolve_cache_dir(args.cache))
    raw = cache.read_model(args.model_id)
    if raw is None:
        print(f"Model {args.model_id} not found.", file=sys.stderr)
        return 1

    model = decode_model(args.model_id, raw)
    if model is None:
        print(f"Model {args.model_id} could not be decoded.", file=sys.stderr)
        return 1

    render_preview(model, args.out)
    print(f"Wrote preview {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
