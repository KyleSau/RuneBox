"""Decode RS 317/377 texture sprites (idx0 archive 6) into RGBA images.

Ports the client's ``Image8(archive, name, 0)`` constructor: each ``<id>.dat``
member begins with a u16 offset into the shared ``index.dat`` member, which
holds the crop size, palette and per-sprite dimensions. Palette index 0 is
transparent.
"""

from __future__ import annotations

from src.rs2.buffer import Buffer

TEXTURE_ARCHIVE_FILE_ID = 6
MAX_TEXTURES = 50


def _decode_sprite(dat_bytes: bytes, idx_bytes: bytes):
    from PIL import Image

    dat = Buffer(dat_bytes)
    idx = Buffer(idx_bytes)

    idx.position = dat.read_u16()
    crop_w = idx.read_u16()
    crop_h = idx.read_u16()
    palette_size = idx.read_u8()

    palette = [0] * palette_size
    for i in range(palette_size - 1):
        palette[i + 1] = idx.read_u24()

    # index is always 0 for textures, so no per-sprite skip loop is needed.
    crop_x = idx.read_u8()
    crop_y = idx.read_u8()
    width = idx.read_u16()
    height = idx.read_u16()
    pixel_order = idx.read_u8()

    pixel_count = width * height
    pixels = [0] * pixel_count

    if pixel_order == 0:
        for i in range(pixel_count):
            pixels[i] = dat.read_u8()
    elif pixel_order == 1:
        for x in range(width):
            for y in range(height):
                pixels[x + (y * width)] = dat.read_u8()

    img = Image.new("RGBA", (max(crop_w, 1), max(crop_h, 1)), (0, 0, 0, 0))
    px = img.load()
    off = 0
    for y in range(height):
        for x in range(width):
            entry = pixels[off]
            off += 1
            if entry == 0:
                continue
            rgb = palette[entry]
            px[x + crop_x, y + crop_y] = ((rgb >> 16) & 0xFF, (rgb >> 8) & 0xFF, rgb & 0xFF, 255)
    return img


def decode_textures(archive) -> dict[int, "object"]:
    """Decode every texture sprite present in a loaded ``FileArchive``."""
    idx_bytes = archive.read("index.dat")
    if not idx_bytes:
        return {}

    images: dict[int, object] = {}
    for texture_id in range(MAX_TEXTURES):
        dat_bytes = archive.read(f"{texture_id}.dat")
        if not dat_bytes:
            continue
        try:
            images[texture_id] = _decode_sprite(dat_bytes, idx_bytes)
        except Exception:
            continue
    return images


def load_texture_images(cache) -> dict[int, "object"]:
    """Read archive 6 from a ``CacheReader`` and decode all textures to RGBA."""
    raw = cache.read_archive(TEXTURE_ARCHIVE_FILE_ID)
    if raw is None:
        return {}

    from src.cache.file_archive import FileArchive

    try:
        archive = FileArchive.load(raw)
    except Exception:
        return {}
    return decode_textures(archive)


def build_texture_context(cache) -> dict[int, bytes]:
    """Decode all textures and return ``{id: PNG bytes}`` for HTTP serving.

    The RGBA crop is composited onto an opaque background (palette index 0 is
    transparent in the source, but ground tiles want a solid material) so the
    texture tiles cleanly when wrapped on a plane.
    """
    import io

    from PIL import Image

    images = load_texture_images(cache)
    out: dict[int, bytes] = {}
    for tex_id, img in images.items():
        try:
            flat = Image.new("RGB", img.size, (0, 0, 0))
            flat.paste(img, (0, 0), img)
            buf = io.BytesIO()
            flat.save(buf, format="PNG")
            out[tex_id] = buf.getvalue()
        except Exception:
            continue
    return out


def build_texture_manifest(ctx: dict[int, bytes]) -> dict:
    ids = sorted(ctx)
    return {
        "source": "377-cache",
        "note": "Draw3D textures (idx0 archive 6) for ground tiles / materials.",
        "count": len(ids),
        "textures": [{"id": i, "file": f"/api/texture/{i}.png"} for i in ids],
    }
