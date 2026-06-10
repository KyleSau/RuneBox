"""NPC definition index from config archive."""

from __future__ import annotations

from pathlib import Path

from src.cache.config_locator import ConfigBundle, load_config_archive
from src.rs2.buffer import Buffer
from src.rs2.npc_decoder import NPCDefinition, decode_npc


class NPCIndex:
    def __init__(self, config: ConfigBundle):
        npc_dat = config.read_member("npc.dat")
        npc_idx = config.read_member("npc.idx")
        if npc_dat is None or npc_idx is None:
            raise FileNotFoundError("npc.dat or npc.idx missing from config archive")

        idx = Buffer(npc_idx)
        self.count = idx.read_u16()
        self.offsets: list[int] = []
        offset = 2  # matches NPCType.unpack / ObjType.unpack
        for _ in range(self.count):
            self.offsets.append(offset)
            offset += idx.read_u16()

        self.dat = npc_dat
        self.source = config.source

    @classmethod
    def from_cache(
        cls,
        cache_dir: Path | None = None,
        config_archive_path: Path | None = None,
        npc_dat: Path | None = None,
        npc_idx: Path | None = None,
    ) -> "NPCIndex":
        if npc_dat is not None and npc_idx is not None:
            return cls._from_loose(npc_dat, npc_idx)
        config = load_config_archive(cache_dir, config_archive_path)
        return cls(config)

    @classmethod
    def _from_loose(cls, npc_dat: Path, npc_idx: Path) -> "NPCIndex":
        idx = Buffer(npc_idx.read_bytes())
        inst = cls.__new__(cls)
        inst.count = idx.read_u16()
        inst.offsets = []
        offset = 2
        for _ in range(inst.count):
            inst.offsets.append(offset)
            offset += idx.read_u16()
        inst.dat = npc_dat.read_bytes()
        inst.source = str(npc_dat.parent)
        return inst

    def get(self, npc_id: int) -> NPCDefinition | None:
        if npc_id < 0 or npc_id >= self.count:
            return None
        buf = Buffer(self.dat)
        buf.position = self.offsets[npc_id]
        npc = decode_npc(buf)
        npc.id = npc_id
        return npc

    def search(self, query: str) -> list[NPCDefinition]:
        q = query.lower()
        results: list[NPCDefinition] = []
        for npc_id in range(self.count):
            npc = self.get(npc_id)
            if npc is None or not npc.name:
                continue
            if q in npc.name.lower():
                results.append(npc)
        return results
