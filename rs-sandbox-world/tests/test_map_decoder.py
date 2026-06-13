"""Unit tests for map decode helpers (no cache required)."""

from __future__ import annotations

import struct

from src.rs2.map_decoder import REGION_SIZE, calculate_vertex_height, decode_terrain_map
from src.rs2.xtea import decrypt, decrypt_block


def test_xtea_block_size():
    key = [0x10203040, 0x50607080, 0x90A0B0C0, 0xD0E0F0A1]
    out = decrypt(bytes(8), key)
    assert len(out) == 8


def test_decode_explicit_height_tile():
    # plane 0, tile (0,0): opcode 1, height byte 5 -> vertex height -40
    data = bytes([1, 5])
    # fill rest of region with opcode 0 defaults
    for _ in range(REGION_SIZE * REGION_SIZE - 1):
        data += b"\x00"
    for plane in range(1, 4):
        data += b"\x00" * (REGION_SIZE * REGION_SIZE)
    region = decode_terrain_map(data, 10, 20)
    assert region.height_at(0, 0) == -40
    assert not region.blocked_at(0, 0)


def test_decode_blocked_settings():
    data = bytearray()
    for _ in range(REGION_SIZE * REGION_SIZE):
        data.extend([50, 0])  # settings opcode 50 -> settings=1 (blocked)
    for plane in range(1, 4):
        data.extend(b"\x00" * (REGION_SIZE * REGION_SIZE))
    region = decode_terrain_map(bytes(data), 0, 0)
    assert region.blocked_at(0, 0)
    assert region.blocked_at(10, 10)


def test_vertex_height_deterministic():
    a = calculate_vertex_height(1000, 2000)
    b = calculate_vertex_height(1000, 2000)
    assert a == b
    assert 0 <= a <= 255
