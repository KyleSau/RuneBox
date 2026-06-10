"""Dump a model from cache to JSON and/or OBJ."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from src.cache.cache_locator import CacheReader
from src.config import DEFAULT_CACHE_DIR, discover_cache_dir
from src.preview.render_preview import export_obj
from src.rs2.model_decoder import decode_model


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dump a RS model from cache.")
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE_DIR, help="Path to cache directory")
    parser.add_argument("--model-id", type=int, required=True, help="Model file id in idx1")
    parser.add_argument("--out", type=Path, help="Output JSON path")
    parser.add_argument("--obj", type=Path, help="Optional OBJ export path")
    args = parser.parse_args(argv)

    cache = CacheReader(discover_cache_dir(args.cache))
    raw = cache.read_model(args.model_id)
    if raw is None:
        print(f"Model {args.model_id} not found or empty in cache.", file=sys.stderr)
        return 1

    model = decode_model(args.model_id, raw)
    if model is None:
        print(f"Model {args.model_id} could not be decoded.", file=sys.stderr)
        return 1

    payload = model.to_json_dict()
    print(
        f"model {args.model_id}: {payload['metadata']['vertexCount']} verts, "
        f"{payload['metadata']['faceCount']} faces, {payload['metadata']['rawByteSize']} bytes"
    )

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Wrote {args.out}")

    if args.obj:
        export_obj(model, args.obj)
        print(f"Wrote {args.obj}")

    if not args.out and not args.obj:
        print(json.dumps(payload, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
