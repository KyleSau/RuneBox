"""Apply RS frame transforms to a model's vertices (ports Model.applyTransform).

Operates on a merged, labelled model: integer vertices plus a per-vertex label
(``vertex_skins``). Each frame's :class:`SeqTransform` mutates a fresh copy of
the base vertices; frames are independent (not cumulative).
"""

from __future__ import annotations

import math

import numpy as np

from src.rs2.seq_decoder import (
    OP_ALPHA,
    OP_BASE,
    OP_ROTATE,
    OP_SCALE,
    OP_TRANSLATE,
    SeqTransform,
    SeqType,
)

_SIN = [int(math.sin(i * 0.0030679615) * 65536) for i in range(2048)]
_COS = [int(math.cos(i * 0.0030679615) * 65536) for i in range(2048)]


def build_label_vertices(vertex_skins: list[int] | None) -> list[list[int]]:
    """label id -> list of vertex indices (ports Model.createLabelReferences)."""
    if not vertex_skins:
        return []
    max_label = max(vertex_skins)
    groups: list[list[int]] = [[] for _ in range(max_label + 1)]
    for v, label in enumerate(vertex_skins):
        groups[label].append(v)
    return groups


def build_label_faces(face_skins: list[int] | None) -> list[list[int]]:
    """label id -> list of face indices (ports Model.createLabelReferences for faces)."""
    if not face_skins:
        return []
    max_label = max(face_skins)
    groups: list[list[int]] = [[] for _ in range(max_label + 1)]
    for f, label in enumerate(face_skins):
        groups[label].append(f)
    return groups


def apply_transform(
    vertices: list[list[int]],
    label_vertices: list[list[int]],
    transform: SeqTransform,
    *,
    face_alphas: list[int] | None = None,
    label_faces: list[list[int]] | None = None,
) -> None:
    """Apply one frame transform in place to ``vertices`` (and optionally face alphas)."""
    skeleton = transform.skeleton
    base = [0, 0, 0]
    for i in range(len(transform.bases)):
        b = transform.bases[i]
        _op(
            vertices,
            label_vertices,
            base,
            skeleton.base_types[b],
            skeleton.base_labels[b],
            transform.x[i],
            transform.y[i],
            transform.z[i],
            face_alphas=face_alphas,
            label_faces=label_faces,
        )


def _op(
    vertices,
    label_vertices,
    base,
    type_,
    labels,
    x,
    y,
    z,
    *,
    face_alphas=None,
    label_faces=None,
):
    n = len(label_vertices)
    if type_ == OP_BASE:
        cx = cy = cz = 0
        count = 0
        for label in labels:
            if label >= n:
                continue
            for v in label_vertices[label]:
                cx += vertices[v][0]
                cy += vertices[v][1]
                cz += vertices[v][2]
                count += 1
        if count > 0:
            base[0] = cx // count + x
            base[1] = cy // count + y
            base[2] = cz // count + z
        else:
            base[0], base[1], base[2] = x, y, z
    elif type_ == OP_TRANSLATE:
        for label in labels:
            if label >= n:
                continue
            for v in label_vertices[label]:
                vertices[v][0] += x
                vertices[v][1] += y
                vertices[v][2] += z
    elif type_ == OP_ROTATE:
        bx, by, bz = base
        pitch = (x & 0xFF) * 8
        yaw = (y & 0xFF) * 8
        roll = (z & 0xFF) * 8
        for label in labels:
            if label >= n:
                continue
            for v in label_vertices[label]:
                vx = vertices[v][0] - bx
                vy = vertices[v][1] - by
                vz = vertices[v][2] - bz
                if roll != 0:
                    s = _SIN[roll]
                    c = _COS[roll]
                    nx = (vy * s + vx * c) >> 16
                    vy = (vy * c - vx * s) >> 16
                    vx = nx
                if pitch != 0:
                    s = _SIN[pitch]
                    c = _COS[pitch]
                    ny = (vy * c - vz * s) >> 16
                    vz = (vy * s + vz * c) >> 16
                    vy = ny
                if yaw != 0:
                    s = _SIN[yaw]
                    c = _COS[yaw]
                    nx = (vz * s + vx * c) >> 16
                    vz = (vz * c - vx * s) >> 16
                    vx = nx
                vertices[v][0] = vx + bx
                vertices[v][1] = vy + by
                vertices[v][2] = vz + bz
    elif type_ == OP_SCALE:
        bx, by, bz = base
        for label in labels:
            if label >= n:
                continue
            for v in label_vertices[label]:
                vertices[v][0] = (vertices[v][0] - bx) * x // 128 + bx
                vertices[v][1] = (vertices[v][1] - by) * y // 128 + by
                vertices[v][2] = (vertices[v][2] - bz) * z // 128 + bz
    elif type_ == OP_ALPHA:
        if label_faces is None or face_alphas is None:
            return
        for label in labels:
            if label >= len(label_faces):
                continue
            for face_idx in label_faces[label]:
                face_alphas[face_idx] += x * 8
                if face_alphas[face_idx] < 0:
                    face_alphas[face_idx] = 0
                elif face_alphas[face_idx] > 255:
                    face_alphas[face_idx] = 255


def face_alphas_after_transform(merged, transform: SeqTransform) -> list[int]:
    """Face alphas after one RS animation frame (ports Model.applyTransform OP_ALPHA)."""
    base_alphas = list(merged.face_alphas or [0] * len(merged.faces))
    if not merged.face_skins:
        return base_alphas
    label_faces = build_label_faces(merged.face_skins)
    label_vertices = build_label_vertices(merged.vertex_skins)
    dummy = [list(v) for v in merged.vertices]
    apply_transform(
        dummy,
        label_vertices,
        transform,
        face_alphas=base_alphas,
        label_faces=label_faces,
    )
    return base_alphas


def get_seq_frame_duration(
    seq: SeqType, frame: int, transforms: dict[int, SeqTransform]
) -> int:
    """Ports ``SeqType.getFrameDuration`` (seq.dat duration, else transform delay)."""
    dur = 0
    if frame < len(seq.durations):
        dur = seq.durations[frame]
    if dur == 0:
        tid = seq.transform_ids[frame] if frame < len(seq.transform_ids) else -1
        transform = transforms.get(tid)
        if transform is not None:
            dur = transform.delay
    if dur == 0:
        dur = 1
    return dur


def build_seq_durations(
    seq: SeqType, transforms: dict[int, SeqTransform]
) -> list[int]:
    """Per-frame display lengths in RS client cycles (20 ms each)."""
    return [get_seq_frame_duration(seq, f, transforms) for f in range(seq.frame_count)]


def spotanim_face_alphas_for_export(
    model,
    seq: SeqType,
    transforms: dict[int, SeqTransform],
) -> list[int]:
    """Per-face max RS faceAlpha across all frames (most transparent state).

    Static GLB grouping uses these so faces stay in BLEND primitives while COLOR
    morphs animate toward opaque frames (ice barrage, ghosts, etc.).
    """
    base = list(model.face_alphas or [0] * len(model.faces))
    if seq is None or not model.face_skins:
        return base
    label_faces = build_label_faces(model.face_skins)
    label_vertices = build_label_vertices(model.vertex_skins)
    for fi in range(seq.frame_count):
        tid = seq.transform_ids[fi] if fi < len(seq.transform_ids) else -1
        transform = transforms.get(tid)
        if transform is None:
            continue
        alphas = list(model.face_alphas or [0] * len(model.faces))
        dummy = [list(v) for v in model.vertices]
        apply_transform(
            dummy,
            label_vertices,
            transform,
            face_alphas=alphas,
            label_faces=label_faces,
        )
        for i, a in enumerate(alphas):
            if a > base[i]:
                base[i] = a
    return base


def spotanim_posed_vertices(
    model,
    seq: SeqType,
    transforms: dict[int, SeqTransform],
    frame: int,
    *,
    scale_xy: int = 128,
    scale_z: int = 128,
    rotation: int = 0,
) -> list[list[int]]:
    """Vertices after one spotanim frame (ports ``SpotAnimEntity.getModel``)."""
    label_vertices = build_label_vertices(model.vertex_skins)
    work = [list(v) for v in model.vertices]
    tid = seq.transform_ids[frame] if frame < len(seq.transform_ids) else -1
    if tid >= 0:
        transform = transforms.get(tid)
        if transform is not None:
            apply_transform(work, label_vertices, transform)
    scaled = _scale_int(work, scale_xy, scale_z)
    _apply_rs_rotation(scaled, rotation)
    return scaled


def spotanim_face_alphas_at_frame(
    model,
    seq: SeqType,
    transforms: dict[int, SeqTransform],
    frame: int,
) -> list[int]:
    """Face alphas after the frame's transform (OP_ALPHA)."""
    alphas = list(model.face_alphas or [0] * len(model.faces))
    if not model.face_skins:
        return alphas
    tid = seq.transform_ids[frame] if frame < len(seq.transform_ids) else -1
    transform = transforms.get(tid)
    if transform is None:
        return alphas
    return face_alphas_after_transform(model, transform)


def pick_display_face_alphas(merged, seq: SeqType, transforms: dict[int, SeqTransform]) -> list[int]:
    """Pick the idle frame with the strongest transparency (ghosts, spirits)."""
    if seq is None or not merged.face_skins:
        return list(merged.face_alphas or [0] * len(merged.faces))
    best = list(merged.face_alphas or [0] * len(merged.faces))
    best_score = sum(best)
    for fi in range(seq.frame_count):
        tid = seq.transform_ids[fi] if fi < len(seq.transform_ids) else -1
        transform = transforms.get(tid)
        if transform is None:
            continue
        alphas = face_alphas_after_transform(merged, transform)
        score = sum(alphas)
        if score > best_score:
            best_score = score
            best = alphas
    return best


def _scale_int(vertices: list[list[int]], scale_xy: int, scale_z: int) -> list[list[int]]:
    """Apply NPC resize the way the client does (integer, before animating):
    width (x,z) by scale_xy, height (y) by scale_z."""
    if scale_xy == 128 and scale_z == 128:
        return [list(v) for v in vertices]
    out = []
    for x, y, z in vertices:
        out.append([x * scale_xy // 128, y * scale_z // 128, z * scale_xy // 128])
    return out


def _y_up(vertices: list[list[int]]) -> np.ndarray:
    """RS (Y-down) -> Y-up via 180 deg rotation about X (negate Y and Z),
    matching mesh_assembly._scaled_y_up (sans scale, already applied)."""
    arr = np.asarray(vertices, dtype="f4")
    arr[:, 1] = -arr[:, 1]
    arr[:, 2] = -arr[:, 2]
    return arr


def _rotate_y90_rs(vertices: list[list[int]]) -> None:
    """Ports Model.rotateY90 (clockwise on Y in RS space)."""
    for v in vertices:
        x, y, z = v
        v[0] = z
        v[2] = -x


def _apply_rs_rotation(vertices: list[list[int]], rotation: int) -> None:
    if rotation in (0, 360):
        return
    steps = (rotation // 90) % 4
    for _ in range(steps):
        _rotate_y90_rs(vertices)


def compute_seq_morphs(
    model,
    seq: SeqType,
    transforms: dict[int, SeqTransform],
    *,
    scale_xy: int = 128,
    scale_z: int = 128,
    rotation: int = 0,
    pose_fn=None,
):
    """Per-frame position + COLOR morphs (one transform id per frame).

    Used for NPC stand (secondary seq) and spotanims. Rest pose is frame 0 after
    transform + scale. Frame timing uses ``getFrameDuration + 1`` client cycles
    (secondary / spotanim entity paths).

    ``pose_fn(frame) -> list[list[int]]`` lets callers supply their own posing
    (e.g. locs, which scale/rotate/translate differently than spotanims). It must
    return RS-space (Y-down) integer vertices; ``_y_up`` is applied here.

    Returns ``(pos_deltas, color_deltas, durations, export_alphas)`` or ``None``.
    """
    if seq is None or seq.frame_count <= 1:
        return None
    if not model.vertex_skins:
        return None

    if pose_fn is None:
        def pose_fn(fi: int):
            return spotanim_posed_vertices(
                model,
                seq,
                transforms,
                fi,
                scale_xy=scale_xy,
                scale_z=scale_z,
                rotation=rotation,
            )

    def _pose_for_frame(fi: int) -> np.ndarray:
        return _y_up(pose_fn(fi))

    rest = _pose_for_frame(0)
    n_verts = len(rest)
    export_alphas = spotanim_face_alphas_for_export(model, seq, transforms)

    def _vertex_colors(fi: int, *, baseline_export: bool = False) -> np.ndarray:
        """Per-model-vertex alpha in 0–1 (matches mesh COLOR_0 alpha channel)."""
        if baseline_export:
            alphas = export_alphas
        else:
            alphas = spotanim_face_alphas_at_frame(model, seq, transforms, fi)
        colors = np.zeros((n_verts, 4), dtype="f4")
        for face_i, (a, b, c) in enumerate(model.faces):
            alpha_rs = alphas[face_i] if face_i < len(alphas) else 0
            a8 = (255 - alpha_rs) / 255.0
            for vi in (a, b, c):
                if 0 <= vi < n_verts:
                    colors[vi, 3] = max(colors[vi, 3], a8)
        return colors

    # Mesh base COLOR uses export (most transparent) alphas; morph from that baseline.
    rest_colors = _vertex_colors(0, baseline_export=True)

    deltas: list[np.ndarray] = []
    color_deltas: list[np.ndarray] = []
    durations = build_seq_durations(seq, transforms)
    any_motion = False
    any_color = False

    for fi in range(seq.frame_count):
        posed = _pose_for_frame(fi)
        delta = posed - rest
        if np.abs(delta).max() > 0.01:
            any_motion = True
        deltas.append(delta)

        frame_colors = _vertex_colors(fi)
        c_delta = frame_colors - rest_colors
        if np.abs(c_delta).max() > 1.0 / 255.0:
            any_color = True
        color_deltas.append(c_delta)

    if not any_motion and not any_color:
        return None
    return deltas, color_deltas, durations, export_alphas


def compute_frame_morphs(
    merged,
    seq: SeqType,
    transforms: dict[int, SeqTransform],
    scale_xy: int = 128,
    scale_z: int = 128,
):
    """NPC stand / idle morphs (ports secondary seq on ``PathingEntity``)."""
    return compute_seq_morphs(
        merged, seq, transforms, scale_xy=scale_xy, scale_z=scale_z, rotation=0
    )


def compute_spotanim_morphs(
    model,
    seq: SeqType,
    transforms: dict[int, SeqTransform],
    *,
    scale_xy: int = 128,
    scale_z: int = 128,
    rotation: int = 0,
):
    """Spotanim GFX morphs (ports ``SpotAnimEntity.getModel``)."""
    return compute_seq_morphs(
        model,
        seq,
        transforms,
        scale_xy=scale_xy,
        scale_z=scale_z,
        rotation=rotation,
    )
