"""Rasterize a decoded RS 317 interface (widget tree) to a flat RGBA PNG.

This is a *static* render of the default (non-hovered) state, intended to back
the viewer's side-panel tabs (equipment, skills, prayer, magic, logout, music).
It composites the component types that carry visible chrome -- containers (0),
inventory ghost slots (2), rectangles (3), text (4/8) and sprites (5) -- while
skipping 3D model components (6) and hover-only hidden containers, matching what
the client shows before the user interacts.
"""

from __future__ import annotations

import io

from src.export.font_archive import FONT_BY_INDEX, render_text, string_width
from src.export.interface_archive import Widget

# Side-panel content area (the inventory background is 190x261).
PANEL_W = 190
PANEL_H = 261


def _parse_sprite(ref: str) -> tuple[str, int] | None:
    if not ref:
        return None
    comma = ref.rfind(",")
    if comma < 0:
        return None
    try:
        return ref[:comma], int(ref[comma + 1:])
    except ValueError:
        return None


class InterfaceRenderContext:
    def __init__(self, interfaces: dict[int, Widget], sprites, fonts: dict):
        self.interfaces = interfaces
        self.sprites = sprites  # MediaSprites
        self.fonts = fonts


def _blit(canvas, img, x: int, y: int, clip: tuple[int, int, int, int]) -> None:
    if img is None:
        return
    cx0, cy0, cx1, cy1 = clip
    iw, ih = img.size
    nx0 = max(x, cx0, 0)
    ny0 = max(y, cy0, 0)
    nx1 = min(x + iw, cx1, canvas.width)
    ny1 = min(y + ih, cy1, canvas.height)
    if nx1 <= nx0 or ny1 <= ny0:
        return
    sub = img.crop((nx0 - x, ny0 - y, nx1 - x, ny1 - y))
    if sub.mode != "RGBA":
        sub = sub.convert("RGBA")
    canvas.alpha_composite(sub, (nx0, ny0))


def _draw_rect(canvas, x, y, w, h, color, filled, clip):
    from PIL import Image, ImageDraw

    if w <= 0 or h <= 0:
        return
    rgb = ((color >> 16) & 0xFF, (color >> 8) & 0xFF, color & 0xFF, 255)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if filled:
        d.rectangle([0, 0, w - 1, h - 1], fill=rgb)
    else:
        d.rectangle([0, 0, w - 1, h - 1], outline=rgb)
    _blit(canvas, img, x, y, clip)


def _draw_text(ctx, canvas, w: Widget, x, y, clip):
    text = w.dis_text or ""
    if not text:
        return
    text = text.replace("%1", "1").replace("%2", "1").replace("%3", "1")
    name = FONT_BY_INDEX[w.font] if 0 <= w.font < len(FONT_BY_INDEX) else "p11_full"
    font = ctx.fonts.get(name) or ctx.fonts.get("p11_full")
    if font is None:
        return
    color = w.dis_color & 0xFFFFFF
    lines = text.replace("\\n", "\n").split("\n")
    line_h = font["height"] + 1
    for i, line in enumerate(lines):
        safe = "".join(ch for ch in line if 0 <= ord(ch) < 256)
        if not safe.strip():
            continue
        img = render_text(font, safe, rgb=color, shadow=w.shadow, crop=False)
        tx = x
        if w.center:
            tx = x + (w.width - string_width(font, safe)) // 2
        _blit(canvas, img, tx, y + i * line_h, clip)


def _draw_sprite(ctx, canvas, ref: str, x, y, clip):
    parsed = _parse_sprite(ref)
    if parsed is None:
        return
    name, index = parsed
    _blit(canvas, ctx.sprites.image(name, index), x, y, clip)


# Inventory item cell size (client draws 32x32 item sprites on the grid step).
_INV_CELL = 32


def _draw_inventory(ctx, canvas, w: Widget, x, y, clip):
    # Ports the client's type-2 draw: each empty slot's ghost sprite is placed at
    # its grid cell (col*(32+padX), row*(32+padY)) plus the slot's own offset.
    # Equipment (1688) uses those offsets to bend the 3x5 grid into the doll shape.
    cols = max(w.inv_w, 1)
    for slot, entry in enumerate(w.inv_sprites):
        if slot >= w.inv_w * w.inv_h or entry is None:
            continue
        sx, sy, name = entry
        if not name:
            continue
        col = slot % cols
        row = slot // cols
        px = x + col * (_INV_CELL + w.inv_pad_x) + sx
        py = y + row * (_INV_CELL + w.inv_pad_y) + sy
        _draw_sprite(ctx, canvas, name, px, py, clip)


def _draw(ctx, canvas, w: Widget, x, y, clip):
    t = w.type
    if t == 0:
        if w.hidden:
            return
        cx0, cy0, cx1, cy1 = clip
        nclip = (max(cx0, x), max(cy0, y),
                 min(cx1, x + w.width), min(cy1, y + w.height))
        for (cid, dx, dy) in w.children:
            child = ctx.interfaces.get(cid)
            if child is not None:
                _draw(ctx, canvas, child, x + dx, y + dy, nclip)
    elif t == 2:
        _draw_inventory(ctx, canvas, w, x, y, clip)
    elif t == 3:
        _draw_rect(canvas, x, y, w.width, w.height, w.dis_color, w.filled, clip)
    elif t in (4, 8):
        _draw_text(ctx, canvas, w, x, y, clip)
    elif t == 5:
        _draw_sprite(ctx, canvas, w.dis_sprite or w.en_sprite, x, y, clip)
    # type 6 (model) and other interactive types are skipped for the static view.


def render_interface_png(ctx: InterfaceRenderContext, root_id: int,
                         width: int = PANEL_W, height: int = PANEL_H) -> bytes | None:
    from PIL import Image

    root = ctx.interfaces.get(root_id)
    if root is None:
        return None
    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    _draw(ctx, canvas, root, 0, 0, (0, 0, width, height))
    buf = io.BytesIO()
    canvas.save(buf, format="PNG")
    return buf.getvalue()


# Side-panel tab -> root interface id (317 default tabInterfaceIDs subset).
TAB_INTERFACES = {
    "equipment": 1644,
    "skills": 3917,
    "prayer": 5608,
    "magic": 1151,
    "logout": 2449,
    "music": 962,
}


def build_interface_render_context(cache) -> InterfaceRenderContext:
    from src.export.interface_archive import build_interface_cache
    from src.export.sprite_archive import MediaSprites
    from src.export.font_archive import build_font_context

    interfaces = build_interface_cache(cache)
    sprites = MediaSprites(cache)
    fonts = build_font_context(cache)
    return InterfaceRenderContext(interfaces, sprites, fonts)


def build_interface_manifest(ctx: InterfaceRenderContext) -> dict:
    return {
        "source": "377-cache",
        "note": "317 interface widgets rendered to PNG (static default state).",
        "tabs": {name: rid for name, rid in TAB_INTERFACES.items()
                 if rid in ctx.interfaces},
    }
