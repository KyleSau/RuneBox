"""Try OpenRS2 validated XTEA keys against an encrypted landscape file."""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

from src.cache.cache_locator import CacheReader
from src.cache.map_index import (
    LANDSCAPE_FILE_OFFSET,
    load_map_file_index,
    prepare_map_bytes,
    region_id,
)
from src.rs2.landscape_decoder import decode_landscape
from src.rs2.xtea import decrypt


def main() -> None:
    rx = int(sys.argv[1]) if len(sys.argv) > 1 else 48
    ry = int(sys.argv[2]) if len(sys.argv) > 2 else 50
    cache_path = Path(sys.argv[3]) if len(sys.argv) > 3 else Path(
        r"..\cache-runescape-live-en-b377-2006-05-02-00-00-00-openrs2#657\cache"
    )

    cache = CacheReader(cache_path.resolve(), prefer_java=False)
    idx = load_map_file_index(cache)
    rid = region_id(rx, ry)
    fid = idx[rid] + LANDSCAPE_FILE_OFFSET
    raw = cache.read_file(4, fid)
    if not raw:
        print(f"No landscape file idx4:{fid}")
        sys.exit(1)
    prep = prepare_map_bytes(raw)
    print(f"Region ({rx},{ry}) rid={rid} file={fid} prep={len(prep)} bytes")
    if len(prep) % 8:
        print("Prepared data not XTEA-aligned")
        sys.exit(1)

    with urllib.request.urlopen(
        "https://archive.openrs2.org/keys/valid.json",
        timeout=120,
    ) as resp:
        keys: list[list[int]] = json.load(resp)
    print(f"Trying {len(keys)} keys...")

    for i, key in enumerate(keys):
        try:
            dec = decrypt(prep, key)
            objs = decode_landscape(dec, rx, ry)
        except Exception:
            continue
        if objs is not None:
            print(f"FOUND key {key} at index {i} -> {len(objs)} objects")
            print(json.dumps({f"{rx},{ry}": key}))
            return

    print("No key found")
    sys.exit(1)


if __name__ == "__main__":
    main()
