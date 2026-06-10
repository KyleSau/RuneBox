"""Locate and open the classic RS main_file_cache layout."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.cache import java_bridge
from src.cache.file_store import FileStore


@dataclass
class CachePaths:
    root: Path
    dat: Path
    idx: list[Path]

    @classmethod
    def from_directory(cls, cache_dir: Path) -> "CachePaths":
        from src.config import resolve_cache_dir

        root = resolve_cache_dir(cache_dir)
        if not (root / "main_file_cache.dat").exists():
            raise FileNotFoundError(
                f"No main_file_cache.dat found under {cache_dir}. "
                "Expected OpenRS2 layout: .../cache/main_file_cache.dat"
            )

        idx = [root / f"main_file_cache.idx{i}" for i in range(5)]
        missing = [p for p in idx if not p.exists()]
        if missing:
            raise FileNotFoundError(f"Missing index files: {', '.join(str(p) for p in missing)}")

        return cls(root=root, dat=root / "main_file_cache.dat", idx=idx)


class CacheReader:
    """Read-only view of the 317/377 cache.

    Cache I/O and decompression prefer the Java client (FileStore, FileArchive, gzip).
    Python FileStore is kept as a fallback when the client is unavailable.
    """

    def __init__(self, cache_dir: Path, *, prefer_java: bool = True):
        paths = CachePaths.from_directory(cache_dir)
        self.paths = paths
        self.cache_dir = paths.root
        self.use_java = prefer_java and java_bridge.is_available()
        # filestores[i] uses idx[i] with store id i+1 (see FileStore.java).
        self.filestores = [
            FileStore(paths.dat, paths.idx[i], store_id=i + 1) for i in range(5)
        ]

    def read_file(self, store_idx: int, file_id: int) -> bytes | None:
        if self.use_java:
            data = java_bridge.read_cache_file(self.cache_dir, store_idx, file_id)
            if data is not None:
                return data
        return self.filestores[store_idx].read(file_id)

    def read_archive(self, file_id: int) -> bytes | None:
        """Read a packed archive from idx0 (title, config, versionlist, ...)."""
        return self.read_file(0, file_id)

    def read_model(self, model_id: int) -> bytes | None:
        """Decompressed model bytes (idx1 + OnDemand gzip)."""
        if self.use_java:
            data = java_bridge.read_model_bytes(self.cache_dir, model_id)
            if data is not None:
                return data
        raw = self.filestores[1].read(model_id)
        if raw is None:
            return None
        from src.rs2.model_decoder import prepare_model_bytes

        return prepare_model_bytes(raw)

    def read_animation(self, anim_id: int) -> bytes | None:
        return self.read_file(2, anim_id)
