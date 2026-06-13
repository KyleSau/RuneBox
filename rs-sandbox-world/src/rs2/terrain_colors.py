"""RS SceneBuilder-style terrain vertex colours from flo.dat + map tiles."""

from __future__ import annotations

from dataclasses import dataclass

from src.rs2.flo_decoder import FloType, decimate_hsl
from src.rs2.map_decoder import REGION_SIZE, RegionMap
from src.rs2.palette import build_palette, hsl_to_rgb

MAGENTA_RGB = 0xFF00FF


def mul_hsl(hsl: int, lightness: int) -> int:
    if hsl == -1:
        return 12345678
    lightness = (lightness * (hsl & 0x7F)) // 128
    lightness = max(2, min(126, lightness))
    return (hsl & 0xFF80) + lightness


def adjust_lightness(hsl: int, scalar: int) -> int:
    if hsl == -2:
        return 12345678
    if hsl == -1:
        scalar = max(0, min(127, scalar))
        return 127 - scalar
    scalar = (scalar * (hsl & 0x7F)) // 128
    scalar = max(2, min(126, scalar))
    return (hsl & 0xFF80) + scalar


@dataclass
class TilePaint:
    """Corner colours for one terrain layer (underlay and/or full-tile overlay)."""
    sw: tuple[int, int, int, int]
    se: tuple[int, int, int, int]
    ne: tuple[int, int, int, int]
    nw: tuple[int, int, int, int]
    texture_id: int = -1
    overlay_shape: int = 0
    overlay_rotation: int = 0
    fg_sw: tuple[int, int, int, int] | None = None
    fg_se: tuple[int, int, int, int] | None = None
    fg_ne: tuple[int, int, int, int] | None = None
    fg_nw: tuple[int, int, int, int] | None = None
    # Lit underlay corners (always from flo underlay + lightmap, even under overlays).
    under_sw: tuple[int, int, int, int] | None = None
    under_se: tuple[int, int, int, int] | None = None
    under_ne: tuple[int, int, int, int] | None = None
    under_nw: tuple[int, int, int, int] | None = None


_WHITE = (255, 255, 255, 255)
_DEFAULT_UNDERLAY = (40, 56, 28, 255)


def _height_grid(region: RegionMap, plane: int) -> list[list[int]]:
    """RS heightmap corners: tile (x,z).height is the SW vertex of that tile."""
    tiles = region.plane(plane)
    grid: list[list[int]] = [[0] * (REGION_SIZE + 1) for _ in range(REGION_SIZE + 1)]
    for gx in range(REGION_SIZE):
        for gz in range(REGION_SIZE):
            grid[gx][gz] = tiles[gx][gz].height
    for gz in range(REGION_SIZE):
        grid[REGION_SIZE][gz] = tiles[REGION_SIZE - 1][gz].height
    for gx in range(REGION_SIZE):
        grid[gx][REGION_SIZE] = tiles[gx][REGION_SIZE - 1].height
    grid[REGION_SIZE][REGION_SIZE] = tiles[REGION_SIZE - 1][REGION_SIZE - 1].height
    return grid


def _build_lightmap(heights: list[list[int]]) -> list[list[int]]:
    size = REGION_SIZE + 1
    lightmap = [[96] * size for _ in range(size)]
    light_ambient = 96
    light_attenuation = 768
    light_x, light_y, light_z = -50, -10, -50
    light_magnitude = (light_attenuation * int((light_x * light_x + light_y * light_y + light_z * light_z) ** 0.5)) >> 8

    for z in range(1, REGION_SIZE):
        for x in range(1, REGION_SIZE):
            dx = heights[x + 1][z] - heights[x - 1][z]
            dz = heights[x][z + 1] - heights[x][z - 1]
            length = int((dx * dx + 65536 + dz * dz) ** 0.5)
            if length == 0:
                continue
            normal_x = (dx << 8) // length
            normal_y = 65536 // length
            normal_z = (dz << 8) // length
            light = light_ambient + ((light_x * normal_x + light_y * normal_y + light_z * normal_z) // light_magnitude)
            lightmap[x][z] = light
    return lightmap


def _hsl_to_rgba(hsl: int, palette: list[int]) -> tuple[int, int, int, int]:
    if hsl in (-1, 12345678):
        return (40, 56, 28, 255)
    r, g, b = hsl_to_rgb(hsl, palette)
    return (r, g, b, 255)


def _average_texture_rgb(texture_id: int, textures: dict[int, object]) -> tuple[int, int, int, int]:
    img = textures.get(texture_id)
    if img is None:
        return (128, 128, 128, 255)
    w, h = img.size
    r, g, b, a = img.getpixel((w // 2, h // 2))
    if a == 0:
        return (128, 128, 128, 255)
    return (r, g, b, 255)


def _texture_corner_colors(
    texture_id: int,
    textures: dict[int, object] | None,
) -> tuple[tuple, tuple, tuple, tuple]:
    """Textured tiles sample archive-6 sprites; vertex colour is white."""
    if textures and texture_id in textures:
        return (_WHITE, _WHITE, _WHITE, _WHITE)
    rgb = _average_texture_rgb(texture_id, textures or {})
    return (rgb, rgb, rgb, rgb)


def _direct_base_color(tile, flos: list[FloType]) -> int:
    """Single-tile underlay HSL (no 5-tile blend kernel) for region border tiles."""
    flo_id = tile.underlay_id
    if flo_id <= 0 or flo_id > len(flos):
        return -1
    flo = flos[flo_id - 1]
    return decimate_hsl(flo.hue, flo.saturation, flo.lightness)


def _make_tile_paint(
    x0: int,
    z0: int,
    tile,
    base_color: int,
    flos: list[FloType],
    lightmap: list[list[int]],
    palette: list[int],
    textures: dict[int, object] | None,
) -> TilePaint | None:
    underlay_id = tile.underlay_id
    overlay_id = tile.overlay_id
    if underlay_id <= 0 and overlay_id <= 0:
        return None

    light_sw = lightmap[x0][z0]
    light_se = lightmap[x0 + 1][z0]
    light_ne = lightmap[x0 + 1][z0 + 1]
    light_nw = lightmap[x0][z0 + 1]

    under_sw = under_se = under_ne = under_nw = None
    if base_color != -1:
        under_sw = _hsl_to_rgba(mul_hsl(base_color, light_sw), palette)
        under_se = _hsl_to_rgba(mul_hsl(base_color, light_se), palette)
        under_ne = _hsl_to_rgba(mul_hsl(base_color, light_ne), palette)
        under_nw = _hsl_to_rgba(mul_hsl(base_color, light_nw), palette)

    if overlay_id <= 0:
        if base_color == -1:
            return None
        return TilePaint(
            sw=under_sw,
            se=under_se,
            ne=under_ne,
            nw=under_nw,
            under_sw=under_sw,
            under_se=under_se,
            under_ne=under_ne,
            under_nw=under_nw,
        )

    if overlay_id > len(flos):
        return None
    overlay = flos[overlay_id - 1]
    texture_id = overlay.texture_id
    shape = tile.overlay_path + 1
    rotation = tile.overlay_rotation

    c1_sw = under_sw if under_sw is not None else _DEFAULT_UNDERLAY
    c1_se = under_se if under_se is not None else _DEFAULT_UNDERLAY
    c1_ne = under_ne if under_ne is not None else _DEFAULT_UNDERLAY
    c1_nw = under_nw if under_nw is not None else _DEFAULT_UNDERLAY

    overlay_hsl = -1
    if texture_id < 0:
        if overlay.rgb == MAGENTA_RGB:
            return None
        overlay_hsl = decimate_hsl(overlay.hue, overlay.saturation, overlay.lightness)

    fg_sw = _hsl_to_rgba(adjust_lightness(overlay_hsl, light_sw), palette)
    fg_se = _hsl_to_rgba(adjust_lightness(overlay_hsl, light_se), palette)
    fg_ne = _hsl_to_rgba(adjust_lightness(overlay_hsl, light_ne), palette)
    fg_nw = _hsl_to_rgba(adjust_lightness(overlay_hsl, light_nw), palette)

    if texture_id >= 0:
        fg_sw, fg_se, fg_ne, fg_nw = _texture_corner_colors(texture_id, textures)

    if shape <= 1:
        return TilePaint(
            sw=fg_sw,
            se=fg_se,
            ne=fg_ne,
            nw=fg_nw,
            texture_id=texture_id,
            overlay_shape=1,
            overlay_rotation=rotation,
            under_sw=under_sw,
            under_se=under_se,
            under_ne=under_ne,
            under_nw=under_nw,
        )

    if base_color == -1 and texture_id < 0:
        return None

    return TilePaint(
        sw=c1_sw,
        se=c1_se,
        ne=c1_ne,
        nw=c1_nw,
        texture_id=texture_id if texture_id >= 0 else -1,
        overlay_shape=shape,
        overlay_rotation=rotation,
        fg_sw=fg_sw,
        fg_se=fg_se,
        fg_ne=fg_ne,
        fg_nw=fg_nw,
        under_sw=under_sw,
        under_se=under_se,
        under_ne=under_ne,
        under_nw=under_nw,
    )


def build_region_tile_paints(
    region: RegionMap,
    flos: list[FloType],
    *,
    plane: int = 0,
    textures: dict[int, object] | None = None,
) -> list[list[TilePaint | None]]:
    tiles = region.plane(plane)
    heights = _height_grid(region, plane)
    lightmap = _build_lightmap(heights)
    palette = build_palette()

    blend_chroma = [0] * REGION_SIZE
    blend_saturation = [0] * REGION_SIZE
    blend_lightness = [0] * REGION_SIZE
    blend_luminance = [0] * REGION_SIZE
    blend_magnitude = [0] * REGION_SIZE

    paints: list[list[TilePaint | None]] = [[None] * REGION_SIZE for _ in range(REGION_SIZE)]

    for x0 in range(-5, REGION_SIZE + 5):
        for z0 in range(REGION_SIZE):
            x1 = x0 + 5
            if 0 <= x1 < REGION_SIZE:
                flo_id = tiles[x1][z0].underlay_id
                if flo_id > 0 and flo_id <= len(flos):
                    flo = flos[flo_id - 1]
                    blend_chroma[z0] += flo.chroma
                    blend_saturation[z0] += flo.saturation
                    blend_lightness[z0] += flo.lightness
                    blend_luminance[z0] += flo.luminance
                    blend_magnitude[z0] += 1
            x2 = x0 - 5
            if 0 <= x2 < REGION_SIZE:
                flo_id = tiles[x2][z0].underlay_id
                if flo_id > 0 and flo_id <= len(flos):
                    flo = flos[flo_id - 1]
                    blend_chroma[z0] -= flo.chroma
                    blend_saturation[z0] -= flo.saturation
                    blend_lightness[z0] -= flo.lightness
                    blend_luminance[z0] -= flo.luminance
                    blend_magnitude[z0] -= 1

        if x0 < 1 or x0 >= REGION_SIZE - 1:
            continue

        hue_acc = sat_acc = light_acc = lum_acc = mag_acc = 0
        for z0 in range(-5, REGION_SIZE + 5):
            dz1 = z0 + 5
            if 0 <= dz1 < REGION_SIZE:
                hue_acc += blend_chroma[dz1]
                sat_acc += blend_saturation[dz1]
                light_acc += blend_lightness[dz1]
                lum_acc += blend_luminance[dz1]
                mag_acc += blend_magnitude[dz1]
            dz2 = z0 - 5
            if 0 <= dz2 < REGION_SIZE:
                hue_acc -= blend_chroma[dz2]
                sat_acc -= blend_saturation[dz2]
                light_acc -= blend_lightness[dz2]
                lum_acc -= blend_luminance[dz2]
                mag_acc -= blend_magnitude[dz2]

            if z0 < 1 or z0 >= REGION_SIZE - 1:
                continue

            tile = tiles[x0][z0]
            underlay_id = tile.underlay_id
            overlay_id = tile.overlay_id
            if underlay_id <= 0 and overlay_id <= 0:
                continue

            base_color = -1
            if underlay_id > 0 and lum_acc > 0 and mag_acc > 0:
                hue = (hue_acc * 256) // lum_acc
                saturation = sat_acc // mag_acc
                lightness = light_acc // mag_acc
                base_color = decimate_hsl(hue, saturation, lightness)

            paints[x0][z0] = _make_tile_paint(
                x0, z0, tile, base_color, flos, lightmap, palette, textures
            )

    # Border tiles sit outside the blend kernel — fill with direct flo colours.
    for x0 in range(REGION_SIZE):
        for z0 in range(REGION_SIZE):
            if paints[x0][z0] is not None:
                continue
            tile = tiles[x0][z0]
            if tile.underlay_id <= 0 and tile.overlay_id <= 0:
                continue
            base_color = _direct_base_color(tile, flos)
            paints[x0][z0] = _make_tile_paint(
                x0, z0, tile, base_color, flos, lightmap, palette, textures
            )

    return paints


def build_region_base_colors(
    region: RegionMap,
    flos: list[FloType],
    *,
    plane: int = 0,
) -> list[list[int]]:
    """Per-tile blended underlay HSL (SceneBuilder baseColor), or -1."""
    tiles = region.plane(plane)
    base: list[list[int]] = [[-1] * REGION_SIZE for _ in range(REGION_SIZE)]

    blend_chroma = [0] * REGION_SIZE
    blend_saturation = [0] * REGION_SIZE
    blend_lightness = [0] * REGION_SIZE
    blend_luminance = [0] * REGION_SIZE
    blend_magnitude = [0] * REGION_SIZE

    for x0 in range(-5, REGION_SIZE + 5):
        for z0 in range(REGION_SIZE):
            x1 = x0 + 5
            if 0 <= x1 < REGION_SIZE:
                flo_id = tiles[x1][z0].underlay_id
                if flo_id > 0 and flo_id <= len(flos):
                    flo = flos[flo_id - 1]
                    blend_chroma[z0] += flo.chroma
                    blend_saturation[z0] += flo.saturation
                    blend_lightness[z0] += flo.lightness
                    blend_luminance[z0] += flo.luminance
                    blend_magnitude[z0] += 1
            x2 = x0 - 5
            if 0 <= x2 < REGION_SIZE:
                flo_id = tiles[x2][z0].underlay_id
                if flo_id > 0 and flo_id <= len(flos):
                    flo = flos[flo_id - 1]
                    blend_chroma[z0] -= flo.chroma
                    blend_saturation[z0] -= flo.saturation
                    blend_lightness[z0] -= flo.lightness
                    blend_luminance[z0] -= flo.luminance
                    blend_magnitude[z0] -= 1

        if x0 < 1 or x0 >= REGION_SIZE - 1:
            continue

        hue_acc = sat_acc = light_acc = lum_acc = mag_acc = 0
        for z0 in range(-5, REGION_SIZE + 5):
            dz1 = z0 + 5
            if 0 <= dz1 < REGION_SIZE:
                hue_acc += blend_chroma[dz1]
                sat_acc += blend_saturation[dz1]
                light_acc += blend_lightness[dz1]
                lum_acc += blend_luminance[dz1]
                mag_acc += blend_magnitude[dz1]
            dz2 = z0 - 5
            if 0 <= dz2 < REGION_SIZE:
                hue_acc -= blend_chroma[dz2]
                sat_acc -= blend_saturation[dz2]
                light_acc -= blend_lightness[dz2]
                lum_acc -= blend_luminance[dz2]
                mag_acc -= blend_magnitude[dz2]

            if z0 < 1 or z0 >= REGION_SIZE - 1:
                continue

            if lum_acc <= 0 or mag_acc <= 0:
                continue
            if tiles[x0][z0].underlay_id <= 0:
                continue

            hue = (hue_acc * 256) // lum_acc
            saturation = sat_acc // mag_acc
            lightness = light_acc // mag_acc
            base[x0][z0] = decimate_hsl(hue, saturation, lightness)

    return base


def _average_rgba(samples: list[tuple[int, int, int, int]]) -> tuple[int, int, int, int]:
    vis = [c for c in samples if c and len(c) >= 4 and c[3] > 0]
    if not vis:
        return _DEFAULT_UNDERLAY
    if len(vis) == 1:
        return vis[0]
    r = sum(c[0] for c in vis) // len(vis)
    g = sum(c[1] for c in vis) // len(vis)
    b = sum(c[2] for c in vis) // len(vis)
    a = sum(c[3] for c in vis) // len(vis)
    return (r, g, b, a)


def _underlay_corner(paint: TilePaint | None, corner: str) -> tuple[int, int, int, int] | None:
    if paint is None:
        return None
    return getattr(paint, f"under_{corner}", None)


def build_region_corner_underlay_colors(
    region: RegionMap,
    flos: list[FloType],
    *,
    plane: int = 0,
    textures: dict[int, object] | None = None,
) -> tuple[list[list[int]], list[list[tuple[int, int, int, int] | None]]]:
    """Welded heightmap vertex grid: heights + underlay RGBA per corner."""
    heights = _height_grid(region, plane)
    paints = build_region_tile_paints(region, flos, plane=plane, textures=textures)

    corner: list[list[tuple[int, int, int, int] | None]] = [
        [None] * (REGION_SIZE + 1) for _ in range(REGION_SIZE + 1)
    ]
    for gx in range(REGION_SIZE + 1):
        for gz in range(REGION_SIZE + 1):
            samples: list[tuple[int, int, int, int]] = []
            if gx < REGION_SIZE and gz < REGION_SIZE:
                c = _underlay_corner(paints[gx][gz], "sw")
                if c:
                    samples.append(c)
            if gx > 0 and gz < REGION_SIZE:
                c = _underlay_corner(paints[gx - 1][gz], "se")
                if c:
                    samples.append(c)
            if gx > 0 and gz > 0:
                c = _underlay_corner(paints[gx - 1][gz - 1], "ne")
                if c:
                    samples.append(c)
            if gx < REGION_SIZE and gz > 0:
                c = _underlay_corner(paints[gx][gz - 1], "nw")
                if c:
                    samples.append(c)
            if samples:
                corner[gx][gz] = _average_rgba(samples)

    _fill_missing_corner_colors(corner, paints, region.plane(plane))

    return heights, corner


def _grid_point_has_underlay(gx: int, gz: int, tiles) -> bool:
    for tx, tz in ((gx, gz), (gx - 1, gz), (gx - 1, gz - 1), (gx, gz - 1)):
        if 0 <= tx < REGION_SIZE and 0 <= tz < REGION_SIZE:
            if tiles[tx][tz].underlay_id > 0:
                return True
    return False


def _fill_missing_corner_colors(
    corner: list[list[tuple[int, int, int, int] | None]],
    paints: list[list[TilePaint | None]],
    tiles,
) -> None:
    """Propagate underlay colours so welded terrain never leaves grid holes."""
    _DEFAULT_UNDERLAY = (40, 56, 28, 255)
    for _ in range(REGION_SIZE + 1):
        changed = False
        for gx in range(REGION_SIZE + 1):
            for gz in range(REGION_SIZE + 1):
                if corner[gx][gz] is not None:
                    continue
                samples: list[tuple[int, int, int, int]] = []
                for dx, dz in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    nx, nz = gx + dx, gz + dz
                    if 0 <= nx <= REGION_SIZE and 0 <= nz <= REGION_SIZE:
                        c = corner[nx][nz]
                        if c and c[3] > 0:
                            samples.append(c)
                if samples:
                    corner[gx][gz] = _average_rgba(samples)
                    changed = True
        if not changed:
            break
    for gx in range(REGION_SIZE + 1):
        for gz in range(REGION_SIZE + 1):
            if corner[gx][gz] is not None:
                continue
            if _grid_point_has_underlay(gx, gz, tiles):
                corner[gx][gz] = _DEFAULT_UNDERLAY
