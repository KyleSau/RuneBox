"""Extract config archive (idx0 file 2) from a 377 cache."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.cache.cache_locator import CacheReader
from src.cache.config_locator import DEFAULT_CONFIG_ARCHIVE_ID
from src.cache.file_archive import FileArchive
from src.config import DEFAULT_CACHE_DIR, resolve_cache_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Extract config archive from cache idx0.")
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--out", type=Path, default=Path("outputs/intermediate/config_archive.dat"))
    parser.add_argument("--verify", action="store_true", help="Verify npc.dat/obj.dat exist after extract")
    args = parser.parse_args(argv)

    cache = CacheReader(resolve_cache_dir(args.cache))
    raw = cache.read_archive(DEFAULT_CONFIG_ARCHIVE_ID)
    if raw is None:
        print(
            f"Config archive (idx0 file {DEFAULT_CONFIG_ARCHIVE_ID}) is missing from {cache.paths.root}.\n"
            "This OpenRS2 dump is incomplete. Download a complete 377 cache from:\n"
            "  https://archive.openrs2.org/caches/657\n"
            "  https://runewiki.org/archive/cache/packed/377.zip",
            file=sys.stderr,
        )
        return 1

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(raw)
    print(f"Wrote config archive ({len(raw)} bytes) to {args.out}")

    if args.verify:
        arch = FileArchive.load(raw)
        for name in ("npc.dat", "npc.idx", "obj.dat", "obj.idx", "seq.dat"):
            data = arch.read(name)
            print(f"  {name}: {'OK' if data else 'MISSING'} ({len(data) if data else 0} bytes)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
