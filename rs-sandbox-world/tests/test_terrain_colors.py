"""Terrain underlay corner blending."""

from src.rs2.map_decoder import REGION_SIZE, RegionMap, TileData
from src.rs2.terrain_colors import (
    TilePaint,
    _average_rgba,
    build_region_corner_underlay_colors,
    build_region_tile_paints,
)
from src.rs2.flo_decoder import FloType, decimate_hsl


def _flo(hue: int, sat: int, light: int, *, chroma: int = 1000, lum: int = 100) -> FloType:
    return FloType(
        id=1,
        hue=hue,
        saturation=sat,
        lightness=light,
        chroma=chroma,
        luminance=lum,
        hsl=decimate_hsl(hue, sat, light),
    )


def _flat_region(underlay_id: int = 1) -> RegionMap:
    tiles = [
        [[TileData(underlay_id=underlay_id, height=0) for _ in range(REGION_SIZE)] for _ in range(REGION_SIZE)]
        for _ in range(4)
    ]
    return RegionMap(region_x=0, region_y=0, tiles=tiles)


def test_underlay_corners_tracked_separately_from_overlay():
    flos = [_flo(40, 128, 128), _flo(200, 128, 128)]
    region = _flat_region(underlay_id=1)
    region.tiles[0][10][10].overlay_id = 2
    region.tiles[0][10][10].overlay_path = 0

    paints = build_region_tile_paints(region, flos, plane=0)
    paint = paints[10][10]
    assert paint is not None
    assert paint.overlay_shape == 1
    assert paint.sw != paint.under_sw
    assert paint.under_sw is not None


def test_welded_corners_average_adjacent_underlay():
    flos = [_flo(40, 128, 128), _flo(200, 128, 128)]
    region = _flat_region(underlay_id=1)
    region.tiles[0][10][10].overlay_id = 2
    region.tiles[0][10][10].overlay_path = 0
    region.tiles[0][11][10].underlay_id = 1

    paints = build_region_tile_paints(region, flos, plane=0)
    _, corners = build_region_corner_underlay_colors(region, flos, plane=0)

    shared = corners[11][10]
    assert shared is not None
    grass_only = paints[11][10].under_se
    assert grass_only is not None
    assert shared == grass_only


def test_average_rgba_skips_transparent():
    assert _average_rgba([(10, 20, 30, 255), (0, 0, 0, 0)]) == (10, 20, 30, 255)
