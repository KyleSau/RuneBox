"""Scan all cache indices for config/npc.dat signatures."""

from __future__ import annotations

import bz2
import gzip
import struct
import sys
import zlib
import zlib as _zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.cache.cache_locator import CacheReader
from src.cache.file_archive import FileArchive, _decompress_bzip2


def hash_name(name: str) -> int:
    value = 0
    for ch in name.upper():
        value = (value * 61 + ord(ch) - 32) & 0xFFFFFFFF
        if value >= 0x80000000:
            value -= 0x100000000
    return value


def looks_like_npc_idx(data: bytes) -> bool:
    if len(data) < 4:
        return False
    count = struct.unpack(">H", data[:2])[0]
    if count < 100 or count > 30000:
        return False
    pos = 2
    total = 2
    for _ in range(count):
        if pos + 2 > len(data):
            return False
        sz = struct.unpack(">H", data[pos : pos + 2])[0]
        if sz == 0 or sz > 5000:
            return False
        pos += 2
        total += sz
    return abs(total - len(data)) <= 4


def try_decompress(raw: bytes) -> list[tuple[str, bytes]]:
    out: list[tuple[str, bytes]] = [("raw", raw)]
    if raw[:2] == b"\x1f\x8b":
        try:
            out.append(("gzip", gzip.decompress(raw)))
        except OSError:
            try:
                out.append(("zlib-gzip", zlib.decompress(raw, zlib.MAX_WBITS | 32)))
            except Exception:
                pass
    if len(raw) > 6:
        try:
            out.append(("bzip-container", _decompress_bzip2(raw, 6, struct.unpack(">I", b"\x00" + raw[3:6])[0] if False else int.from_bytes(raw[3:6], "big"))))
        except Exception:
            pass
        try:
            packed = int.from_bytes(raw[3:6], "big")
            if packed > 0 and packed < len(raw):
                out.append(("bzip6", _decompress_bzip2(raw, 6, packed)))
        except Exception:
            pass
    try:
        out.append(("bzip0", bz2.decompress(b"BZh1" + raw)))
    except Exception:
        pass
    return out


def scan_member(data: bytes, label: str) -> None:
    if looks_like_npc_idx(data):
        count = struct.unpack(">H", data[:2])[0]
        print(f"  NPC_IDX candidate: {label} count={count} size={len(data)}")
    if b"Unicorn\n" in data or b"unicorn\n" in data:
        print(f"  UNICORN string: {label} size={len(data)}")
    for name in ("npc.dat", "npc.idx", "obj.dat", "obj.idx"):
        if hash_name(name) == struct.unpack(">i", data[:4])[0] if len(data) >= 4 else False:
            pass
    try:
        arch = FileArchive.load(data)
        hits = [n for n in ("npc.dat", "npc.idx", "obj.dat", "seq.dat") if arch.read(n)]
        if hits:
            print(f"  FileArchive with {hits}: {label}")
    except Exception:
        pass


def main() -> None:
    from src.config import discover_cache_dir; cache_path = discover_cache_dir()
    cache = CacheReader(cache_path)
    target_crc = (-1998798937) & 0xFFFFFFFF
    npc_dat_h = hash_name("npc.dat")
    npc_idx_h = hash_name("npc.idx")

    print("=== idx0 archive CRCs ===")
    for fid in range(int(cache.filestores[0].file_count())):
        raw = cache.read_archive(fid)
        if not raw:
            print(f"file {fid}: MISSING")
            continue
        crc = zlib.crc32(raw) & 0xFFFFFFFF
        signed = crc if crc < 0x80000000 else crc - 0x100000000
        print(f"file {fid}: {len(raw)} bytes crc={signed} config_match={crc == target_crc}")

    print("\n=== Scan all idx files ===")
    for idx in range(5):
        fs = cache.filestores[idx]
        for fid in range(fs.file_count()):
            raw = fs.read(fid)
            if not raw or len(raw) < 10:
                continue
            label = f"idx{idx}:{fid}"
            for mode, data in try_decompress(raw):
                scan_member(data, f"{label}/{mode}")
            try:
                arch = FileArchive.load(raw)
                for fi, h in enumerate(arch.file_hash):
                    if h in (npc_dat_h, npc_idx_h):
                        print(f"  HASH MATCH idx{idx}:{fid} member {fi} hash={h}")
                    try:
                        if arch.unpacked:
                            member = arch.data[arch.file_offset[fi] : arch.file_offset[fi] + arch.file_size_inflated[fi]]
                        else:
                            member = _decompress_bzip2(arch.data, arch.file_offset[fi], arch.file_size_deflated[fi])
                        if looks_like_npc_idx(member):
                            print(f"  npc.idx member idx{idx}:{fid}/arch member {fi} size={len(member)}")
                        if b"Unicorn\n" in member:
                            print(f"  Unicorn in idx{idx}:{fid} member {fi}")
                    except Exception:
                        pass
            except Exception:
                pass

    print("\nDone.")


if __name__ == "__main__":
    main()
