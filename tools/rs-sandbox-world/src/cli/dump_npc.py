"""Dump or search NPC definitions from config archive."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from src.cache.config_locator import ConfigNotFoundError
from src.cache.npc_index import NPCIndex
from src.config import DEFAULT_CACHE_DIR, resolve_cache_dir


def _format_npc(npc) -> str:
    recolors = ""
    if npc.color_src and npc.color_dst:
        pairs = ", ".join(f"{s}->{d}" for s, d in zip(npc.color_src, npc.color_dst))
        recolors = f"\n  recolors: {pairs}"
    models = npc.model_ids or []
    return (
        f"NPC ID: {npc.id}\n"
        f"  name: {npc.name}\n"
        f"  model IDs: {models}\n"
        f"  stand animation: {npc.seq_stand_id}\n"
        f"  walk animation: {npc.seq_walk_id}\n"
        f"  combat level: {npc.level}\n"
        f"  scale values: xy={npc.scale_xy}, z={npc.scale_z}"
        f"{recolors}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dump or search NPC definitions.")
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE_DIR, help="Path to cache directory")
    parser.add_argument("--config-archive", type=Path, help="Standalone config archive blob (idx0 file 2)")
    parser.add_argument("--npc-dat", type=Path, help="Loose npc.dat path")
    parser.add_argument("--npc-idx", type=Path, help="Loose npc.idx path")
    parser.add_argument("--npc-id", type=int, help="Dump a single NPC id")
    parser.add_argument("--search", type=str, help="Case-insensitive name search")
    parser.add_argument("--out", type=Path, help="Optional JSON output path")
    args = parser.parse_args(argv)

    if not args.npc_id and not args.search:
        parser.error("Provide --npc-id or --search")

    try:
        index = NPCIndex.from_cache(
            cache_dir=resolve_cache_dir(args.cache) if args.cache else None,
            config_archive_path=args.config_archive,
            npc_dat=args.npc_dat,
            npc_idx=args.npc_idx,
        )
    except ConfigNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(f"Loaded {index.count} NPC definitions from {index.source}")

    if args.npc_id is not None:
        npc = index.get(args.npc_id)
        if npc is None:
            print(f"NPC {args.npc_id} not found.", file=sys.stderr)
            return 1
        results = [npc]
    else:
        results = index.search(args.search or "")
        if not results:
            print(f"No NPCs matching {args.search!r}.")
            return 0

    for npc in results:
        print(_format_npc(npc))
        print()

    if args.out:
        payload = [npc.to_dict() for npc in results]
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(payload if len(payload) > 1 else payload[0], indent=2), encoding="utf-8")
        print(f"Wrote {args.out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
