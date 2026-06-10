"""Search item definitions for weapon/armor model IDs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from src.cache.config_locator import ConfigNotFoundError
from src.cache.item_index import ItemIndex
from src.config import DEFAULT_CACHE_DIR, resolve_cache_dir


def _format_item(item) -> str:
    recolors = ""
    if item.src_color and item.dst_color:
        pairs = ", ".join(f"{s}->{d}" for s, d in zip(item.src_color, item.dst_color))
        recolors = f"\n  recolors: {pairs}"
    return (
        f"Item ID: {item.id}\n"
        f"  name: {item.name}\n"
        f"  ground model: {item.model_id}\n"
        f"  worn models: {item.worn_model_ids()}"
        f"{recolors}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dump or search item definitions.")
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--config-archive", type=Path)
    parser.add_argument("--item-id", type=int)
    parser.add_argument("--search", type=str)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)

    if not args.item_id and not args.search:
        parser.error("Provide --item-id or --search")

    try:
        index = ItemIndex.from_cache(cache_dir=resolve_cache_dir(args.cache), config_archive_path=args.config_archive)
    except ConfigNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(f"Loaded {index.count} item definitions from {index.source}")

    if args.item_id is not None:
        item = index.get(args.item_id)
        if item is None:
            print(f"Item {args.item_id} not found.", file=sys.stderr)
            return 1
        results = [item]
    else:
        results = index.search(args.search or "")
        if not results:
            print(f"No items matching {args.search!r}.")
            return 0

    for item in results:
        print(_format_item(item))
        print()

    if args.out:
        payload = [item.to_dict() for item in results]
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(payload if len(payload) > 1 else payload[0], indent=2), encoding="utf-8")
        print(f"Wrote {args.out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
