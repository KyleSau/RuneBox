"""OSRS wiki sound ID names (informational; 377 cache has fewer sounds)."""

from __future__ import annotations

import json
import re
from pathlib import Path

_ROW_RE = re.compile(r"^\|\s*(\d+)\s*\|\s*([^|]+?)\s*\|")

_DEFAULT_WIKI = Path(__file__).resolve().parents[2] / "data" / "sound_names_wiki.json"


def _clean_wiki_name(raw: str) -> str:
    name = raw.strip().replace(r"\_", "_").replace("\\", "")
    return name


def parse_wiki_markdown(text: str) -> dict[int, str]:
    """Parse | ID | name | rows from the OSRS wiki markdown export."""
    names: dict[int, str] = {}
    for line in text.splitlines():
        match = _ROW_RE.match(line.strip())
        if not match:
            continue
        name = _clean_wiki_name(match.group(2))
        if name and name != "Sound" and not name.startswith("-"):
            names[int(match.group(1))] = name
    return names


def load_wiki_names(path: Path | None = None) -> dict[int, str]:
    path = path or _DEFAULT_WIKI
    if path.suffix == ".json" and path.is_file():
        raw = json.loads(path.read_text(encoding="utf-8"))
        return {int(k): v for k, v in raw.items()}
    if path.is_file():
        return parse_wiki_markdown(path.read_text(encoding="utf-8"))
    return {}


def build_sound_index(
    wiki_names: dict[int, str],
    *,
    cache_max_id: int,
    cache_ids: set[int],
) -> list[dict]:
    """Build viewer index: every cached sound + wiki label when known."""
    entries = []
    for sound_id in sorted(cache_ids):
        wiki = wiki_names.get(sound_id)
        entries.append(
            {
                "id": sound_id,
                "name": wiki or f"sound_{sound_id}",
                "inCache": True,
            }
        )
    return entries


def save_sound_index(entries: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "revision": "377",
                "audioSource": "cache-synth",
                "note": (
                    "Playback is synthesized from sounds.dat (377 cache) only — never wiki MP3s. "
                    "Wiki/OSRS names here are labels for search; newer OSRS IDs may not exist in this cache."
                ),
                "maxCacheId": max((e["id"] for e in entries), default=0),
                "count": len(entries),
                "sounds": entries,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
