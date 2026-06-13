"""LocType decoder tests."""

from __future__ import annotations

from src.rs2.buffer import Buffer
from src.rs2.loc_decoder import _read_loc, loc_display_name, loc_is_interactable


def _pack_loc(*chunks: bytes) -> bytes:
    return b"".join(chunks) + b"\x00"


def test_read_loc_name_after_category_opcode():
    body = _pack_loc(
        b"\x01\x01\x00\x2a\x0a",  # one model, id 42, kind 10
        b"\x3d\xe9\x03",  # opcode 61 category -> u16 1001
        b"\x02Door\n",  # name
        b"\x03It's a sturdy wooden door.\n",  # examine
        b"\x1eOpen\n",  # opcode 30 -> Open
    )
    loc = _read_loc(2579, Buffer(body))
    assert loc.name == "Door"
    assert loc.examine == "It's a sturdy wooden door."
    assert loc.actions[0] == "Open"
    assert loc_display_name(loc) == "Door"


def test_read_loc_debug_name_fallback():
    body = _pack_loc(
        b"\x01\x01\x00\x2a\x0a",
        b"\xfaOak tree\n",  # opcode 250 debug name
    )
    loc = _read_loc(100, Buffer(body))
    assert loc.debug_name == "Oak tree"
    assert loc_display_name(loc) == "Oak tree"


def test_loc_1510_runelite_alias():
    from pathlib import Path

    from src.cache.config_locator import load_config_archive
    from src.config import resolve_cache_dir
    from src.rs2.loc_decoder import decode_loc_types, loc_display_name

    cache_dir = resolve_cache_dir(Path(r"..\cache-runescape-live-en-b377-2006-05-02-00-00-00-openrs2#657\cache"))
    bundle = load_config_archive(cache_dir=cache_dir)
    locs = decode_loc_types(bundle.read_member("loc.dat"), bundle.read_member("loc.idx"))
    assert loc_display_name(locs[1510], kind=0) == "Door"
    assert loc_display_name(locs[1515], kind=0) == "Large door"


def test_read_loc_examine_derived_name():
    body = _pack_loc(
        b"\x01\x01\x00\x2a\x0a",
        b"\x03It's a pile of logs.\n",
    )
    loc = _read_loc(500, Buffer(body))
    assert loc_display_name(loc) == "a pile of logs"


def test_loc_interactable_defaults():
    body = _pack_loc(
        b"\x01\x01\x00\x2a\x0a",  # kind 10 centrepiece
    )
    loc = _read_loc(1, Buffer(body))
    assert loc_is_interactable(loc) is True

    wall = _pack_loc(
        b"\x01\x01\x00\x2a\x00",  # kind 0 wall
    )
    loc_wall = _read_loc(2, Buffer(wall))
    assert loc_is_interactable(loc_wall) is False

    with_open = _pack_loc(
        b"\x01\x01\x00\x2a\x00",
        b"\x1eOpen\n",
    )
    loc_door = _read_loc(3, Buffer(with_open))
    assert loc_is_interactable(loc_door) is True


def test_loc_display_name_never_uses_kind_label():
    body = _pack_loc(
        b"\x01\x01\x00\x2a\x16",  # kind 22 ground decor
    )
    loc = _read_loc(99999, Buffer(body))
    assert loc_display_name(loc, kind=22) == "Object (99999)"
    assert "Ground decoration" not in loc_display_name(loc, kind=22)
    assert "Wall" not in loc_display_name(loc, kind=22)
