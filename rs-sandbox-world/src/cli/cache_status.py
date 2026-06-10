"""Report what is available in a 317/377 cache directory."""

from __future__ import annotations

import argparse
from pathlib import Path

from src.cache.cache_locator import CachePaths, CacheReader
from src.cache.config_locator import DEFAULT_CONFIG_ARCHIVE_ID, load_config_archive
from src.cache.file_archive import FileArchive
from src.cache import java_bridge
from src.cache.model_index import load_model_count
from src.config import DEFAULT_CACHE_DIR, cache_setup_hint, discover_cache_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Summarize cache contents and gaps.")
    parser.add_argument(
        "--cache",
        type=Path,
        default=DEFAULT_CACHE_DIR,
        help="Cache directory (parent folder or .../cache with main_file_cache.dat)",
    )
    args = parser.parse_args(argv)

    cache_dir = discover_cache_dir(args.cache)
    if not (cache_dir / "main_file_cache.dat").exists():
        print(f"No cache at {cache_dir}")
        print(cache_setup_hint())
        return 1
    paths = CachePaths.from_directory(cache_dir)
    cache = CacheReader(cache_dir)

    print(f"Cache path: {paths.root}")
    print(f"  main_file_cache.dat: {paths.dat.stat().st_size:,} bytes")
    backend = "Java client (FileStore/FileArchive/gzip)" if java_bridge.is_available() else "Python fallback"
    print(f"  cache backend: {backend}")
    print()

    print("Index stores:")
    labels = ["archives", "models", "animations", "midi/sound", "maps"]
    for i, label in enumerate(labels):
        fs = cache.filestores[i]
        count = fs.file_count()
        nonempty = sum(1 for fid in range(count) if fs.read(fid))
        print(f"  idx{i} ({label}): {nonempty}/{count} files")

    print()
    print("idx0 archives (title/config/versionlist bundle slots):")
    for fid in range(int(cache.filestores[0].file_count())):
        raw = cache.read_archive(fid)
        if raw is None:
            marker = "MISSING"
            if fid == DEFAULT_CONFIG_ARCHIVE_ID:
                marker += "  <-- config (npc.dat/obj.dat) expected here"
            elif fid == 0:
                marker += "  <-- title archive expected here"
            print(f"  file {fid}: {marker}")
            continue
        try:
            arch = FileArchive.load(raw)
            extras = []
            for name in ("npc.dat", "obj.dat", "model_version", "seq.dat"):
                member = None
                if java_bridge.is_available():
                    member = java_bridge.read_archive_member(cache_dir, fid, name)
                if member is None and arch:
                    member = arch.read(name)
                if member:
                    extras.append(name)
            extra = f" [{', '.join(extras)}]" if extras else ""
            print(f"  file {fid}: {len(raw):,} bytes, {arch.file_count} members{extra}")
        except Exception as exc:
            print(f"  file {fid}: {len(raw):,} bytes, not a FileArchive ({exc})")

    print()
    try:
        models = load_model_count(cache_dir)
        print(f"Models (idx1 via versionlist): {models:,} entries — dump/preview OK")
    except Exception as exc:
        print(f"Models: versionlist issue ({exc})")

    print()
    try:
        config = load_config_archive(cache_dir=cache_dir)
        npc = config.read_member("npc.dat")
        obj = config.read_member("obj.dat")
        print(f"Config: OK from {config.source}")
        print(f"  npc.dat: {len(npc) if npc else 0:,} bytes")
        print(f"  obj.dat: {len(obj) if obj else 0:,} bytes")
        print("  dump_npc / dump_item: OK")
    except Exception as exc:
        print(f"Config: MISSING — dump_npc / dump_item will fail")
        print(f"  Reason: {exc}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
