"""Decode loc.dat / loc.idx (LocType - in-game scenery objects).

Ports LocType.unpack / LocType.read (377 client). ``loc.idx`` is a u16 count
followed by per-entry u16 record lengths; the running sum gives each entry's
offset into ``loc.dat`` (entry 0 starts at offset 2). Scenery models are keyed
by a "kind" (10 = centrepiece, 0-3 walls, etc.) and carry recolour, scale,
translate and rotation/orientation data applied when the world is built.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.rs2.buffer import Buffer

TYPE_CENTREPIECE = 10


@dataclass
class LocType:
    id: int
    name: str | None = None
    examine: str | None = None
    model_ids: list[int] | None = None
    model_kinds: list[int] | None = None
    src_color: list[int] = field(default_factory=list)
    dst_color: list[int] = field(default_factory=list)
    size_x: int = 1
    size_z: int = 1
    scale_x: int = 128
    scale_y: int = 128
    scale_z: int = 128
    translate_x: int = 0
    translate_y: int = 0
    translate_z: int = 0
    invert: bool = False
    seq_id: int = -1
    light_ambient: int = 0
    light_attenuation: int = 0
    actions: list[str | None] = field(default_factory=list)

    def kinds(self) -> list[int]:
        if self.model_kinds:
            return list(self.model_kinds)
        if self.model_ids:
            return [TYPE_CENTREPIECE]
        return []

    def model_ids_for_kind(self, kind: int) -> list[int]:
        """Model id(s) for a given kind (mirrors LocType.getModel selection)."""
        if not self.model_ids:
            return []
        if self.model_kinds is None:
            # Only kind 10 is valid; all model ids merge into one centrepiece.
            if kind != TYPE_CENTREPIECE:
                return []
            return list(self.model_ids)
        for i, k in enumerate(self.model_kinds):
            if k == kind:
                return [self.model_ids[i]]
        return []


def _read_i16(buf: Buffer) -> int:
    value = buf.read_u16()
    if value > 32767:
        value -= 0x10000
    return value


def decode_loc_types(loc_dat: bytes, loc_idx: bytes) -> dict[int, LocType]:
    """Ports LocType.unpack + per-entry LocType.read."""
    idx = Buffer(loc_idx)
    count = idx.read_u16()
    offsets: list[int] = []
    offset = 2
    for _ in range(count):
        offsets.append(offset)
        offset += idx.read_u16()

    out: dict[int, LocType] = {}
    for loc_id in range(count):
        buf = Buffer(loc_dat)
        buf.position = offsets[loc_id]
        out[loc_id] = _read_loc(loc_id, buf)
    return out


def _read_loc(loc_id: int, buf: Buffer) -> LocType:
    loc = LocType(id=loc_id)
    while True:
        code = buf.read_u8()
        if code == 0:
            break
        if code == 1:
            n = buf.read_u8()
            if n > 0:
                loc.model_kinds = []
                loc.model_ids = []
                for _ in range(n):
                    loc.model_ids.append(buf.read_u16())
                    loc.model_kinds.append(buf.read_u8())
        elif code == 2:
            loc.name = buf.read_string()
        elif code == 3:
            loc.examine = buf.read_string()
        elif code == 5:
            n = buf.read_u8()
            if n > 0:
                loc.model_kinds = None
                loc.model_ids = [buf.read_u16() for _ in range(n)]
        elif code == 14:
            loc.size_x = buf.read_u8()
        elif code == 15:
            loc.size_z = buf.read_u8()
        elif code == 17:
            pass  # solid = false
        elif code == 18:
            pass  # blocksProjectiles = false
        elif code == 19:
            buf.read_u8()  # interactable
        elif code == 21:
            pass  # adjustToTerrain
        elif code == 22:
            pass  # dynamic
        elif code == 23:
            pass  # occludes
        elif code == 24:
            loc.seq_id = buf.read_u16()
            if loc.seq_id == 65535:
                loc.seq_id = -1
        elif code == 28:
            buf.read_u8()  # decorOffset
        elif code == 29:
            loc.light_ambient = buf.read_i8()
        elif code == 39:
            loc.light_attenuation = buf.read_i8()
        elif 30 <= code < 39:
            # LocType right-click options (codes 30-38 -> actions[0..8]). "hidden"
            # marks an option the client suppresses.
            idx = code - 30
            text = buf.read_string()
            while len(loc.actions) <= idx:
                loc.actions.append(None)
            loc.actions[idx] = None if text.lower() == "hidden" else text
        elif code == 40:
            n = buf.read_u8()
            loc.src_color = []
            loc.dst_color = []
            for _ in range(n):
                loc.src_color.append(buf.read_u16())
                loc.dst_color.append(buf.read_u16())
        elif code == 60:
            buf.read_u16()  # mapfunctionIcon
        elif code == 62:
            loc.invert = True
        elif code == 64:
            pass  # castShadow = false
        elif code == 65:
            loc.scale_x = buf.read_u16()
        elif code == 66:
            loc.scale_z = buf.read_u16()
        elif code == 67:
            loc.scale_y = buf.read_u16()
        elif code == 68:
            buf.read_u16()  # mapsceneIcon
        elif code == 69:
            buf.read_u8()  # interactionSideFlags
        elif code == 70:
            loc.translate_x = _read_i16(buf)
        elif code == 71:
            loc.translate_y = _read_i16(buf)
        elif code == 72:
            loc.translate_z = _read_i16(buf)
        elif code == 73:
            pass  # important
        elif code == 74:
            pass  # decorative
        elif code == 75:
            buf.read_u8()  # supportsObj
        elif code == 77:
            buf.read_u16()  # varbit
            buf.read_u16()  # varp
            override_count = buf.read_u8()
            for _ in range(override_count + 1):
                buf.read_u16()
        else:
            break
    return loc


def loc_recolor_map(loc: LocType) -> dict[int, int]:
    recolor: dict[int, int] = {}
    for src, dst in zip(loc.src_color, loc.dst_color):
        recolor[src] = dst
    return recolor
