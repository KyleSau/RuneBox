"""Load + cache RS animation data (sequences and frame transforms).

Unpacking every frame file is slow (~90s), so the decoded transform map is
pickled to ``outputs/intermediate`` and reused on subsequent runs.
"""

from __future__ import annotations

import pickle
from dataclasses import dataclass
from pathlib import Path

from src.cache.config_locator import DEFAULT_CONFIG_ARCHIVE_ID
from src.cache.file_archive import FileArchive
from src.rs2.seq_decoder import (
    SeqTransform,
    SeqType,
    decode_seq_types,
    load_all_transforms,
)

_CACHE_VERSION = 1
_CACHE_PATH = Path("outputs/intermediate/anim_transforms.pkl")


@dataclass
class AnimationData:
    seqs: dict[int, SeqType]
    transforms: dict[int, SeqTransform]

    def stand_seq(self, npc) -> SeqType | None:
        sid = getattr(npc, "seq_stand_id", None)
        if sid is None or sid < 0:
            return None
        return self.seqs.get(sid)


def load_animation_data(cache, *, use_cache: bool = True) -> AnimationData | None:
    raw_seq = None
    archive_bytes = cache.read_archive(DEFAULT_CONFIG_ARCHIVE_ID)
    if archive_bytes is not None:
        raw_seq = FileArchive.load(archive_bytes).read("seq.dat")
    if not raw_seq:
        return None
    seqs = decode_seq_types(raw_seq)

    transforms: dict[int, SeqTransform] | None = None
    if use_cache and _CACHE_PATH.exists():
        try:
            with _CACHE_PATH.open("rb") as fh:
                blob = pickle.load(fh)
            if blob.get("version") == _CACHE_VERSION:
                transforms = blob["transforms"]
        except Exception:
            transforms = None

    if transforms is None:
        transforms = load_all_transforms(cache.read_animation)
        if use_cache and transforms:
            try:
                _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
                with _CACHE_PATH.open("wb") as fh:
                    pickle.dump({"version": _CACHE_VERSION, "transforms": transforms}, fh)
            except Exception:
                pass

    return AnimationData(seqs=seqs, transforms=transforms)
