"""Unit tests for landscape object decode."""

from __future__ import annotations

from src.rs2.landscape_decoder import decode_landscape


def _usmart(n: int) -> bytes:
    if n < 128:
        return bytes([n])
    v = n + 32768
    return bytes([(v >> 8) & 0xFF, v & 0xFF])


def test_decode_single_loc():
    # One loc id 10 at tile (0, 0) plane 0, kind 10, rotation 1.
    payload = _usmart(11)  # loc_id -1 + 11 = 10
    payload += _usmart(1)  # first placement at packed loc_data 0
    payload += bytes([((10 << 2) | 1) & 0xFF])  # kind 10, rot 1
    payload += _usmart(0)  # end loc placements for this id
    payload += _usmart(0)  # end stream

    objs = decode_landscape(payload, 0, 0)
    assert objs is not None
    assert len(objs) == 1
    assert objs[0].id == 10
    assert objs[0].x == 0
    assert objs[0].z == 0
    assert objs[0].plane == 0
    assert objs[0].kind == 10
    assert objs[0].rotation == 1


def test_decode_rejects_trailing_garbage():
    payload = _usmart(0) + b"\xff"
    assert decode_landscape(payload, 0, 0) is None
