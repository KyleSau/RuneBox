"""Model index helpers from versionlist archive."""

from __future__ import annotations

from pathlib import Path

from src.cache.cache_locator import CacheReader
from src.cache.file_archive import FileArchive


def load_model_count(cache_dir: Path) -> int:
    cache = CacheReader(cache_dir)
    raw = cache.read_archive(5)
    if raw is None:
        raise FileNotFoundError("versionlist archive (idx0 file 5) not found")
    arch = FileArchive.load(raw)
    data = arch.read("model_version")
    if data is None:
        raise FileNotFoundError("model_version missing from versionlist")
    return len(data) // 2
