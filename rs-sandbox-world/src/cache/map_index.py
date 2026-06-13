"""Read 317/377 map archives from cache idx4."""

from __future__ import annotations

import gzip
import json
import os
import struct
import zlib
from pathlib import Path
from typing import TYPE_CHECKING

from src.config import PIPELINE_ROOT

if TYPE_CHECKING:
    from src.cache.cache_locator import CacheReader

MAP_STORE_IDX = 4
LANDSCAPE_FILE_OFFSET = 0x8000  # classic: l{rx}_{ry} at m id + 0x8000
LANDSCAPE_FILE_OFFSET_OPENRS2 = 1  # OpenRS2 377 extracts: landscape at terrain id + 1


def region_id(region_x: int, region_y: int) -> int:
    return ((region_x & 0xFF) << 8) | (region_y & 0xFF)


def terrain_file_id(region_x: int, region_y: int) -> int:
    """Terrain tile map (``m{rx}_{ry}``) - gzip, not XTEA encrypted."""
    return region_id(region_x, region_y)


def landscape_file_id(region_x: int, region_y: int) -> int:
    """Object landscape (``l{rx}_{ry}``) - gzip + XTEA."""
    return region_id(region_x, region_y) + LANDSCAPE_FILE_OFFSET


def jagex_name_hash(name: str) -> int:
    """Signed 32-bit string hash used by Jagex cache naming."""
    h = 0
    for ch in name:
        h = (h * 31 + ord(ch)) & 0xFFFFFFFF
    if h >= 0x80000000:
        h -= 0x100000000
    return h


def prepare_map_bytes(data: bytes) -> bytes:
    """Decompress gzip map payloads (same header check as models)."""
    if len(data) >= 2 and data[0] == 0x1F and data[1] == 0x8B:
        try:
            return gzip.decompress(data)
        except OSError:
            return zlib.decompress(data, zlib.MAX_WBITS | 32)
    return data


def default_xtea_keys_path() -> Path:
    env = os.environ.get("XTEA_KEYS_PATH")
    if env:
        return Path(env)
    return PIPELINE_ROOT / "data" / "xtea_keys.json"


def load_xtea_keys(path: Path | None = None) -> dict[int, list[int]]:
    """Load region-id -> [k0,k1,k2,k3] from JSON.

    Keys may be region ids (``12850``) or ``"50,50"`` coordinate strings.
    """
    path = path or default_xtea_keys_path()
    if not path.is_file():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    out: dict[int, list[int]] = {}
    for key, value in raw.items():
        if key.startswith("_"):
            continue
        if not isinstance(value, list) or len(value) != 4:
            continue
        ints = [int(x) & 0xFFFFFFFF for x in value]
        if "," in str(key):
            rx_s, ry_s = str(key).split(",", 1)
            rid = region_id(int(rx_s), int(ry_s))
        else:
            rid = int(key) & 0xFFFF
        out[rid] = ints
    return out


def parse_map_index_pairs(data: bytes, *, max_file_id: int = 65535) -> dict[int, int]:
    """Parse ``map_index`` versionlist member: u16 (regionId, idx4FileId) pairs."""
    if len(data) < 4:
        return {}
    vals = struct.unpack(">" + "H" * (len(data) // 2), data)
    out: dict[int, int] = {}
    for i in range(0, len(vals) - 1, 2):
        region = int(vals[i]) & 0xFFFF
        file_id = int(vals[i + 1])
        if file_id < 0 or file_id > max_file_id:
            continue
        out[region] = file_id
    return out


def load_map_file_index(cache: "CacheReader", *, max_file_id: int | None = None) -> dict[int, int]:
    """Build regionId -> idx4 file id table from versionlist ``map_index``."""
    raw = cache.read_archive(5)
    if raw is None:
        return {}
    from src.cache.file_archive import FileArchive

    arch = FileArchive.load(raw)
    data = arch.read("map_index")
    if data is None:
        return {}
    if max_file_id is None:
        max_file_id = cache.filestores[MAP_STORE_IDX].file_count() - 1
    return parse_map_index_pairs(data, max_file_id=max_file_id)


def resolve_terrain_file_id(
    cache: "CacheReader",
    region_x: int,
    region_y: int,
    *,
    index: dict[int, int] | None = None,
) -> int | None:
    rid = region_id(region_x, region_y)
    if index is None:
        index = load_map_file_index(cache)
    if rid in index:
        return index[rid]
    classic = terrain_file_id(region_x, region_y)
    if cache.read_file(MAP_STORE_IDX, classic):
        return classic
    return None


def read_map_file(
    cache: "CacheReader",
    file_id: int,
    *,
    xtea_key: list[int] | None = None,
) -> bytes | None:
    raw = cache.read_file(MAP_STORE_IDX, file_id)
    if not raw:
        return None
    data = prepare_map_bytes(raw)
    if xtea_key:
        from src.rs2.xtea import decrypt

        if len(data) % 8:
            return None
        data = decrypt(data, xtea_key)
    return data


def read_terrain_bytes(
    cache: "CacheReader",
    region_x: int,
    region_y: int,
    *,
    index: dict[int, int] | None = None,
) -> bytes | None:
    file_id = resolve_terrain_file_id(cache, region_x, region_y, index=index)
    if file_id is None:
        return None
    return read_map_file(cache, file_id)


def resolve_landscape_file_id(
    cache: "CacheReader",
    region_x: int,
    region_y: int,
    *,
    index: dict[int, int] | None = None,
) -> int | None:
    """Locate idx4 landscape file for a region (format varies by cache extract)."""
    rid = region_id(region_x, region_y)
    if index is None:
        index = load_map_file_index(cache)
    candidates: list[int] = []
    if rid in index:
        base = index[rid]
        candidates.append(base + LANDSCAPE_FILE_OFFSET_OPENRS2)
        candidates.append(base + LANDSCAPE_FILE_OFFSET)
    candidates.append(landscape_file_id(region_x, region_y))
    seen: set[int] = set()
    for file_id in candidates:
        if file_id in seen:
            continue
        seen.add(file_id)
        if cache.read_file(MAP_STORE_IDX, file_id):
            return file_id
    return None


def _landscape_payload_valid(data: bytes, region_x: int, region_y: int) -> bool:
    from src.rs2.landscape_decoder import decode_landscape

    return decode_landscape(data, region_x, region_y) is not None


def read_landscape_bytes(
    cache: "CacheReader",
    region_x: int,
    region_y: int,
    *,
    xtea_keys: dict[int, list[int]] | None = None,
    index: dict[int, int] | None = None,
) -> bytes | None:
    file_id = resolve_landscape_file_id(cache, region_x, region_y, index=index)
    if file_id is None:
        return None
    raw = cache.read_file(MAP_STORE_IDX, file_id)
    if not raw:
        return None
    prep = prepare_map_bytes(raw)
    if _landscape_payload_valid(prep, region_x, region_y):
        return prep

    rid = region_id(region_x, region_y)
    key = (xtea_keys or {}).get(rid)
    if key and len(prep) % 8 == 0:
        from src.rs2.xtea import decrypt

        try:
            dec = decrypt(prep, key)
        except ValueError:
            dec = None
        if dec and _landscape_payload_valid(dec, region_x, region_y):
            return dec
    return None
