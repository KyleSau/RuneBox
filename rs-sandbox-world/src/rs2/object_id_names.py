"""Supplemental object display names from RuneLite ObjectID.java (377/OSRS overlap)."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

_CONST_RE = re.compile(
    r"public\s+static\s+final\s+int\s+([A-Z0-9_]+)\s*=\s*(\d+)\s*;",
)


def _const_to_label(name: str) -> str:
    parts = name.split("_")
    while parts and parts[-1].isdigit():
        parts.pop()
    if not parts:
        return name.replace("_", " ").title()
    return " ".join(p.lower() for p in parts).title()


def _find_object_id_java() -> Path | None:
    root = Path(__file__).resolve().parents[2]
    candidates = [
        root.parent / "runelite-master" / "runelite-master" / "runelite-api" / "src" / "main" / "java" / "net" / "runelite" / "api" / "ObjectID.java",
        root / "runelite-master" / "runelite-master" / "runelite-api" / "src" / "main" / "java" / "net" / "runelite" / "api" / "ObjectID.java",
    ]
    for path in candidates:
        if path.is_file():
            return path
    return None


@lru_cache(maxsize=1)
def load_object_id_names() -> dict[int, str]:
    path = _find_object_id_java()
    if path is None:
        return {}
    out: dict[int, str] = {}
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        m = _CONST_RE.search(line)
        if not m:
            continue
        label = _const_to_label(m.group(1))
        if not label:
            continue
        out[int(m.group(2))] = label
    return out


def lookup_object_id_name(loc_id: int) -> str | None:
    return load_object_id_names().get(loc_id)
