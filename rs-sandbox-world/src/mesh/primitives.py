"""Low-poly primitive mesh builders for RS-style weapon reconstruction."""

from __future__ import annotations

import numpy as np
import trimesh


def _rgba(rgb: tuple[int, int, int]) -> np.ndarray:
    return np.array([rgb[0], rgb[1], rgb[2], 255], dtype=np.uint8)


def box_prism(
    size_x: float,
    size_y: float,
    size_z: float,
    center: tuple[float, float, float] = (0.0, 0.0, 0.0),
    color: tuple[int, int, int] = (128, 128, 128),
) -> trimesh.Trimesh:
    """Axis-aligned box; length along +X."""
    mesh = trimesh.creation.box(extents=[size_x, size_y, size_z])
    mesh.apply_translation(center)
    mesh.visual.face_colors = np.tile(_rgba(color), (len(mesh.faces), 1))
    return mesh


def tapered_box_prism(
    length: float,
    width_start: float,
    width_end: float,
    height_start: float,
    height_end: float,
    x_start: float = 0.0,
    color: tuple[int, int, int] = (128, 128, 128),
) -> trimesh.Trimesh:
    """Tapered stock-like prism along X."""
    x_end = x_start + length
    xs = np.array([x_start, x_end, x_end, x_start, x_start, x_end, x_end, x_start], dtype=np.float64)
    ys = np.array(
        [
            -width_start / 2,
            -width_end / 2,
            width_end / 2,
            width_start / 2,
            -width_start / 2,
            -width_end / 2,
            width_end / 2,
            width_start / 2,
        ],
        dtype=np.float64,
    )
    zs = np.array(
        [
            -height_start / 2,
            -height_end / 2,
            -height_end / 2,
            -height_start / 2,
            height_start / 2,
            height_end / 2,
            height_end / 2,
            height_start / 2,
        ],
        dtype=np.float64,
    )
    verts = np.column_stack([xs, ys, zs])
    faces = np.array(
        [
            [0, 1, 2],
            [0, 2, 3],
            [4, 6, 5],
            [4, 7, 6],
            [0, 4, 5],
            [0, 5, 1],
            [2, 6, 7],
            [2, 7, 3],
            [0, 3, 7],
            [0, 7, 4],
            [1, 5, 6],
            [1, 6, 2],
        ],
        dtype=np.int64,
    )
    mesh = trimesh.Trimesh(vertices=verts, faces=faces, process=False)
    mesh.visual.face_colors = np.tile(_rgba(color), (len(mesh.faces), 1))
    return mesh


def octagonal_cylinder(
    length: float,
    radius: float,
    x_start: float = 0.0,
    segments: int = 8,
    color: tuple[int, int, int] = (128, 128, 128),
) -> trimesh.Trimesh:
    """Octagonal prism along X."""
    angles = np.linspace(0, 2 * np.pi, segments, endpoint=False)
    ring0 = np.column_stack([np.zeros(segments), radius * np.cos(angles), radius * np.sin(angles)])
    ring1 = ring0.copy()
    ring1[:, 0] = length
    verts = np.vstack([ring0, ring1])
    verts[:, 0] += x_start
    faces: list[list[int]] = []
    for i in range(segments):
        j = (i + 1) % segments
        a, b, c, d = i, j, i + segments, j + segments
        faces.extend([[a, b, c], [b, d, c]])
    # Caps
    center0 = len(verts)
    center1 = center0 + 1
    verts = np.vstack([verts, [[x_start, 0, 0], [x_start + length, 0, 0]]])
    for i in range(segments):
        j = (i + 1) % segments
        faces.append([center0, i, j])
        faces.append([center1, j + segments, i + segments])
    mesh = trimesh.Trimesh(vertices=verts, faces=np.array(faces), process=False)
    mesh.visual.face_colors = np.tile(_rgba(color), (len(mesh.faces), 1))
    return mesh


def ring_band(
    x_pos: float,
    outer_radius: float,
    inner_radius: float,
    thickness: float,
    segments: int = 8,
    color: tuple[int, int, int] = (128, 128, 128),
) -> trimesh.Trimesh:
    """Short barrel band ring at x position."""
    return octagonal_cylinder(thickness, outer_radius, x_start=x_pos - thickness / 2, segments=segments, color=color)


def faceted_blade_tip(
    length: float,
    width: float,
    thickness: float,
    x_start: float = 0.0,
    color: tuple[int, int, int] = (160, 160, 170),
) -> trimesh.Trimesh:
    """Four-sided pyramid tip along +X for a readable faceted sword point."""
    x_base = x_start
    x_tip = x_start + length
    hw = width / 2
    ht = thickness / 2
    verts = np.array(
        [
            [x_base, -hw, -ht],
            [x_base, hw, -ht],
            [x_base, hw, ht],
            [x_base, -hw, ht],
            [x_tip, 0.0, 0.0],
        ],
        dtype=np.float64,
    )
    faces = np.array(
        [
            [0, 1, 4],
            [1, 2, 4],
            [2, 3, 4],
            [3, 0, 4],
            [0, 2, 1],
            [0, 3, 2],
        ],
        dtype=np.int64,
    )
    mesh = trimesh.Trimesh(vertices=verts, faces=faces, process=False)
    mesh.visual.face_colors = np.tile(_rgba(color), (len(mesh.faces), 1))
    return mesh


def blade_center_ridge(
    length: float,
    width: float,
    height: float,
    x_start: float,
    z_offset: float = 0.0,
    color: tuple[int, int, int] = (100, 102, 108),
) -> trimesh.Trimesh:
    """Raised center ridge along the top of a blade (+Z)."""
    mesh = tapered_box_prism(
        length,
        width,
        width * 0.65,
        height,
        height * 0.55,
        x_start=x_start,
        color=color,
    )
    mesh.apply_translation([0.0, 0.0, z_offset + height * 0.4])
    return mesh


def pommel_faceted(
    size: float,
    center: tuple[float, float, float],
    color: tuple[int, int, int] = (100, 102, 108),
) -> trimesh.Trimesh:
    """Low-poly pommel: short octagonal nub + end cap."""
    cx, cy, cz = center
    core = octagonal_cylinder(size * 0.7, size * 0.42, x_start=cx - size * 0.35, color=color)
    cap = box_prism(size * 0.35, size * 0.11, size * 0.11, center=(cx - size * 0.52, cy, cz), color=color)
    return merge_meshes(core, cap)


def wedge_blade(
    length: float,
    width: float,
    thickness: float,
    x_start: float = 0.0,
    color: tuple[int, int, int] = (160, 160, 170),
) -> trimesh.Trimesh:
    """Simple tapered blade wedge along X."""
    x_tip = x_start + length
    x_base = x_start
    hw = width / 2
    ht = thickness / 2
    verts = np.array(
        [
            [x_base, -hw, -ht],
            [x_base, hw, -ht],
            [x_base, -hw, ht],
            [x_base, hw, ht],
            [x_tip, 0, -ht * 0.3],
            [x_tip, 0, ht * 0.3],
        ],
        dtype=np.float64,
    )
    faces = np.array(
        [
            [0, 1, 2],
            [1, 3, 2],
            [0, 4, 1],
            [2, 3, 5],
            [0, 2, 4],
            [1, 5, 3],
            [4, 5, 1],
            [4, 2, 5],
        ],
        dtype=np.int64,
    )
    mesh = trimesh.Trimesh(vertices=verts, faces=faces, process=False)
    mesh.visual.face_colors = np.tile(_rgba(color), (len(mesh.faces), 1))
    return mesh


def crossguard(
    span: float,
    depth: float,
    height: float,
    x_pos: float,
    color: tuple[int, int, int] = (150, 150, 160),
) -> trimesh.Trimesh:
    return box_prism(depth, span, height, center=(x_pos, 0, 0), color=color)


def trigger_guard(
    width: float,
    height: float,
    depth: float,
    center: tuple[float, float, float],
    color: tuple[int, int, int] = (90, 92, 98),
) -> trimesh.Trimesh:
    """Blocky U-shaped trigger guard from three boxes."""
    cx, cy, cz = center
    leg = box_prism(depth * 0.35, width * 0.18, height, center=(cx, cy - width * 0.35, cz), color=color)
    top = box_prism(depth * 0.35, width, height * 0.25, center=(cx, cy, cz + height * 0.35), color=color)
    right = box_prism(depth * 0.35, width * 0.18, height, center=(cx, cy + width * 0.35, cz), color=color)
    return merge_meshes(leg, top, right)


def curved_magazine(
    length: float,
    width: float,
    thickness: float,
    center: tuple[float, float, float],
    tilt_deg: float = 25.0,
    color: tuple[int, int, int] = (72, 72, 78),
) -> trimesh.Trimesh:
    """Exaggerated curved magazine block."""
    mesh = box_prism(length, width, thickness, center=center, color=color)
    rot = trimesh.transformations.rotation_matrix(np.radians(tilt_deg), [0, 0, 1])
    mesh.apply_transform(rot)
    return mesh


def segmented_magazine(
    segments: int,
    seg_length: float,
    width: float,
    thickness: float,
    start_center: tuple[float, float, float],
    tilt_deg: float = 22.0,
    color: tuple[int, int, int] = (96, 98, 104),
) -> trimesh.Trimesh:
    """Curved magazine from thick block segments."""
    cx, cy, cz = start_center
    parts = []
    for i in range(segments):
        t = i / max(segments - 1, 1)
        angle = np.radians(tilt_deg)
        dx = i * seg_length * 0.85 * np.cos(angle)
        dy = -i * seg_length * 0.55 * np.sin(angle)
        parts.append(
            box_prism(
                seg_length,
                width,
                thickness,
                center=(cx + dx, cy + dy, cz),
                color=color,
            )
        )
    return merge_meshes(*parts)


def merge_meshes(*meshes: trimesh.Trimesh) -> trimesh.Trimesh:
    if not meshes:
        raise ValueError("No meshes to merge")
    if len(meshes) == 1:
        return meshes[0].copy()
    return trimesh.util.concatenate([m.copy() for m in meshes])
