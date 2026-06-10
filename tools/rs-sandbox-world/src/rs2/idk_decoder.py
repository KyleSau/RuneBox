"""Decode idk.dat (identity kit / character design body parts).

Ports IdkType.java (377 client). Identity kits are the static body-part models a
Player is assembled from (head, jaw, torso, arms, hands, legs, feet) plus their
recolour pairs. Unlike NPCs the kit models never carry equipment.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.rs2.buffer import Buffer


@dataclass
class IdkType:
    id: int
    type: int = -1
    model_ids: list[int] | None = None
    head_model_ids: list[int] = field(default_factory=lambda: [-1, -1, -1, -1, -1])
    color_src: list[int] = field(default_factory=lambda: [0] * 6)
    color_dst: list[int] = field(default_factory=lambda: [0] * 6)
    selectable: bool = False


def decode_idk_types(idk_dat: bytes) -> list[IdkType]:
    """Ports IdkType.unpack / IdkType.read."""
    buf = Buffer(idk_dat)
    count = buf.read_u16()
    out: list[IdkType] = []
    for i in range(count):
        entry = IdkType(id=i)
        while True:
            code = buf.read_u8()
            if code == 0:
                break
            if code == 1:
                entry.type = buf.read_u8()
            elif code == 2:
                n = buf.read_u8()
                entry.model_ids = [buf.read_u16() for _ in range(n)]
            elif code == 3:
                entry.selectable = True
            elif 40 <= code < 50:
                entry.color_src[code - 40] = buf.read_u16()
            elif 50 <= code < 60:
                entry.color_dst[code - 50] = buf.read_u16()
            elif 60 <= code < 70:
                entry.head_model_ids[code - 60] = buf.read_u16()
            else:
                # Unknown code: bail to avoid desyncing the shared buffer.
                break
        out.append(entry)
    return out


def idk_recolor_map(entry: IdkType) -> dict[int, int]:
    """HSL recolour pairs stored on the kit itself (colorSrc -> colorDst)."""
    recolor: dict[int, int] = {}
    for src, dst in zip(entry.color_src, entry.color_dst):
        if src != 0:
            recolor[src] = dst
    return recolor
