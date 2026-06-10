"""Decode RS 317/377 media-archive sprites (hitmarks, cross, etc.) to RGBA PNG.

Ports the client's ``Image24(FileArchive, name, index)`` constructor: a named
``<name>.dat`` member holds packed palette-indexed pixels for one or more sprite
frames, while the shared ``index.dat`` member holds, per frame, the crop offset,
dimensions and pixel layout. Frame 0 of a ``.dat`` begins with a u16 offset into
``index.dat`` pointing at that sprite-set's shared header (crop size + palette).
Palette index 0 is transparent.
"""

from __future__ import annotations

import io

from src.rs2.buffer import Buffer

# Standard 317/377 cache archive index holding UI sprites ("media").
MEDIA_ARCHIVE_FILE_ID = 4

# Sprite groups the viewer needs, with the max frame count to probe.
# NOTE: counts must not exceed the real frame count -- decoding past the last
# frame reads garbage dimensions out of index.dat and can allocate huge images.
NEEDED_SPRITES = {
    "hitmarks": 20,
    "cross": 8,
    # Fixed-mode interface chrome (inventory / equipment tab panel).
    "sideicons": 13,   # tab icons (3 = inventory, 4 = equipment)
    "redstone1": 1,    # selected-tab red stone background
    "redstone2": 1,
    "redstone3": 1,
    "invback": 1,      # 190x261 inventory/equipment panel background
    "wornicons": 12,   # equipment empty-slot ghost icons
}


def decode_media_sprite(dat_bytes: bytes, idx_bytes: bytes, index: int):
    """Decode one frame (``index``) of a named media sprite into an RGBA image."""
    from PIL import Image

    dat = Buffer(dat_bytes)
    idx = Buffer(idx_bytes)

    idx.position = dat.read_u16()
    crop_w = idx.read_u16()
    crop_h = idx.read_u16()
    palette_size = idx.read_u8()

    palette = [0] * palette_size
    for k in range(palette_size - 1):
        rgb = idx.read_u24()
        palette[k + 1] = rgb if rgb != 0 else 1

    # Skip preceding frames: each carries crop_x/crop_y (u8) + width/height (u16)
    # + layout (u8) in the index, and width*height bytes in the data member.
    for _ in range(index):
        idx.position += 2
        w = idx.read_u16()
        h = idx.read_u16()
        dat.position += w * h
        idx.position += 1

    crop_x = idx.read_u8()
    crop_y = idx.read_u8()
    width = idx.read_u16()
    height = idx.read_u16()
    layout = idx.read_u8()

    pixel_count = width * height
    pixels = [0] * pixel_count
    if layout == 0:
        for i in range(pixel_count):
            pixels[i] = palette[dat.read_u8()]
    elif layout == 1:
        for x in range(width):
            for y in range(height):
                pixels[x + (y * width)] = palette[dat.read_u8()]

    img = Image.new("RGBA", (max(crop_w, 1), max(crop_h, 1)), (0, 0, 0, 0))
    px = img.load()
    off = 0
    for y in range(height):
        for x in range(width):
            rgb = pixels[off]
            off += 1
            if rgb == 0:
                continue
            px[x + crop_x, y + crop_y] = ((rgb >> 16) & 0xFF, (rgb >> 8) & 0xFF, rgb & 0xFF, 255)
    return img


def _to_png(img) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def build_sprite_context(cache) -> dict:
    """Pre-decode needed media sprites to PNG bytes.

    Returns ``{name: [png_bytes, ...]}`` with one entry per decodable frame.
    """
    raw = cache.read_archive(MEDIA_ARCHIVE_FILE_ID)
    if raw is None:
        raise RuntimeError("media archive (4) missing from cache")

    from src.cache.file_archive import FileArchive

    archive = FileArchive.load(raw)
    idx_bytes = archive.read("index.dat")
    if not idx_bytes:
        raise RuntimeError("index.dat missing from media archive")

    out: dict[str, list[bytes]] = {}
    for name, max_frames in NEEDED_SPRITES.items():
        dat_bytes = archive.read(f"{name}.dat")
        if not dat_bytes:
            continue
        frames: list[bytes] = []
        for i in range(max_frames):
            try:
                frames.append(_to_png(decode_media_sprite(dat_bytes, idx_bytes, i)))
            except Exception:
                break
        if frames:
            out[name] = frames
    return out


class MediaSprites:
    """Lazily decode arbitrary ``name,index`` media sprites to RGBA images.

    The interface renderer references many sprite sets by name (miscgraphics,
    staticons, prayeroff, magicoff, ...), so rather than pre-listing them we
    decode each frame on first use and cache the resulting PIL image.
    """

    def __init__(self, cache):
        raw = cache.read_archive(MEDIA_ARCHIVE_FILE_ID)
        if raw is None:
            raise RuntimeError("media archive (4) missing from cache")
        from src.cache.file_archive import FileArchive

        self._archive = FileArchive.load(raw)
        self._idx = self._archive.read("index.dat")
        if not self._idx:
            raise RuntimeError("index.dat missing from media archive")
        self._dat_cache: dict[str, bytes | None] = {}
        self._img_cache: dict[tuple[str, int], object] = {}

    def _dat(self, name: str) -> bytes | None:
        if name not in self._dat_cache:
            self._dat_cache[name] = self._archive.read(f"{name}.dat") or None
        return self._dat_cache[name]

    def image(self, name: str, index: int):
        key = (name, index)
        if key in self._img_cache:
            return self._img_cache[key]
        dat = self._dat(name)
        img = None
        if dat is not None and index >= 0:
            try:
                img = decode_media_sprite(dat, self._idx, index)
            except Exception:
                img = None
        self._img_cache[key] = img
        return img


def build_sprite_manifest(ctx: dict) -> dict:
    return {
        "source": "377-cache",
        "note": "Media-archive UI sprites (hitmarks, cross, tab interface) decoded to PNG.",
        "sprites": {name: len(frames) for name, frames in ctx.items()},
    }
