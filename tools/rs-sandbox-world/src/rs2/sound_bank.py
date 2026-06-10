"""Load RS sound bank from config archive 8 (sounds.dat)."""

from __future__ import annotations

from pathlib import Path

from src.cache.cache_locator import CacheReader
from src.cache.file_archive import FileArchive
from src.rs2.sound_track import SoundTrack

_SOUNDS_ARCHIVE_ID = 8
_loaded = False
_max_id = 0


def load_sounds(cache: CacheReader | None = None, *, cache_dir: Path | None = None) -> None:
    """Unpack sounds.dat once into :class:`SoundTrack`."""
    global _loaded, _max_id
    if _loaded:
        return
    if cache is None:
        from src.config import DEFAULT_CACHE_DIR, resolve_cache_dir

        cache = CacheReader(resolve_cache_dir(cache_dir or DEFAULT_CACHE_DIR))
    raw = cache.read_archive(_SOUNDS_ARCHIVE_ID)
    if raw is None:
        raise FileNotFoundError("Sound archive (idx0 file 8) missing from cache")
    arch = FileArchive.load(raw)
    sounds_dat = arch.read("sounds.dat")
    if not sounds_dat:
        raise FileNotFoundError("sounds.dat missing from sound archive")
    SoundTrack.unpack(sounds_dat)
    _loaded = True
    _max_id = max(SoundTrack.tracks.keys()) if SoundTrack.tracks else 0


def sound_count() -> int:
    return len(SoundTrack.tracks)


def max_sound_id() -> int:
    return _max_id


def has_sound(sound_id: int) -> bool:
    return sound_id in SoundTrack.tracks


def render_wav(sound_id: int, loop_count: int = 1) -> bytes | None:
    if not _loaded:
        raise RuntimeError("call load_sounds() first")
    return SoundTrack.generate_wav(sound_id, loop_count)
