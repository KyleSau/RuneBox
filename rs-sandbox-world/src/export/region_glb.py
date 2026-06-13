"""Build terrain GLB from decoded region map data."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from src.export.glb_writer import GLBBuilder
from src.rs2.flo_decoder import load_flo_types
from src.rs2.map_decoder import REGION_SIZE, RegionMap
from src.rs2.terrain_colors import (
    TilePaint,
    build_region_corner_underlay_colors,
    build_region_tile_paints,
)
from src.rs2.palette import srgb_rgba_to_linear8
from src.rs2.tile_overlay import OverlayTriangle, build_partial_overlay_triangles

if TYPE_CHECKING:
    from src.cache.cache_locator import CacheReader

_TILE = 128
_HEIGHT_SCALE = 1.0 / 8.0
# Layer terrain passes to avoid coplanar z-fighting at shores and tile seams.
_PARTIAL_UNDERLAY_Y_BIAS = 0.0
_OVERLAY_Y_BIAS = 6.0


def _scene_x_grid(gx: int | float) -> float:
    """RS scene X within a region (317 tile grid, 128 units per tile)."""
    return float(gx) * _TILE


def _mirror_overlay_rotation(rotation: int) -> int:
    """Reflect overlay rotation when terrain X is mirrored to match rsToScene."""
    return (4 - (rotation & 3)) & 3


def height_to_scene_y(vertex_height: int) -> float:
    return (-vertex_height) * _HEIGHT_SCALE


def _on_region_edge(x: int, z: int) -> bool:
    return x == 0 or z == 0 or x == REGION_SIZE - 1 or z == REGION_SIZE - 1


def _opaque_rgba(rgba: tuple[int, int, int, int] | None, fallback: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    if rgba is None or len(rgba) < 4 or rgba[3] <= 0:
        return fallback
    return rgba


def _glb_vertex_color(rgba: tuple[int, int, int, int] | None, fallback: tuple[int, int, int, int]) -> list[int]:
    """RS palette RGB → linear COLOR_0 (matches model GLB export)."""
    return list(srgb_rgba_to_linear8(_opaque_rgba(rgba, fallback)))


def _append_oriented_tri(
    indices: list,
    positions: list,
    ia: int,
    ib: int,
    ic: int,
) -> None:
    """Emit a tri wound so the geometric normal favors +Y (visible from above)."""
    pa, pb, pc = positions[ia], positions[ib], positions[ic]
    ax, az = pb[0] - pa[0], pb[2] - pa[2]
    bx, bz = pc[0] - pa[0], pc[2] - pa[2]
    ny = ax * bz - az * bx
    if ny < 0:
        indices.extend([ia, ic, ib])
    else:
        indices.extend([ia, ib, ic])


def _append_welded_underlay(
    positions: list,
    normals: list,
    uvs: list,
    colors: list,
    indices: list,
    *,
    heights: list[list[int]],
    corner_colors: list[list[tuple | None]],
    paints: list[list[TilePaint | None]],
    tiles,
) -> None:
    """Welded underlay grid — one vertex per height corner (position weld)."""
    _FALLBACK = (40, 56, 28, 255)
    vtx_map: dict[tuple[int, int], int] = {}

    def vertex_index(gx: int, gz: int, hint: tuple[int, int, int, int] | None = None) -> int | None:
        rgba = _opaque_rgba(corner_colors[gx][gz], hint or _FALLBACK)
        key = (gx, gz)
        hit = vtx_map.get(key)
        if hit is not None:
            return hit
        positions.append([_scene_x_grid(gx), height_to_scene_y(heights[gx][gz]), gz * _TILE])
        normals.append([0.0, 1.0, 0.0])
        uvs.append([0.0, 0.0])
        colors.append(_glb_vertex_color(rgba, _FALLBACK))
        idx = len(positions) - 1
        vtx_map[key] = idx
        return idx

    for x in range(REGION_SIZE):
        for z in range(REGION_SIZE):
            paint = paints[x][z]
            tile = tiles[x][z]
            if paint is None or tile.underlay_id <= 0:
                continue
            hints = (
                paint.under_sw,
                paint.under_se,
                paint.under_ne,
                paint.under_nw,
            )
            i0 = vertex_index(x, z, hints[0])
            i1 = vertex_index(x + 1, z, hints[1])
            i2 = vertex_index(x + 1, z + 1, hints[2])
            i3 = vertex_index(x, z + 1, hints[3])
            if None in (i0, i1, i2, i3):
                continue
            _append_oriented_tri(indices, positions, i0, i1, i2)
            _append_oriented_tri(indices, positions, i0, i3, i2)


def _append_tile_quad(
    positions: list,
    normals: list,
    uvs: list,
    colors: list,
    indices: list,
    *,
    x: int,
    z: int,
    corners: list[list[int]],
    paint: TilePaint,
    textured: bool,
) -> None:
    base = len(positions)
    corner_coords = (
        (x, z, paint.sw),
        (x + 1, z, paint.se),
        (x + 1, z + 1, paint.ne),
        (x, z + 1, paint.nw),
    )
    y_bias = _OVERLAY_Y_BIAS if textured else 0.0
    _FALLBACK = (40, 56, 28, 255)
    for gx, gz, rgba in corner_coords:
        positions.append([_scene_x_grid(gx), height_to_scene_y(corners[gx][gz]) + y_bias, gz * _TILE])
        normals.append([0.0, 1.0, 0.0])
        if textured:
            # UV u flipped to match terrain X mirror applied in the viewer (scale.x = -1).
            local_u = 0.0 if gx > x else 1.0
            local_v = 1.0 if gz > z else 0.0
            uvs.append([local_u, local_v])
            colors.append(_glb_vertex_color((255, 255, 255, 255), _FALLBACK))
        else:
            uvs.append([0.0, 0.0])
            colors.append(_glb_vertex_color(rgba, _FALLBACK))
    _append_oriented_tri(indices, positions, base, base + 1, base + 2)
    _append_oriented_tri(indices, positions, base, base + 3, base + 2)


def _append_overlay_tri(
    tri: OverlayTriangle,
    positions: list,
    normals: list,
    uvs: list,
    colors: list,
    indices: list,
) -> None:
    base = len(positions)
    y_bias = 0.0
    if tri.is_underlay:
        y_bias = _PARTIAL_UNDERLAY_Y_BIAS
    elif tri.textured:
        y_bias = _OVERLAY_Y_BIAS
    _FALLBACK = (40, 56, 28, 255)
    for v, c, uv in ((tri.v0, tri.c0, tri.u0), (tri.v1, tri.c1, tri.u1), (tri.v2, tri.c2, tri.u2)):
        positions.append([v[0], v[1] + y_bias, v[2]])
        normals.append([0.0, 1.0, 0.0])
        uvs.append(list(uv))
        colors.append(_glb_vertex_color(c, _FALLBACK))
    _append_oriented_tri(indices, positions, base, base + 1, base + 2)


def build_region_terrain_glb(
    region: RegionMap,
    *,
    plane: int = 0,
    cache: "CacheReader | None" = None,
    textures: dict[int, object] | None = None,
) -> bytes | None:
    """Terrain mesh with welded underlay vertices (smooth tile boundaries)."""
    tiles = region.plane(plane)

    flos = load_flo_types(cache) if cache is not None else []
    if not flos:
        return None

    if textures is None and cache is not None:
        from src.export.texture_archive import load_texture_images

        textures = load_texture_images(cache)

    paints = build_region_tile_paints(region, flos, plane=plane, textures=textures)
    heights, corner_colors = build_region_corner_underlay_colors(
        region, flos, plane=plane, textures=textures
    )

    color_positions: list = []
    color_normals: list = []
    color_uvs: list = []
    color_cols: list = []
    color_indices: list = []

    tex_groups: dict[int, tuple[list, list, list, list, list]] = {}

    _append_welded_underlay(
        color_positions,
        color_normals,
        color_uvs,
        color_cols,
        color_indices,
        heights=heights,
        corner_colors=corner_colors,
        paints=paints,
        tiles=tiles,
    )

    for x in range(REGION_SIZE):
        for z in range(REGION_SIZE):
            paint = paints[x][z]
            if paint is None:
                continue
            tile = tiles[x][z]

            if paint.overlay_shape >= 2:
                if _on_region_edge(x, z):
                    # Partial taper shapes assume a neighbour region; on the map
                    # perimeter draw a full overlay tile instead of a broken taper.
                    if paint.texture_id >= 0 and textures and paint.texture_id in textures:
                        group = tex_groups.setdefault(
                            paint.texture_id,
                            ([], [], [], [], []),
                        )
                        _append_tile_quad(
                            *group,
                            x=x,
                            z=z,
                            corners=heights,
                            paint=paint,
                            textured=True,
                        )
                    else:
                        full_paint = TilePaint(
                            sw=paint.fg_sw or paint.sw,
                            se=paint.fg_se or paint.se,
                            ne=paint.fg_ne or paint.ne,
                            nw=paint.fg_nw or paint.nw,
                        )
                        _append_tile_quad(
                            color_positions,
                            color_normals,
                            color_uvs,
                            color_cols,
                            color_indices,
                            x=x,
                            z=z,
                            corners=heights,
                            paint=full_paint,
                            textured=False,
                        )
                    continue

                overlay_tris = build_partial_overlay_triangles(
                    x,
                    z,
                    tile,
                    corners=heights,
                    c1_sw=paint.sw,
                    c1_se=paint.se,
                    c1_ne=paint.ne,
                    c1_nw=paint.nw,
                    c2_sw=paint.fg_sw or paint.sw,
                    c2_se=paint.fg_se or paint.se,
                    c2_ne=paint.fg_ne or paint.ne,
                    c2_nw=paint.fg_nw or paint.nw,
                    texture_id=paint.texture_id,
                    height_to_scene_y=height_to_scene_y,
                    rotation_override=_mirror_overlay_rotation(tile.overlay_rotation),
                )
                for tri in overlay_tris:
                    if tri.textured and paint.texture_id >= 0:
                        group = tex_groups.setdefault(
                            paint.texture_id,
                            ([], [], [], [], []),
                        )
                        _append_overlay_tri(tri, *group)
                    else:
                        _append_overlay_tri(
                            tri,
                            color_positions,
                            color_normals,
                            color_uvs,
                            color_cols,
                            color_indices,
                        )
                continue

            if paint.texture_id >= 0 and textures and paint.texture_id in textures:
                group = tex_groups.setdefault(
                    paint.texture_id,
                    ([], [], [], [], []),
                )
                _append_tile_quad(
                    *group,
                    x=x,
                    z=z,
                    corners=heights,
                    paint=paint,
                    textured=True,
                )
            elif paint.overlay_shape == 1:
                _append_tile_quad(
                    color_positions,
                    color_normals,
                    color_uvs,
                    color_cols,
                    color_indices,
                    x=x,
                    z=z,
                    corners=heights,
                    paint=paint,
                    textured=False,
                )

    if not color_indices and not tex_groups:
        return None

    builder = GLBBuilder()

    if color_indices:
        mat = builder.add_color_material("terrain")
        builder.add_primitive(
            np.asarray(color_positions, dtype=np.float32),
            np.asarray(color_normals, dtype=np.float32),
            np.asarray(color_uvs, dtype=np.float32),
            np.asarray(color_cols, dtype=np.uint8),
            mat,
            indices=np.asarray(color_indices, dtype=np.uint32),
        )

    for texture_id, (pos, nrm, uv, col, idx) in sorted(tex_groups.items()):
        image = textures.get(texture_id) if textures else None
        if image is None or not idx:
            continue
        _add_smooth_normals(pos, nrm, idx)
        mat = builder.add_texture_material(f"terrain_tex_{texture_id}", image)
        builder.add_primitive(
            np.asarray(pos, dtype=np.float32),
            np.asarray(nrm, dtype=np.float32),
            np.asarray(uv, dtype=np.float32),
            np.asarray(col, dtype=np.uint8),
            mat,
            indices=np.asarray(idx, dtype=np.uint32),
        )

    return builder.build()


def _add_smooth_normals(positions: list, normals: list, indices: list) -> None:
    accum = np.zeros((len(positions), 3), dtype=np.float64)
    pos_arr = np.asarray(positions, dtype=np.float64)
    for t in range(0, len(indices), 3):
        ia, ib, ic = indices[t], indices[t + 1], indices[t + 2]
        pa, pb, pc = pos_arr[ia], pos_arr[ib], pos_arr[ic]
        n = np.cross(pb - pa, pc - pa)
        norm = np.linalg.norm(n)
        if norm > 1e-8:
            n /= norm
        else:
            n = np.array([0.0, 1.0, 0.0])
        accum[ia] += n
        accum[ib] += n
        accum[ic] += n
    for i in range(len(accum)):
        norm = np.linalg.norm(accum[i])
        if norm > 1e-8:
            normals[i] = (accum[i] / norm).tolist()
        else:
            normals[i] = [0.0, 1.0, 0.0]
