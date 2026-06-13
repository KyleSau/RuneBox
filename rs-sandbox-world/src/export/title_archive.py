"""Decode RS 317/377 title-screen assets from the title archive (idx0 slot 1)."""

from __future__ import annotations

import io

from src.export.font_archive import TITLE_ARCHIVE_FILE_ID
from src.export.sprite_archive import decode_media_sprite

TITLE_SPRITES = {
    "titlebox": 1,
    "titlebutton": 1,
    "runes": 12,
    "logo": 1,
}

# 317 Game.loadTitleBackground — blitOpaque(dx,dy) draws src onto buffer at (dx,dy):
# buffer[bx,by] = src[bx - dx, by - dy]
_FIRST_PASS = {
    "title0": (0, 0),
    "title1": (-637, 0),
    "title2": (-128, 0),
    "title3": (-202, -371),
    "title4": (-202, -171),
    "title5": (0, -265),
    "title6": (-562, -265),
    "title7": (-128, -171),
    "title8": (-562, -171),
}
_SECOND_PASS = {
    "title0": (382, 0),
    "title1": (-255, 0),
    "title2": (254, 0),
    "title3": (180, -371),
    "title4": (180, -171),
    "title5": (382, -265),
    "title6": (-180, -265),
    "title7": (254, -171),
    "title8": (-180, -171),
}
_BUFFER_SIZE = {
    "title0": (128, 265),
    "title1": (128, 265),
    "title2": (509, 171),
    "title3": (360, 132),
    "title4": (360, 200),
    "title5": (202, 238),
    "title6": (203, 238),
    "title7": (74, 94),
    "title8": (75, 94),
}
_SCREEN_POS = {
    "title0": (0, 0),
    "title1": (637, 0),
    "title2": (128, 0),
    "title3": (202, 371),
    "title4": (202, 171),
    "title5": (0, 265),
    "title6": (562, 265),
    "title7": (128, 171),
    "title8": (562, 171),
}
_FLAME_BUFFERS = ("title0", "title1")
_STATIC_BUFFERS = tuple(k for k in _SCREEN_POS if k not in _FLAME_BUFFERS)


def _title_archive(cache):
    raw = cache.read_archive(TITLE_ARCHIVE_FILE_ID)
    if raw is None:
        raise RuntimeError("title archive (1) missing from cache")
    from src.cache.file_archive import FileArchive

    archive = FileArchive.load(raw)
    idx = archive.read("index.dat")
    if not idx:
        raise RuntimeError("index.dat missing from title archive")
    return archive, idx


def build_title_context(cache) -> dict:
    """Pre-decode title UI sprites to PNG bytes."""
    archive, idx = _title_archive(cache)
    sprites: dict[str, list[bytes]] = {}
    for name, max_frames in TITLE_SPRITES.items():
        dat = archive.read(f"{name}.dat")
        if not dat:
            continue
        frames: list[bytes] = []
        for i in range(max_frames):
            try:
                from PIL import Image

                img = decode_media_sprite(dat, idx, i)
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                frames.append(buf.getvalue())
            except Exception:
                break
        if frames:
            sprites[name] = frames
    return {"sprites": sprites, "archive": archive}


def title_sprite_png(ctx: dict, name: str, index: int) -> bytes | None:
    frames = ctx.get("sprites", {}).get(name)
    if not frames or index < 0 or index >= len(frames):
        return None
    return frames[index]


def _title_jpeg(cache):
    archive, idx = _title_archive(cache)
    jpg = archive.read("title.dat")
    if not jpg:
        raise RuntimeError("title.dat missing from title archive")
    from PIL import Image

    return Image.open(io.BytesIO(jpg)).convert("RGBA"), archive, idx


def _blit_into_buffer(buf, src, dx: int, dy: int) -> None:
    """317 Image24.blitOpaque(dx,dy) into a buffer: buf[bx,by] = src[bx - dx, by - dy]."""
    bw, bh = buf.size
    spx = buf.load()
    src_px = src.load()
    sw, sh = src.size
    for by in range(bh):
        for bx in range(bw):
            sx, sy = bx - dx, by - dy
            if 0 <= sx < sw and 0 <= sy < sh:
                spx[bx, by] = src_px[sx, sy]


def _compose_title_buffers(src) -> dict:
    """Both loadTitleBackground passes into per-layer buffers (matches 317 client)."""
    from PIL import Image

    src_flip = src.transpose(Image.FLIP_LEFT_RIGHT)
    buffers: dict[str, object] = {}
    for name, (w, h) in _BUFFER_SIZE.items():
        layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        _blit_into_buffer(layer, src, *_FIRST_PASS[name])
        _blit_into_buffer(layer, src_flip, *_SECOND_PASS[name])
        buffers[name] = layer
    return buffers


def render_title_background(cache) -> bytes:
    """Static stone background (no animated flame columns — those are canvas overlays)."""
    from PIL import Image

    src, archive, idx = _title_jpeg(cache)
    buffers = _compose_title_buffers(src)
    canvas = Image.new("RGBA", (765, 503), (0, 0, 0, 255))

    for name in _STATIC_BUFFERS:
        sx, sy = _SCREEN_POS[name]
        layer = buffers[name]
        canvas.paste(layer, (sx, sy), layer)

    buf = io.BytesIO()
    canvas.save(buf, format="PNG")
    return buf.getvalue()


def render_title_logo(cache) -> bytes | None:
    """RuneScape title logo sprite (logo.dat frame 0) — composited separately on the client."""
    archive, idx = _title_archive(cache)
    logo_dat = archive.read("logo.dat")
    if not logo_dat:
        return None
    try:
        logo = decode_media_sprite(logo_dat, idx, 0)
        buf = io.BytesIO()
        logo.save(buf, format="PNG")
        return buf.getvalue()
    except Exception:
        return None


def render_flame_background(cache, side: str = "right") -> bytes:
    """Flame column mask (128×265) from composed title0/title1 buffers."""
    buf = io.BytesIO()
    src, _, _ = _title_jpeg(cache)
    buffers = _compose_title_buffers(src)
    key = "title0" if side == "left" else "title1"
    buffers[key].save(buf, format="PNG")
    return buf.getvalue()
