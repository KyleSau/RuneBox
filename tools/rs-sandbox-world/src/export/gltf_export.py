"""Build GLB files from assembled triangle soup.

Every primitive is emitted with POSITION, flat per-face NORMAL, TEXCOORD_0 and
COLOR_0 plus a material, because Unreal's Interchange glTF importer builds empty
static meshes from primitives missing normals/UVs. Non-textured faces become one
vertex-coloured primitive; each distinct texture id becomes its own UV-mapped
primitive. All primitives live in a single mesh so Unreal imports one multi-slot
static mesh.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import numpy as np

from src.export.glb_writer import GLBBuilder
from src.export.mesh_assembly import Triangle


def _smooth_normal_map(triangles: list[Triangle]) -> dict:
    """Accumulate (area-weighted) face normals per vertex position. The raw,
    un-normalised sum is returned so callers can detect degenerate vertices
    (e.g. RS' duplicated two-sided faces whose opposite normals cancel out)."""
    acc: dict[tuple, np.ndarray] = {}
    for tri in triangles:
        p0 = np.asarray(tri.v0, dtype="f8")
        p1 = np.asarray(tri.v1, dtype="f8")
        p2 = np.asarray(tri.v2, dtype="f8")
        face_normal = np.cross(p1 - p0, p2 - p0)  # length encodes 2*area weighting
        for vertex in (tri.v0, tri.v1, tri.v2):
            key = (round(vertex[0], 3), round(vertex[1], 3), round(vertex[2], 3))
            acc[key] = acc.get(key, np.zeros(3)) + face_normal
    return acc


def _vertex_key(vertex) -> tuple:
    return (round(vertex[0], 3), round(vertex[1], 3), round(vertex[2], 3))


def _smoothed_vertex_normal(smooth_map: dict, vertex, flat: np.ndarray) -> np.ndarray:
    """Smoothed normal for a vertex, falling back to this face's flat normal when
    the averaged normal is degenerate or sits in the opposite hemisphere. This
    keeps curved surfaces gouraud-smooth while preventing duplicated back-faces
    and sharp creases from getting nonsensical (cancelled/flipped) normals."""
    acc = smooth_map.get(_vertex_key(vertex))
    if acc is None:
        return flat
    length = float(np.linalg.norm(acc))
    if length <= 1e-6:
        return flat
    smooth = acc / length
    if float(np.dot(smooth, flat)) <= 0.0:
        return flat
    return smooth


def _group_arrays(triangles: list[Triangle], textured: bool, smooth_map: dict | None = None):
    count = len(triangles)
    positions = np.zeros((count * 3, 3), dtype="f4")
    normals = np.zeros((count * 3, 3), dtype="f4")
    uvs = np.zeros((count * 3, 2), dtype="f4")
    colors = np.zeros((count * 3, 4), dtype="u1")

    for i, tri in enumerate(triangles):
        p0 = np.asarray(tri.v0, dtype="f8")
        p1 = np.asarray(tri.v1, dtype="f8")
        p2 = np.asarray(tri.v2, dtype="f8")
        positions[i * 3] = p0
        positions[i * 3 + 1] = p1
        positions[i * 3 + 2] = p2

        normal = np.cross(p1 - p0, p2 - p0)
        length = np.linalg.norm(normal)
        flat = normal / length if length > 1e-12 else np.array([0.0, 1.0, 0.0])

        if smooth_map is not None:
            normals[i * 3] = _smoothed_vertex_normal(smooth_map, tri.v0, flat)
            normals[i * 3 + 1] = _smoothed_vertex_normal(smooth_map, tri.v1, flat)
            normals[i * 3 + 2] = _smoothed_vertex_normal(smooth_map, tri.v2, flat)
        else:
            normals[i * 3] = flat
            normals[i * 3 + 1] = flat
            normals[i * 3 + 2] = flat

        if textured:
            uvs[i * 3] = tri.uv0 or (0.0, 0.0)
            uvs[i * 3 + 1] = tri.uv1 or (0.0, 0.0)
            uvs[i * 3 + 2] = tri.uv2 or (0.0, 0.0)
            # Vertex alpha scales the texture (RS faceAlpha on textured faces).
            colors[i * 3] = tri.rgba
            colors[i * 3 + 1] = tri.rgba
            colors[i * 3 + 2] = tri.rgba
        else:
            colors[i * 3] = tri.rgba
            colors[i * 3 + 1] = tri.rgba
            colors[i * 3 + 2] = tri.rgba

    return positions, normals, uvs, colors


_FRAME_SECONDS_PER_UNIT = 0.020  # RS animation duration unit ~= one 20ms client cycle


def _group_morphs(
    group: list[Triangle], frame_deltas: list[np.ndarray] | None
) -> list[np.ndarray] | None:
    """Per-frame position-delta arrays for a primitive group, laid out to match
    its unwelded (3-per-triangle) POSITION order. Returns None when animation is
    unavailable or any triangle lacks a source vertex index."""
    if not frame_deltas:
        return None
    count = len(group)
    src = np.empty(count * 3, dtype=np.int64)
    for i, tri in enumerate(group):
        if tri.i0 < 0 or tri.i1 < 0 or tri.i2 < 0:
            return None
        src[i * 3] = tri.i0
        src[i * 3 + 1] = tri.i1
        src[i * 3 + 2] = tri.i2
    return [delta[src] for delta in frame_deltas]


def _group_color_morphs(
    group: list[Triangle], frame_color_deltas: list[np.ndarray] | None
) -> list[np.ndarray] | None:
    """Per-frame COLOR_0 deltas (unwelded layout) from per-vertex color offsets."""
    if not frame_color_deltas:
        return None
    count = len(group)
    src = np.empty(count * 3, dtype=np.int64)
    for i, tri in enumerate(group):
        if tri.i0 < 0 or tri.i1 < 0 or tri.i2 < 0:
            return None
        src[i * 3] = tri.i0
        src[i * 3 + 1] = tri.i1
        src[i * 3 + 2] = tri.i2
    out: list[np.ndarray] = []
    for delta in frame_color_deltas:
        flat = np.zeros((count * 3, 4), dtype="f4")
        for i, tri in enumerate(group):
            flat[i * 3] = delta[tri.i0]
            flat[i * 3 + 1] = delta[tri.i1]
            flat[i * 3 + 2] = delta[tri.i2]
        out.append(flat)
    return out


def _merge_morph_targets(
    pos: list[np.ndarray] | None, col: list[np.ndarray] | None
) -> list[tuple[np.ndarray | None, np.ndarray | None]] | None:
    if not pos and not col:
        return None
    n = max(len(pos) if pos else 0, len(col) if col else 0)
    merged: list[tuple[np.ndarray | None, np.ndarray | None]] = []
    for i in range(n):
        p = pos[i] if pos and i < len(pos) else None
        c = col[i] if col and i < len(col) else None
        merged.append((p, c))
    return merged


def _build_keyframes(
    durations: list[int], *, frame_gap: int = 0, loop: bool = True
):
    """Keyframe times for morph weight animation.

    ``frame_gap`` is extra RS cycles between frames (1 for ``SpotAnimEntity`` /
    projectiles; 0 for NPC primary/secondary sequences).
    """
    times: list[float] = []
    targets: list[int] = []
    acc = 0.0
    for f, dur in enumerate(durations):
        times.append(acc)
        targets.append(f)
        # SpotAnimEntity / projectile: each frame lasts getFrameDuration + 1 cycles.
        acc += (dur + frame_gap) * _FRAME_SECONDS_PER_UNIT
    if loop:
        times.append(acc)
        targets.append(0)
    elif durations:
        times.append(acc)
        targets.append(len(durations) - 1)
    return times, targets


def _is_transparent(tri: Triangle) -> bool:
    """RS faceAlpha 0 = opaque; higher values fade toward the framebuffer (see Draw3D)."""
    return tri.rgba[3] < 255


def _dedupe_triangles(triangles: list[Triangle]) -> list[Triangle]:
    """Drop exact-duplicate, same-winding faces. RS models (and merged component
    models) sometimes contain identical coincident faces that z-fight/flicker in
    a depth-buffered renderer. Opposite-wound coincident pairs (genuine two-sided
    surfaces like wing membranes) have a different ordered key and are kept; they
    are resolved by back-face culling instead."""
    seen: set[tuple] = set()
    out: list[Triangle] = []
    for tri in triangles:
        key = (
            (round(tri.v0[0], 2), round(tri.v0[1], 2), round(tri.v0[2], 2)),
            (round(tri.v1[0], 2), round(tri.v1[1], 2), round(tri.v1[2], 2)),
            (round(tri.v2[0], 2), round(tri.v2[1], 2), round(tri.v2[2], 2)),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(tri)
    return out


def build_glb_bytes(
    triangles: list[Triangle],
    textures: dict[int, object] | None = None,
    smooth: bool = True,
    frame_deltas: list[np.ndarray] | None = None,
    frame_color_deltas: list[np.ndarray] | None = None,
    frame_durations: list[int] | None = None,
    *,
    frame_gap: int = 0,
    loop: bool = True,
    morph_interpolation: str = "LINEAR",
    anim_name: str = "idle",
) -> bytes | None:
    if not triangles:
        return None
    triangles = _dedupe_triangles(triangles)
    textures = textures or {}
    builder = GLBBuilder()

    # Smooth normals are averaged across ALL faces by position so shading is
    # gouraud-smooth even across the colour/texture primitive split.
    smooth_map = _smooth_normal_map(triangles) if smooth else None

    # Plain (vertex-colour) faces: one primitive per RS draw priority (opaque) or
    # per (priority, alpha) for translucent faces. Material names encode priority
    # (``M_rs_color_p<N>``) and optional alpha (``_a<A>``) so the viewer can set
    # polygonOffset / transparency like the 317 client's faceAlpha + priority pass.
    by_priority: dict[int, list[Triangle]] = defaultdict(list)
    by_trans: dict[tuple[int, int], list[Triangle]] = defaultdict(list)
    for tri in triangles:
        if tri.texture_id is not None:
            continue
        if _is_transparent(tri):
            by_trans[(tri.priority, tri.rgba[3])].append(tri)
        else:
            by_priority[tri.priority].append(tri)

    for priority in sorted(by_priority):
        group = by_priority[priority]
        positions, normals, uvs, colors = _group_arrays(group, textured=False, smooth_map=smooth_map)
        material = builder.add_color_material(f"M_rs_color_p{priority}")
        builder.add_primitive(
            positions,
            normals,
            uvs,
            colors,
            material,
            _merge_morph_targets(
                _group_morphs(group, frame_deltas),
                _group_color_morphs(group, frame_color_deltas),
            ),
        )

    for (priority, alpha) in sorted(by_trans):
        group = by_trans[(priority, alpha)]
        positions, normals, uvs, colors = _group_arrays(group, textured=False, smooth_map=smooth_map)
        material = builder.add_color_material(f"M_rs_color_p{priority}_a{alpha}", blend=True)
        builder.add_primitive(
            positions,
            normals,
            uvs,
            colors,
            material,
            _merge_morph_targets(
                _group_morphs(group, frame_deltas),
                _group_color_morphs(group, frame_color_deltas),
            ),
        )

    by_texture: dict[tuple[int, int, int], list[Triangle]] = defaultdict(list)
    by_texture_trans: dict[tuple[int, int, int], list[Triangle]] = defaultdict(list)
    for tri in triangles:
        if tri.texture_id is None:
            continue
        key = (tri.texture_id, tri.priority, tri.rgba[3])
        if _is_transparent(tri):
            by_texture_trans[key].append(tri)
        else:
            by_texture[(tri.texture_id, tri.priority, 255)].append(tri)

    for (texture_id, priority, _alpha), group in by_texture.items():
        image = textures.get(texture_id)
        if image is None:
            continue
        positions, normals, uvs, colors = _group_arrays(group, textured=True, smooth_map=smooth_map)
        material = builder.add_texture_material(f"M_rs_tex_{texture_id}_p{priority}", image)
        builder.add_primitive(
            positions,
            normals,
            uvs,
            colors,
            material,
            _merge_morph_targets(
                _group_morphs(group, frame_deltas),
                _group_color_morphs(group, frame_color_deltas),
            ),
        )

    for (texture_id, priority, alpha), group in by_texture_trans.items():
        image = textures.get(texture_id)
        if image is None:
            continue
        positions, normals, uvs, colors = _group_arrays(group, textured=True, smooth_map=smooth_map)
        material = builder.add_texture_material(
            f"M_rs_tex_{texture_id}_p{priority}_a{alpha}", image, blend=True
        )
        builder.add_primitive(
            positions,
            normals,
            uvs,
            colors,
            material,
            _merge_morph_targets(
                _group_morphs(group, frame_deltas),
                _group_color_morphs(group, frame_color_deltas),
            ),
        )

    if not builder.primitives:
        return None

    has_anim = frame_durations and builder.morph_target_count > 0
    if has_anim and (frame_deltas or frame_color_deltas):
        times, targets = _build_keyframes(
            frame_durations, frame_gap=frame_gap, loop=loop
        )
        builder.set_morph_animation(
            times, targets, name=anim_name, interpolation=morph_interpolation
        )

    return builder.build()


def build_glb_bytes_multiclip(
    triangles: list[Triangle],
    textures: dict[int, object] | None = None,
    smooth: bool = True,
    *,
    clips: list[dict] | None = None,
) -> bytes | None:
    """Build a GLB whose mesh carries a single union of position morph targets
    shared by several named animation clips.

    Each clip dict has: ``frame_deltas`` (list of per-model-vertex (N,3) arrays),
    ``durations``, ``name``, and optional ``frame_gap`` / ``loop`` /
    ``interpolation``. Used for assembled players (``stand`` + ``walk``).
    """
    if not triangles:
        return None
    triangles = _dedupe_triangles(triangles)
    textures = textures or {}
    clips = clips or []

    # Concatenate every clip's frames into one union morph-target list; remember
    # each clip's [start, count) slice so its keyframes can index into the union.
    union_pos: list[np.ndarray] = []
    clip_ranges: list[tuple[int, int]] = []
    for clip in clips:
        start = len(union_pos)
        frames = clip.get("frame_deltas") or []
        union_pos.extend(frames)
        clip_ranges.append((start, len(frames)))

    builder = GLBBuilder()
    smooth_map = _smooth_normal_map(triangles) if smooth else None

    def _emit(group: list[Triangle], textured: bool, material: int) -> None:
        positions, normals, uvs, colors = _group_arrays(group, textured=textured, smooth_map=smooth_map)
        morphs = _merge_morph_targets(_group_morphs(group, union_pos or None), None)
        builder.add_primitive(positions, normals, uvs, colors, material, morphs)

    by_priority: dict[int, list[Triangle]] = defaultdict(list)
    by_trans: dict[tuple[int, int], list[Triangle]] = defaultdict(list)
    by_texture: dict[tuple[int, int, int], list[Triangle]] = defaultdict(list)
    by_texture_trans: dict[tuple[int, int, int], list[Triangle]] = defaultdict(list)
    for tri in triangles:
        if tri.texture_id is None:
            if _is_transparent(tri):
                by_trans[(tri.priority, tri.rgba[3])].append(tri)
            else:
                by_priority[tri.priority].append(tri)
        else:
            if _is_transparent(tri):
                by_texture_trans[(tri.texture_id, tri.priority, tri.rgba[3])].append(tri)
            else:
                by_texture[(tri.texture_id, tri.priority, 255)].append(tri)

    for priority in sorted(by_priority):
        _emit(by_priority[priority], False, builder.add_color_material(f"M_rs_color_p{priority}"))
    for (priority, alpha) in sorted(by_trans):
        _emit(by_trans[(priority, alpha)], False,
              builder.add_color_material(f"M_rs_color_p{priority}_a{alpha}", blend=True))
    for (texture_id, priority, _alpha), group in by_texture.items():
        image = textures.get(texture_id)
        if image is None:
            continue
        _emit(group, True, builder.add_texture_material(f"M_rs_tex_{texture_id}_p{priority}", image))
    for (texture_id, priority, alpha), group in by_texture_trans.items():
        image = textures.get(texture_id)
        if image is None:
            continue
        _emit(group, True,
              builder.add_texture_material(f"M_rs_tex_{texture_id}_p{priority}_a{alpha}", image, blend=True))

    if not builder.primitives:
        return None

    if builder.morph_target_count > 0:
        for clip, (start, count) in zip(clips, clip_ranges):
            if count <= 0:
                continue
            times, targets = _build_keyframes(
                clip["durations"],
                frame_gap=clip.get("frame_gap", 0),
                loop=clip.get("loop", True),
            )
            targets = [start + t for t in targets]
            builder.add_morph_animation(
                times, targets,
                name=clip.get("name", "clip"),
                interpolation=clip.get("interpolation", "LINEAR"),
            )

    return builder.build()


def export_glb(
    triangles: list[Triangle],
    path: Path,
    textures: dict[int, object] | None = None,
    smooth: bool = True,
    frame_deltas: list[np.ndarray] | None = None,
    frame_color_deltas: list[np.ndarray] | None = None,
    frame_durations: list[int] | None = None,
    *,
    frame_gap: int = 1,
    loop: bool = True,
    morph_interpolation: str = "LINEAR",
    anim_name: str = "idle",
) -> bool:
    """Write a GLB. Returns False when there is nothing to export."""
    data = build_glb_bytes(
        triangles,
        textures,
        smooth=smooth,
        frame_deltas=frame_deltas,
        frame_color_deltas=frame_color_deltas,
        frame_durations=frame_durations,
        frame_gap=frame_gap,
        loop=loop,
        morph_interpolation=morph_interpolation,
        anim_name=anim_name,
    )
    if data is None:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return True
