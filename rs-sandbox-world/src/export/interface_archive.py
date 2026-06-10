"""Decode RS 317 interface (widget) definitions from the 'interface' archive.

Ports the client's ``RSInterface.unpack``: the ``data`` member of archive 3 holds
a flat stream of widget records. Each record carries layout (position is supplied
by the parent's child list), a component ``type`` and type-specific payload
(container children, sprite names, text, colours, inventory slots, ...).

Only the fields the static renderer needs are kept; cs1 scripts / conditions /
model + listbox payloads are parsed for stream alignment but mostly discarded.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.rs2.buffer import Buffer

# Standard 317/377 cache archive holding interface definitions.
INTERFACE_ARCHIVE_FILE_ID = 3


@dataclass
class Widget:
    id: int
    parent: int = -1
    type: int = 0
    option_type: int = 0
    content_type: int = 0
    width: int = 0
    height: int = 0
    # type 0 (container)
    scroll_max: int = 0
    hidden: bool = False
    children: list[tuple[int, int, int]] = field(default_factory=list)  # (id, x, y)
    # type 2 (inventory)
    inv_w: int = 0
    inv_h: int = 0
    inv_pad_x: int = 0
    inv_pad_y: int = 0
    inv_sprites: list[tuple[int, int, str] | None] = field(default_factory=list)
    # type 3 (rect)
    filled: bool = False
    # type 4 / 8 (text)
    center: bool = False
    font: int = 0
    shadow: bool = False
    dis_text: str = ""
    en_text: str = ""
    # colours
    dis_color: int = 0
    en_color: int = 0
    # type 5 (sprite) -> "name,index"
    dis_sprite: str = ""
    en_sprite: str = ""


def _sword(b: Buffer) -> int:
    v = b.read_u16()
    return v - 65536 if v >= 32768 else v


def unpack_interfaces(data: bytes) -> dict[int, Widget]:
    b = Buffer(data)
    b.read_u16()  # declared cache size (unused)
    out: dict[int, Widget] = {}
    parent = -1
    while b.position < len(data):
        wid = b.read_u16()
        if wid == 65535:
            parent = b.read_u16()
            wid = b.read_u16()
        w = Widget(id=wid, parent=parent)
        out[wid] = w
        w.type = b.read_u8()
        w.option_type = b.read_u8()
        w.content_type = b.read_u16()
        w.width = b.read_u16()
        w.height = b.read_u16()
        b.read_u8()  # alpha
        if b.read_u8() != 0:  # hover/anInt230 -> second byte when nonzero
            b.read_u8()
        n = b.read_u8()  # conditions
        for _ in range(n):
            b.read_u8()
            b.read_u16()
        n = b.read_u8()  # cs1 scripts
        for _ in range(n):
            for _ in range(b.read_u16()):
                b.read_u16()

        t = w.type
        if t == 0:
            w.scroll_max = b.read_u16()
            w.hidden = b.read_u8() == 1
            for _ in range(b.read_u16()):
                cid = b.read_u16()
                cx = _sword(b)
                cy = _sword(b)
                w.children.append((cid, cx, cy))
        if t == 1:
            b.read_u16()
            b.read_u8()
        if t == 2:
            w.inv_w = w.width
            w.inv_h = w.height
            b.read_u8()  # draggable
            b.read_u8()  # interchangeable
            b.read_u8()  # usable
            b.read_u8()  # swap items on drag
            w.inv_pad_x = b.read_u8()
            w.inv_pad_y = b.read_u8()
            for _ in range(20):
                if b.read_u8() == 1:
                    sx = _sword(b)
                    sy = _sword(b)
                    name = b.read_string()
                    w.inv_sprites.append((sx, sy, name))
                else:
                    w.inv_sprites.append(None)
            for _ in range(5):
                b.read_string()  # menu actions
        if t == 3:
            w.filled = b.read_u8() == 1
        if t == 4 or t == 1:
            w.center = b.read_u8() == 1
            w.font = b.read_u8()
            w.shadow = b.read_u8() == 1
        if t == 4:
            w.dis_text = b.read_string()
            w.en_text = b.read_string()
        if t == 8:
            w.dis_text = b.read_string()
        if t in (1, 3, 4):
            w.dis_color = b.read_u32()
        if t in (3, 4):
            w.en_color = b.read_u32()
            b.read_u32()  # disabled hover colour
            b.read_u32()  # enabled hover colour
        if t == 5:
            w.dis_sprite = b.read_string()
            w.en_sprite = b.read_string()
        if t == 6:
            for _ in range(4):
                if b.read_u8() != 0:
                    b.read_u8()
            b.read_u16()  # zoom
            b.read_u16()  # model rot x
            b.read_u16()  # model rot y
        if t == 7:
            b.read_u8()  # centered
            b.read_u8()  # font
            b.read_u8()  # shadow
            b.read_u32()  # colour
            b.read_u16()  # pad x
            b.read_u16()  # pad y
            b.read_u8()  # has actions
            for _ in range(5):
                b.read_string()
        if w.option_type == 2 or t == 2:
            b.read_string()  # selected action
            b.read_string()  # spell name
            b.read_u16()  # spell usable-on flags
        if w.option_type in (1, 4, 5, 6):
            b.read_string()  # tooltip
    return out


def build_interface_cache(cache) -> dict[int, Widget]:
    """Decode every interface widget from archive 3's ``data`` member."""
    raw = cache.read_archive(INTERFACE_ARCHIVE_FILE_ID)
    if raw is None:
        raise RuntimeError("interface archive (3) missing from cache")

    from src.cache.file_archive import FileArchive

    archive = FileArchive.load(raw)
    data = archive.read("data")
    if not data:
        raise RuntimeError("'data' member missing from interface archive")
    return unpack_interfaces(data)
