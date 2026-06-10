"""Decode spotanim.dat (GFX / spot animations) from the config archive."""

from __future__ import annotations

from dataclasses import dataclass, field

from src.rs2.buffer import Buffer


@dataclass
class SpotAnimType:
    id: int
    model_id: int = 0
    seq_id: int = -1
    scale_xy: int = 128
    scale_z: int = 128
    rotation: int = 0
    light_ambient: int = 0
    light_attenuation: int = 0
    color_src: list[int] = field(default_factory=lambda: [0] * 6)
    color_dst: list[int] = field(default_factory=lambda: [0] * 6)


def decode_spotanim_types(spotanim_dat: bytes) -> dict[int, SpotAnimType]:
    """Ports SpotAnimType.unpack."""
    buf = Buffer(spotanim_dat)
    count = buf.read_u16()
    out: dict[int, SpotAnimType] = {}
    for i in range(count):
        entry = SpotAnimType(id=i)
        while True:
            code = buf.read_u8()
            if code == 0:
                break
            if code == 1:
                entry.model_id = buf.read_u16()
            elif code == 2:
                entry.seq_id = buf.read_u16()
            elif code == 4:
                entry.scale_xy = buf.read_u16()
            elif code == 5:
                entry.scale_z = buf.read_u16()
            elif code == 6:
                entry.rotation = buf.read_u16()
            elif code == 7:
                entry.light_ambient = buf.read_u8()
            elif code == 8:
                entry.light_attenuation = buf.read_u8()
            elif 40 <= code < 50:
                entry.color_src[code - 40] = buf.read_u16()
            elif 50 <= code < 60:
                entry.color_dst[code - 50] = buf.read_u16()
        out[i] = entry
    return out


def spotanim_recolor_map(entry: SpotAnimType) -> dict[int, int]:
    """HSL recolour pairs (spotanim stores src/dst in parallel arrays)."""
    recolor: dict[int, int] = {}
    for src, dst in zip(entry.color_src, entry.color_dst):
        if src != 0:
            recolor[src] = dst
    return recolor
