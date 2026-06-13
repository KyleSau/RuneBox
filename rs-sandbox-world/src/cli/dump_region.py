"""Dump decoded region terrain from cache idx4."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from src.cache.cache_locator import CacheReader
from src.cache.map_index import (
    default_xtea_keys_path,
    load_xtea_keys,
    load_map_file_index,
    read_landscape_bytes,
    read_terrain_bytes,
    region_id,
    resolve_landscape_file_id,
    terrain_file_id,
)
from src.config import DEFAULT_CACHE_DIR, cache_setup_hint, discover_cache_dir
from src.rs2.landscape_decoder import decode_landscape
from src.rs2.map_decoder import REGION_SIZE, decode_terrain_map


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dump decoded 317/377 region terrain tiles.")
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE_DIR, help="Cache directory")
    parser.add_argument("--region-x", type=int, required=True, help="Region X (absX >> 6)")
    parser.add_argument("--region-y", type=int, required=True, help="Region Y (absY >> 6)")
    parser.add_argument("--plane", type=int, default=0, help="Height plane (0-3)")
    parser.add_argument("--xtea-keys", type=Path, help="XTEA keys JSON (default: data/xtea_keys.json or XTEA_KEYS_PATH)")
    parser.add_argument("--out", type=Path, help="Write JSON summary to this path")
    parser.add_argument("--show-landscape", action="store_true", help="Also report landscape file presence")
    args = parser.parse_args(argv)

    cache_dir = discover_cache_dir(args.cache)
    if not (cache_dir / "main_file_cache.dat").exists():
        print(str(cache_setup_hint()), file=sys.stderr)
        return 1

    cache = CacheReader(cache_dir)
    rx, ry = args.region_x, args.region_y
    terrain_raw = read_terrain_bytes(cache, rx, ry)
    if not terrain_raw:
        print(
            f"No terrain map at idx4 file {terrain_file_id(rx, ry)} for region ({rx}, {ry}).",
            file=sys.stderr,
        )
        return 1

    region = decode_terrain_map(terrain_raw, rx, ry)
    summary = region.to_summary_dict(plane=args.plane)

    print(f"Region ({rx}, {ry}) id={region_id(rx, ry)} origin=({region.origin_x},{region.origin_y})")
    print(f"  terrain file: idx4:{terrain_file_id(rx, ry)} ({len(terrain_raw)} bytes decompressed)")
    print(f"  plane {args.plane}: sample heights [0,0]={summary['heights'][0][0]} [32,32]={summary['heights'][32][32]}")
    blocked = sum(1 for row in summary["blocked"] for b in row if b)
    print(f"  blocked tiles (settings&1): {blocked}/{REGION_SIZE * REGION_SIZE}")

    if args.show_landscape:
        keys = load_xtea_keys(args.xtea_keys or default_xtea_keys_path())
        map_index = load_map_file_index(cache)
        land_fid = resolve_landscape_file_id(cache, rx, ry, index=map_index)
        land = read_landscape_bytes(cache, rx, ry, xtea_keys=keys, index=map_index)
        if land:
            objs = decode_landscape(land, rx, ry)
            status = f"{len(land)} bytes, {len(objs or [])} objects"
        else:
            status = "missing or XTEA failed"
        fid_label = f"idx4:{land_fid}" if land_fid is not None else "not found"
        print(f"  landscape file: {fid_label} -> {status}")

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(f"Wrote {args.out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
