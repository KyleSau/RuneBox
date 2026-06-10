"""Decode RS 317/377 bitmap fonts (p11_full, etc.) from the title archive.

Ports the client's ``BitmapFont(FileArchive, name, quill)`` constructor: a named
``<name>.dat`` member holds the packed glyph masks while the shared ``index.dat``
member holds, per character, the draw offset, glyph size and pixel layout. The
viewer uses this to render hit-splat damage with the exact font the 317 client
uses (``fontPlain11`` = ``p11_full``), drawn white with a 1px black shadow.
"""

from __future__ import annotations

import io

from src.rs2.buffer import Buffer

# Standard 317/377 cache archive holding the title screen + UI fonts.
TITLE_ARCHIVE_FILE_ID = 1

# Fonts the viewer needs (name -> quill flag, matching Game.loadGame()).
# Order matches the client's font array, so a font index from an interface
# definition can be mapped via FONT_BY_INDEX below.
NEEDED_FONTS = {
    "p11_full": False,
    "p12_full": False,
    "b12_full": False,
    "q8_full": False,
}

# RSInterface font index -> font name (Game.loadGame() load order).
FONT_BY_INDEX = ["p11_full", "p12_full", "b12_full", "q8_full"]


def decode_bitmap_font(dat_bytes: bytes, idx_bytes: bytes) -> dict:
    """Decode one bitmap font into per-character masks + metrics."""
    dat = Buffer(dat_bytes)
    idx = Buffer(idx_bytes)
    idx.position = dat.read_u16() + 4

    k = idx.read_u8()
    if k > 0:
        idx.position += 3 * (k - 1)

    off_x = [0] * 256
    off_y = [0] * 256
    widths = [0] * 256
    heights = [0] * 256
    advance = [0] * 256
    masks: list[bytearray] = [bytearray() for _ in range(256)]
    font_height = 0

    for c in range(256):
        off_x[c] = idx.read_u8()
        off_y[c] = idx.read_u8()
        w = widths[c] = idx.read_u16()
        h = heights[c] = idx.read_u16()
        store_order = idx.read_u8()

        length = w * h
        mask = bytearray(length)
        if store_order == 0:
            for i in range(length):
                mask[i] = dat.read_u8()
        elif store_order == 1:
            for x in range(w):
                for y in range(h):
                    mask[x + (y * w)] = dat.read_u8()
        masks[c] = mask

        if h > font_height and c < 128:
            font_height = h

        # Simple kerning (ports BitmapFont): trim left/right padding columns.
        off_x[c] = 1
        advance[c] = w + 2

        acc = 0
        for y in range(h // 7, h):
            acc += mask[y * w]
        if acc <= (h // 7):
            advance[c] -= 1
            off_x[c] = 0

        acc = 0
        for y in range(h // 7, h):
            acc += mask[(w - 1) + (y * w)]
        if acc <= (h // 7):
            advance[c] -= 1

    advance[ord(" ")] = advance[ord("i")]

    return {
        "ox": off_x,
        "oy": off_y,
        "w": widths,
        "h": heights,
        "advance": advance,
        "mask": masks,
        "height": font_height,
    }


def string_width(font: dict, text: str) -> int:
    return sum(font["advance"][ord(ch)] for ch in text)


def render_text(font: dict, text: str, rgb: int = 0xFFFFFF, shadow: bool = True,
                crop: bool = True):
    """Render ``text`` to an RGBA image (coloured glyphs + 1px black shadow).

    Mirrors Game.drawHitmarks: the black shadow is the same string offset by
    (+1, +1) under the coloured text. With ``crop`` the image is trimmed to the
    ink box (good for centring a single number); without it the full line box is
    kept so a left baseline stays consistent across labels (interface text).
    """
    from PIL import Image

    advance = font["advance"]
    off_x = font["ox"]
    off_y = font["oy"]
    widths = font["w"]
    heights = font["h"]
    masks = font["mask"]
    fh = font["height"]

    pad = 1 if shadow else 0
    img_w = max(string_width(font, text) + pad + 1, 1)
    img_h = max(fh + pad + 1, 1)
    img = Image.new("RGBA", (img_w, img_h), (0, 0, 0, 0))
    px = img.load()

    def blit(origin_x: int, origin_y: int, color: tuple[int, int, int, int]) -> None:
        pen = origin_x
        for ch in text:
            c = ord(ch)
            gw = widths[c]
            gh = heights[c]
            mask = masks[c]
            gx = pen + off_x[c]
            gy = origin_y + off_y[c]
            for yy in range(gh):
                row = yy * gw
                for xx in range(gw):
                    if mask[row + xx] != 0:
                        x = gx + xx
                        y = gy + yy
                        if 0 <= x < img_w and 0 <= y < img_h:
                            px[x, y] = color
            pen += advance[c]

    if shadow:
        blit(1, 1, (0, 0, 0, 255))
    blit(0, 0, ((rgb >> 16) & 0xFF, (rgb >> 8) & 0xFF, rgb & 0xFF, 255))

    # Crop to the actual ink (glyphs + shadow). The per-glyph advance leaves trailing
    # padding that biases the text up/left inside the box, so a caller that centres the
    # image would render the number off-centre. A tight crop centres cleanly.
    if crop:
        bbox = img.getbbox()
        if bbox:
            img = img.crop(bbox)
    return img


def _to_png(img) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def build_font_context(cache) -> dict:
    """Load + decode the fonts the viewer needs from the title archive."""
    raw = cache.read_archive(TITLE_ARCHIVE_FILE_ID)
    if raw is None:
        raise RuntimeError("title archive (1) missing from cache")

    from src.cache.file_archive import FileArchive

    archive = FileArchive.load(raw)
    idx_bytes = archive.read("index.dat")
    if not idx_bytes:
        raise RuntimeError("index.dat missing from title archive")

    fonts: dict[str, dict] = {}
    for name in NEEDED_FONTS:
        dat_bytes = archive.read(f"{name}.dat")
        if not dat_bytes:
            continue
        try:
            fonts[name] = decode_bitmap_font(dat_bytes, idx_bytes)
        except Exception:
            continue
    return fonts


def render_font_png(fonts: dict, name: str, text: str, rgb: int = 0xFFFFFF) -> bytes | None:
    font = fonts.get(name)
    if font is None:
        return None
    safe = "".join(ch for ch in text if 0 <= ord(ch) < 256)
    if not safe:
        return None
    return _to_png(render_text(font, safe, rgb=rgb, shadow=True))


def build_font_manifest(fonts: dict) -> dict:
    return {
        "source": "377-cache",
        "note": "Title-archive bitmap fonts rendered to PNG (white + 1px shadow).",
        "fonts": {name: font["height"] for name, font in fonts.items()},
    }
