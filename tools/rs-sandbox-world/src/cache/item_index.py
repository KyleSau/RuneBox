"""Item definition index from config archive."""

from __future__ import annotations

from pathlib import Path

from src.cache.config_locator import ConfigBundle, load_config_archive
from src.rs2.buffer import Buffer
from src.rs2.item_decoder import ItemDefinition, decode_item


class ItemIndex:
    def __init__(self, config: ConfigBundle):
        obj_dat = config.read_member("obj.dat")
        obj_idx = config.read_member("obj.idx")
        if obj_dat is None or obj_idx is None:
            raise FileNotFoundError("obj.dat or obj.idx missing from config archive")

        idx = Buffer(obj_idx)
        self.count = idx.read_u16()
        self.offsets: list[int] = []
        offset = 2
        for _ in range(self.count):
            self.offsets.append(offset)
            offset += idx.read_u16()

        self.dat = obj_dat
        self.source = config.source

    @classmethod
    def from_cache(
        cls,
        cache_dir: Path | None = None,
        config_archive_path: Path | None = None,
    ) -> "ItemIndex":
        config = load_config_archive(cache_dir, config_archive_path)
        return cls(config)

    def get(self, item_id: int) -> ItemDefinition | None:
        if item_id < 0 or item_id >= self.count:
            return None
        buf = Buffer(self.dat)
        buf.position = self.offsets[item_id]
        item = decode_item(buf)
        item.id = item_id
        return item

    def search(self, query: str) -> list[ItemDefinition]:
        q = query.lower()
        results: list[ItemDefinition] = []
        for item_id in range(self.count):
            item = self.get(item_id)
            if item is None or not item.name:
                continue
            if q in item.name.lower():
                results.append(item)
        return results
