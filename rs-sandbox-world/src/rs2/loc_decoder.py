"""Decode loc.dat / loc.idx (LocType - in-game scenery objects).

Ports LocType.unpack / LocType.read (377 client). ``loc.idx`` is a u16 count
followed by per-entry u16 record lengths; the running sum gives each entry's
offset into ``loc.dat`` (entry 0 starts at offset 2). Scenery models are keyed
by a "kind" (10 = centrepiece, 0-3 walls, etc.) and carry recolour, scale,
translate and rotation/orientation data applied when the world is built.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from src.rs2.buffer import Buffer

from src.rs2.object_id_names import lookup_object_id_name

TYPE_CENTREPIECE = 10


@dataclass
class LocType:
    id: int
    name: str | None = None
    examine: str | None = None
    debug_name: str | None = None
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
    interactable: bool = False

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


def _humanize_debug_name(text: str) -> str:
    s = text.replace("_", " ").strip()
    if not s:
        return s
    return s[0].upper() + s[1:]


def _is_placeholder_loc_name(name: str | None, loc_id: int) -> bool:
    if not name:
        return True
    n = name.strip()
    if not n or re.match(r"^loc_\d+$", n, re.I):
        return True
    if n.lower() == "object":
        return True
    return bool(re.match(rf"^Object\s*\({loc_id}\)$", n, re.I))


def _name_from_examine(examine: str) -> str:
    text = examine.strip()
    lower = text.lower()
    if lower.startswith("it's "):
        text = text[5:].strip()
    elif lower.startswith("it is "):
        text = text[6:].strip()
    elif lower.startswith("this is "):
        text = text[8:].strip()
    return text.split(".")[0].split("!")[0].split("?")[0].strip()[:48] or text[:48]


def loc_menu_name(loc: LocType) -> str | None:
    """317 handleLocOptions uses LocType.name verbatim (opcode 2)."""
    name = (loc.name or "").strip()
    if name and not re.match(r"^loc_\d+$", name, re.I):
        return name
    return None


def loc_display_name(loc: LocType, kind: int | None = None) -> str:
    """Human label when loc.dat name is unset — never generic kind names like 'Wall'."""
    menu = loc_menu_name(loc)
    if menu:
        return menu
    if loc.examine:
        derived = _name_from_examine(loc.examine)
        if derived:
            return derived
    if loc.debug_name:
        return _humanize_debug_name(loc.debug_name)[:48]
    for action in loc.actions or []:
        if action:
            return f"{action} object"
    alias = lookup_object_id_name(loc.id)
    if alias:
        return alias
    return f"Object ({loc.id})"


def loc_examine_text(loc: LocType) -> str:
    """317 examineLoc: type.examine else \"It's a {name}.\" """
    if loc.examine:
        return loc.examine
    menu = loc_menu_name(loc)
    if menu:
        return f"It's a {menu}."
    return ""


def loc_is_interactable(loc: LocType) -> bool:
    """Matches LocType.read post-process (opcode 19 + default rule)."""
    return loc.interactable


def _read_i16(buf: Buffer) -> int:
    value = buf.read_u16()
    if value > 32767:
        value -= 0x10000
    return value


def _read_i32(buf: Buffer) -> int:
    value = buf.read_u32()
    if value >= 0x80000000:
        value -= 0x100000000
    return value


def _skip_params(buf: Buffer) -> None:
    count = buf.read_u8()
    for _ in range(count):
        buf.read_u24()
        is_string = buf.read_u8() == 1
        if is_string:
            buf.read_string()
        else:
            _read_i32(buf)


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


def _finalize_loc_interactable(loc: LocType, interactable_opcode: int) -> None:
    """Ports LocType.read tail — default interactable when opcode 19 absent."""
    if interactable_opcode != -1:
        return
    loc.interactable = bool(loc.model_ids) and (
        loc.model_kinds is None or loc.model_kinds[0] == TYPE_CENTREPIECE
    )
    if any(loc.actions):
        loc.interactable = True


def _read_loc(loc_id: int, buf: Buffer) -> LocType:
    loc = LocType(id=loc_id)
    interactable_opcode = -1
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
            interactable_opcode = buf.read_u8()
            if interactable_opcode == 1:
                loc.interactable = True
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
        elif code == 25:
            pass  # hasAlpha
        elif code == 28:
            buf.read_u8()  # decorOffset / wallWidth
        elif code == 29:
            loc.light_ambient = buf.read_i8()
        elif code == 39:
            loc.light_attenuation = buf.read_i8()
        elif 30 <= code < 35:
            # 377 client: five right-click options (codes 30-34).
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
        elif code == 61:
            buf.read_u16()  # category
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
            buf.read_u8()  # interactionSideFlags / forceApproach
        elif code == 70:
            loc.translate_x = _read_i16(buf)
        elif code == 71:
            loc.translate_y = _read_i16(buf)
        elif code == 72:
            loc.translate_z = _read_i16(buf)
        elif code == 73:
            pass  # important / forceDecor
        elif code == 74:
            pass  # breakRouteFinding
        elif code == 75:
            buf.read_u8()  # raiseObject / supportsObj
        elif code == 77:
            varbit = buf.read_u16()
            if varbit == 65535:
                varbit = -1
            varp = buf.read_u16()
            if varp == 65535:
                varp = -1
            override_count = buf.read_u8()
            for _ in range(override_count + 1):
                entry = buf.read_u16()
                if entry == 65535:
                    entry = -1
        elif code == 249:
            _skip_params(buf)
        elif code == 250:
            loc.debug_name = buf.read_string()
        else:
            # Unknown opcode — skip one byte already consumed; stop to avoid desync.
            break
    _finalize_loc_interactable(loc, interactable_opcode)
    return loc


def loc_recolor_map(loc: LocType) -> dict[int, int]:
    recolor: dict[int, int] = {}
    for src, dst in zip(loc.src_color, loc.dst_color):
        recolor[src] = dst
    return recolor
