"""Locate the config FileArchive (npc.dat, obj.dat, seq.dat, ...)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.cache import java_bridge
from src.cache.cache_locator import CacheReader
from src.cache.file_archive import FileArchive

# Game.loadArchive(2, "config", ...) in Game.java
DEFAULT_CONFIG_ARCHIVE_ID = 2


@dataclass
class ConfigBundle:
    archive: FileArchive | None
    source: str
    cache_dir: Path | None = None

    def read_member(self, name: str) -> bytes | None:
        if self.cache_dir is not None and java_bridge.is_available():
            return java_bridge.read_archive_member(self.cache_dir, DEFAULT_CONFIG_ARCHIVE_ID, name)
        if self.archive is not None:
            return self.archive.read(name)
        return None


class ConfigNotFoundError(FileNotFoundError):
    pass


def load_config_archive(
    cache_dir: Path | None = None,
    config_archive_path: Path | None = None,
    npc_dat: Path | None = None,
    npc_idx: Path | None = None,
    *,
    prefer_java: bool = True,
) -> ConfigBundle:
    """Load config from cache idx0 slot 2 or a raw archive blob."""
    if config_archive_path is not None:
        raw = config_archive_path.read_bytes()
        return ConfigBundle(archive=FileArchive.load(raw), source=str(config_archive_path))

    if npc_dat is not None and npc_idx is not None:
        raise ConfigNotFoundError(
            "Loose npc.dat/npc.idx should be passed directly to NPCIndex.from_cache, not load_config_archive."
        )

    if cache_dir is None:
        raise ConfigNotFoundError("No cache directory or config path provided.")

    cache = CacheReader(cache_dir, prefer_java=prefer_java)
    resolved = cache.cache_dir

    if prefer_java and java_bridge.is_available():
        npc = java_bridge.read_archive_member(resolved, DEFAULT_CONFIG_ARCHIVE_ID, "npc.dat")
        obj = java_bridge.read_archive_member(resolved, DEFAULT_CONFIG_ARCHIVE_ID, "obj.dat")
        if npc and obj:
            return ConfigBundle(
                archive=None,
                source=f"{resolved} idx0 file {DEFAULT_CONFIG_ARCHIVE_ID} (java)",
                cache_dir=resolved,
            )

    raw = cache.read_archive(DEFAULT_CONFIG_ARCHIVE_ID)
    if raw is not None:
        try:
            arch = FileArchive.load(raw)
            if arch.read("npc.dat") and arch.read("npc.idx"):
                return ConfigBundle(
                    archive=arch,
                    source=f"{cache.paths.root} idx0 file {DEFAULT_CONFIG_ARCHIVE_ID}",
                )
        except Exception:
            pass

    raise ConfigNotFoundError(
        f"Config archive missing from {cache.paths.root}. "
        f"idx0 file {DEFAULT_CONFIG_ARCHIVE_ID} is empty or unreadable."
    )
