"""Partial tile overlay meshes (ports SceneTileOverlay.java shape tables)."""

from __future__ import annotations

from dataclasses import dataclass

from src.rs2.map_decoder import TileData

# shape index = overlay_path (0..12); Scene uses overlay_path + 1 as shape id.
SHAPE_POINTS = [
    [1, 3, 5, 7],
    [1, 3, 5, 7],
    [1, 3, 5, 7],
    [1, 3, 5, 7, 6],
    [1, 3, 5, 7, 6],
    [1, 3, 5, 7, 6],
    [1, 3, 5, 7, 6],
    [1, 3, 5, 7, 2, 6],
    [1, 3, 5, 7, 2, 8],
    [1, 3, 5, 7, 2, 8],
    [1, 3, 5, 7, 11, 12],
    [1, 3, 5, 7, 11, 12],
    [1, 3, 5, 7, 13, 14],
]

SHAPE_PATHS = [
    [0, 1, 2, 3, 0, 0, 1, 3],
    [1, 1, 2, 3, 1, 0, 1, 3],
    [0, 1, 2, 3, 1, 0, 1, 3],
    [0, 0, 1, 2, 0, 0, 2, 4, 1, 0, 4, 3],
    [0, 0, 1, 4, 0, 0, 4, 3, 1, 1, 2, 4],
    [0, 0, 4, 3, 1, 0, 1, 2, 1, 0, 2, 4],
    [0, 1, 2, 4, 1, 0, 1, 4, 1, 0, 4, 3],
    [0, 4, 1, 2, 0, 4, 2, 5, 1, 0, 4, 5, 1, 0, 5, 3],
    [0, 4, 1, 2, 0, 4, 2, 3, 0, 4, 3, 5, 1, 0, 4, 5],
    [0, 0, 4, 5, 1, 4, 1, 2, 1, 4, 2, 3, 1, 4, 3, 5],
    [0, 0, 1, 5, 0, 1, 4, 5, 0, 1, 2, 4, 1, 0, 5, 3, 1, 5, 4, 3, 1, 4, 2, 3],
    [1, 0, 1, 5, 1, 1, 4, 5, 1, 1, 2, 4, 0, 0, 5, 3, 0, 5, 4, 3, 0, 4, 2, 3],
    [1, 0, 5, 4, 1, 0, 1, 5, 0, 0, 4, 3, 0, 4, 5, 3, 0, 5, 2, 3, 0, 1, 2, 5],
]

_TILE = 128
_HALF = _TILE // 2
_QUARTER = _TILE // 4
_THREE_QUARTER = (_TILE * 3) // 4


@dataclass
class OverlayTriangle:
    v0: tuple[float, float, float]
    v1: tuple[float, float, float]
    v2: tuple[float, float, float]
    c0: tuple[int, int, int, int]
    c1: tuple[int, int, int, int]
    c2: tuple[int, int, int, int]
    textured: bool
    u0: tuple[float, float] = (0.0, 0.0)
    u1: tuple[float, float] = (0.0, 0.0)
    u2: tuple[float, float] = (0.0, 0.0)
    is_underlay: bool = False


def _corner_heights(corners: list[list[int]], x: int, z: int) -> tuple[int, int, int, int]:
    return corners[x][z], corners[x + 1][z], corners[x + 1][z + 1], corners[x][z + 1]


def _resolve_point(
    point_type: int,
    rotation: int,
    *,
    scene_x: int,
    scene_z: int,
    h_sw: int,
    h_se: int,
    h_ne: int,
    h_nw: int,
    c1_sw: tuple,
    c1_se: tuple,
    c1_ne: tuple,
    c1_nw: tuple,
    c2_sw: tuple,
    c2_se: tuple,
    c2_ne: tuple,
    c2_nw: tuple,
) -> tuple[int, int, int, tuple, tuple]:
    t = point_type
    if (t & 1) == 0 and t <= 8:
        t = ((t - rotation - rotation - 1) & 7) + 1
    elif 8 < t <= 12:
        t = ((t - 9 - rotation) & 3) + 9
    elif 12 < t <= 16:
        t = ((t - 13 - rotation) & 3) + 13

    if t == 1:
        return scene_x, scene_z, h_sw, c1_sw, c2_sw
    if t == 2:
        return (
            scene_x + _HALF,
            scene_z,
            (h_sw + h_se) >> 1,
            _avg_rgba(c1_sw, c1_se),
            _avg_rgba(c2_sw, c2_se),
        )
    if t == 3:
        return scene_x + _TILE, scene_z, h_se, c1_se, c2_se
    if t == 4:
        return (
            scene_x + _TILE,
            scene_z + _HALF,
            (h_se + h_ne) >> 1,
            _avg_rgba(c1_se, c1_ne),
            _avg_rgba(c2_se, c2_ne),
        )
    if t == 5:
        return scene_x + _TILE, scene_z + _TILE, h_ne, c1_ne, c2_ne
    if t == 6:
        return (
            scene_x + _HALF,
            scene_z + _TILE,
            (h_ne + h_nw) >> 1,
            _avg_rgba(c1_ne, c1_nw),
            _avg_rgba(c2_ne, c2_nw),
        )
    if t == 7:
        return scene_x, scene_z + _TILE, h_nw, c1_nw, c2_nw
    if t == 8:
        return (
            scene_x,
            scene_z + _HALF,
            (h_nw + h_sw) >> 1,
            _avg_rgba(c1_nw, c1_sw),
            _avg_rgba(c2_nw, c2_sw),
        )
    if t == 9:
        return (
            scene_x + _HALF,
            scene_z + _QUARTER,
            (h_sw + h_se) >> 1,
            _avg_rgba(c1_sw, c1_se),
            _avg_rgba(c2_sw, c2_se),
        )
    if t == 10:
        return (
            scene_x + _THREE_QUARTER,
            scene_z + _HALF,
            (h_se + h_ne) >> 1,
            _avg_rgba(c1_se, c1_ne),
            _avg_rgba(c2_se, c2_ne),
        )
    if t == 11:
        return (
            scene_x + _HALF,
            scene_z + _THREE_QUARTER,
            (h_ne + h_nw) >> 1,
            _avg_rgba(c1_ne, c1_nw),
            _avg_rgba(c2_ne, c2_nw),
        )
    if t == 12:
        return (
            scene_x + _QUARTER,
            scene_z + _HALF,
            (h_nw + h_sw) >> 1,
            _avg_rgba(c1_nw, c1_sw),
            _avg_rgba(c2_nw, c2_sw),
        )
    if t == 13:
        return scene_x + _QUARTER, scene_z + _QUARTER, h_sw, c1_sw, c2_sw
    if t == 14:
        return scene_x + _THREE_QUARTER, scene_z + _QUARTER, h_se, c1_se, c2_se
    if t == 15:
        return scene_x + _THREE_QUARTER, scene_z + _THREE_QUARTER, h_ne, c1_ne, c2_ne
    return scene_x + _QUARTER, scene_z + _THREE_QUARTER, h_nw, c1_nw, c2_nw


_DEFAULT_UNDERLAY_RGBA = (40, 56, 28, 255)


def _avg_rgba(a: tuple, b: tuple) -> tuple:
    if not a or len(a) < 4 or a[3] <= 0:
        return b if b and len(b) >= 4 and b[3] > 0 else _DEFAULT_UNDERLAY_RGBA
    if not b or len(b) < 4 or b[3] <= 0:
        return a
    return (
        (a[0] + b[0]) >> 1,
        (a[1] + b[1]) >> 1,
        (a[2] + b[2]) >> 1,
        (a[3] + b[3]) >> 1,
    )


def _tile_uv(x: int, z: int, px: int, pz: int, *, mirror_x: bool = True) -> tuple[float, float]:
    u = (px - x * _TILE) / _TILE
    if mirror_x:
        u = 1.0 - u
    return (u, (pz - z * _TILE) / _TILE)


def build_partial_overlay_triangles(
    x: int,
    z: int,
    tile: TileData,
    *,
    corners: list[list[int]],
    c1_sw: tuple,
    c1_se: tuple,
    c1_ne: tuple,
    c1_nw: tuple,
    c2_sw: tuple,
    c2_se: tuple,
    c2_ne: tuple,
    c2_nw: tuple,
    texture_id: int,
    height_to_scene_y,
    rotation_override: int | None = None,
) -> list[OverlayTriangle]:
    """Build overlay triangles for overlay_path >= 1 (Java shape >= 2)."""
    shape_idx = tile.overlay_path + 1
    if shape_idx < 2 or shape_idx >= len(SHAPE_POINTS):
        return []
    rotation = rotation_override if rotation_override is not None else tile.overlay_rotation
    scene_x = x * _TILE
    scene_z = z * _TILE
    h_sw, h_se, h_ne, h_nw = _corner_heights(corners, x, z)

    points = SHAPE_POINTS[shape_idx]
    paths = SHAPE_PATHS[shape_idx]
    verts: list[tuple[float, float, float, tuple, tuple, int, int]] = []

    for pt in points:
        px, pz, py, col1, col2 = _resolve_point(
            pt,
            rotation,
            scene_x=scene_x,
            scene_z=scene_z,
            h_sw=h_sw,
            h_se=h_se,
            h_ne=h_ne,
            h_nw=h_nw,
            c1_sw=c1_sw,
            c1_se=c1_se,
            c1_ne=c1_ne,
            c1_nw=c1_nw,
            c2_sw=c2_sw,
            c2_se=c2_se,
            c2_ne=c2_ne,
            c2_nw=c2_nw,
        )
        verts.append(
            (
                px,
                height_to_scene_y(py),
                pz,
                col1,
                col2,
                px,
                pz,
            )
        )

    out: list[OverlayTriangle] = []
    idx = 0
    while idx + 3 < len(paths):
        color_flag = paths[idx]
        a = paths[idx + 1]
        b = paths[idx + 2]
        c = paths[idx + 3]
        idx += 4

        if a < 4:
            a = (a - rotation) & 3
        if b < 4:
            b = (b - rotation) & 3
        if c < 4:
            c = (c - rotation) & 3

        if color_flag == 0:
            va = verts[a]
            vb = verts[b]
            vc = verts[c]
            c0 = va[3]
            c1 = vb[3]
            c2 = vc[3]
            out.append(
                OverlayTriangle(
                    v0=(va[0], va[1], va[2]),
                    v1=(vb[0], vb[1], vb[2]),
                    v2=(vc[0], vc[1], vc[2]),
                    c0=c0,
                    c1=c1,
                    c2=c2,
                    textured=False,
                    is_underlay=True,
                )
            )
            continue

        va = verts[a]
        vb = verts[b]
        vc = verts[c]
        textured = color_flag != 0 and texture_id >= 0
        if textured:
            c0 = c1 = c2 = (255, 255, 255, 255)
            u0 = _tile_uv(x, z, va[5], va[6])
            u1 = _tile_uv(x, z, vb[5], vb[6])
            u2 = _tile_uv(x, z, vc[5], vc[6])
        else:
            c0 = va[4] if color_flag else va[3]
            c1 = vb[4] if color_flag else vb[3]
            c2 = vc[4] if color_flag else vc[3]
            u0 = u1 = u2 = (0.0, 0.0)

        out.append(
            OverlayTriangle(
                v0=(va[0], va[1], va[2]),
                v1=(vb[0], vb[1], vb[2]),
                v2=(vc[0], vc[1], vc[2]),
                c0=c0,
                c1=c1,
                c2=c2,
                textured=textured,
                u0=u0,
                u1=u1,
                u2=u2,
            )
        )
    return out
