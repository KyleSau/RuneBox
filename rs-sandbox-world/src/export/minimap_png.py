"""Build a 317-style region minimap PNG from decoded terrain (flo underlay colours)."""

from __future__ import annotations

import io
from typing import TYPE_CHECKING

from src.rs2.flo_decoder import load_flo_types
from src.rs2.map_decoder import REGION_SIZE, RegionMap
from src.rs2.terrain_colors import build_region_tile_paints

if TYPE_CHECKING:
    from src.cache.cache_locator import CacheReader

# 317 draws 4×4 RGB blocks per tile in the 512-wide minimap buffer.
_PIXELS_PER_TILE = 4
_DEFAULT_RGB = (20, 28, 14)


def _average_rgba_corners(rgbs) -> tuple[int, int, int] | None:
    vis = [c for c in rgbs if c and len(c) >= 4 and c[3] > 0]
    if not vis:
        return None
    return (
        sum(c[0] for c in vis) // len(vis),
        sum(c[1] for c in vis) // len(vis),
        sum(c[2] for c in vis) // len(vis),
    )


def _texture_minimap_rgb(texture_id: int, textures: dict) -> tuple[int, int, int] | None:
    img = textures.get(texture_id)
    if img is None:
        return None
    w, h = img.size
    if w < 1 or h < 1:
        return None
    samples: list[tuple[int, int, int]] = []
    for u, v in ((0.25, 0.25), (0.75, 0.25), (0.5, 0.5), (0.25, 0.75), (0.75, 0.75)):
        r, g, b, a = img.getpixel((int(u * (w - 1)), int(v * (h - 1))))
        if a > 0:
            samples.append((r, g, b))
    if not samples:
        return None
    return (
        sum(s[0] for s in samples) // len(samples),
        sum(s[1] for s in samples) // len(samples),
        sum(s[2] for s in samples) // len(samples),
    )


def _tile_minimap_rgb(paint, textures: dict | None) -> tuple[int, int, int]:
    if paint is None:
        return _DEFAULT_RGB
    under = _average_rgba_corners([paint.sw, paint.se, paint.ne, paint.nw])
    if paint.overlay_shape >= 2:
        fg = _average_rgba_corners([paint.fg_sw, paint.fg_se, paint.fg_ne, paint.fg_nw])
        if fg:
            if under:
                return tuple(int(fg[i] * 0.6 + under[i] * 0.4) for i in range(3))  # type: ignore[return-value]
            return fg
    tex_rgb = None
    if paint.texture_id >= 0 and textures:
        tex_rgb = _texture_minimap_rgb(paint.texture_id, textures)
    if tex_rgb and under:
        return tuple(int(tex_rgb[i] * 0.55 + under[i] * 0.45) for i in range(3))  # type: ignore[return-value]
    if tex_rgb:
        return tex_rgb
    if under:
        return under
    return _DEFAULT_RGB


def build_region_minimap_png(
    region: RegionMap,
    cache: "CacheReader | None" = None,
    *,
    plane: int = 0,
) -> bytes | None:
    """Return PNG bytes for a north-up minimap of one 64×64 region."""
    from PIL import Image, ImageDraw

    if cache is None:
        return None

    flos = load_flo_types(cache)
    textures = None
    try:
        from src.export.texture_archive import load_texture_images

        textures = load_texture_images(cache)
    except Exception:
        textures = None

    paints = build_region_tile_paints(region, flos, plane=plane, textures=textures)
    tiles = region.plane(plane)
    scale = _PIXELS_PER_TILE
    w = h = REGION_SIZE * scale
    img = Image.new("RGBA", (w, h), (0, 0, 0, 255))
    pix = img.load()

    for x in range(REGION_SIZE):
        for z in range(REGION_SIZE):
            paint = paints[x][z]
            rgb = _tile_minimap_rgb(paint, textures)
            # RS minimap: screen-up is decreasing world Z; X mirrored to match 317 scene.
            for dy in range(scale):
                for dx in range(scale):
                    py = (REGION_SIZE - 1 - z) * scale + dy
                    px = (REGION_SIZE - 1 - x) * scale + dx
                    pix[px, py] = (*rgb, 255)

    draw = ImageDraw.Draw(img)
    wall_rgb = (0xEE, 0xEE, 0xEE)
    for x in range(REGION_SIZE):
        for z in range(REGION_SIZE):
            tile = tiles[x][z]
            if tile.settings & 0x4:
                sx = (REGION_SIZE - 1 - x) * scale
                sy = (REGION_SIZE - 1 - z) * scale
                draw.line([sx, sy, sx + scale - 1, sy], fill=wall_rgb, width=1)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
