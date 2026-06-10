"""Build sounds.json index (wiki names + 377 cache availability)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from src.cache.cache_locator import CacheReader
from src.config import DEFAULT_CACHE_DIR, resolve_cache_dir
from src.rs2.sound_bank import load_sounds
from src.rs2.sound_names import build_sound_index, parse_wiki_markdown, save_sound_index
from src.rs2.sound_track import SoundTrack


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build sound index for the web viewer.")
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument(
        "--wiki",
        type=Path,
        help="Wiki markdown export (List_of_sound_IDs) or pre-parsed JSON",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("outputs/unreal_exports/sounds.json"),
    )
    args = parser.parse_args(argv)

    cache = CacheReader(resolve_cache_dir(args.cache))
    load_sounds(cache)
    cache_ids = set(SoundTrack.tracks.keys())

    wiki_names: dict[int, str] = {}
    if args.wiki and args.wiki.is_file():
        if args.wiki.suffix.lower() == ".json":
            raw = json.loads(args.wiki.read_text(encoding="utf-8"))
            wiki_names = {int(k): v for k, v in raw.items()}
        else:
            wiki_names = parse_wiki_markdown(args.wiki.read_text(encoding="utf-8"))
        print(f"Loaded {len(wiki_names)} wiki sound names")

    entries = build_sound_index(
        wiki_names,
        cache_max_id=max(cache_ids) if cache_ids else 0,
        cache_ids=cache_ids,
    )
    save_sound_index(entries, args.out)
    print(f"Wrote {len(entries)} playable sounds to {args.out}")
    print(f"  377 cache IDs: 0..{max(cache_ids) if cache_ids else 0} ({len(cache_ids)} defined)")
    over = sum(1 for i in wiki_names if i not in cache_ids)
    if over:
        print(f"  {over} wiki IDs are not in this cache (newer OSRS content)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
