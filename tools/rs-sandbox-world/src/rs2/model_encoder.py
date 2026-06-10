"""RS317/377 model encoder (inverse of Model.unpack + Model(int id) decode path)."""

from __future__ import annotations

from .byte_writer import ByteWriter
from .model_decoder import RSModel


def encode_model(model: RSModel) -> bytes:
    """Encode a decoded RSModel back into decompressed model bytes (before gzip)."""
    vertex_count = len(model.vertices)
    face_count = len(model.faces)
    textured_count = len(model.textured_faces)

    if vertex_count == 0 or face_count == 0:
        raise ValueError("Cannot encode empty model")

    has_info = model.face_infos is not None
    has_alpha = model.face_alphas is not None
    has_face_labels = model.face_skins is not None
    has_vertex_labels = model.vertex_skins is not None
    has_per_face_priority = model.face_priorities is not None

    if has_per_face_priority:
        priority_flag = 255
    elif model.priority >= 0:
        priority_flag = model.priority
    else:
        priority_flag = 0
    vertex_flags = ByteWriter()
    vertex_x = ByteWriter()
    vertex_y = ByteWriter()
    vertex_z = ByteWriter()
    prev_x = prev_y = prev_z = 0

    for idx, (x, y, z) in enumerate(model.vertices):
        dx = x - prev_x
        dy = y - prev_y
        dz = z - prev_z
        flags = 0
        if dx != 0:
            flags |= 1
            vertex_x.write_smart(dx)
        if dy != 0:
            flags |= 2
            vertex_y.write_smart(dy)
        if dz != 0:
            flags |= 4
            vertex_z.write_smart(dz)
        vertex_flags.write_u8(flags)
        prev_x, prev_y, prev_z = x, y, z

        if has_vertex_labels:
            pass  # written in separate section below

    vertex_labels = ByteWriter()
    if has_vertex_labels:
        for skin in model.vertex_skins or []:
            vertex_labels.write_u8(skin)

    # --- face orientations + vertex index stream ---
    face_orientations = ByteWriter()
    face_vertices = ByteWriter()
    last = 0
    state_a = state_b = state_c = 0

    for a, b, c in model.faces:
        orientation = _choose_orientation(a, b, c, state_a, state_b, state_c)
        face_orientations.write_u8(orientation)

        if orientation == 1:
            da = a - last
            last = a
            face_vertices.write_smart(da)
            db = b - last
            last = b
            face_vertices.write_smart(db)
            dc = c - last
            last = c
            face_vertices.write_smart(dc)
            state_a, state_b, state_c = a, b, c
        elif orientation == 2:
            state_b = state_c
            dc = c - last
            last = c
            face_vertices.write_smart(dc)
            state_c = c
            # state_a unchanged
        elif orientation == 3:
            state_a = state_c
            dc = c - last
            last = c
            face_vertices.write_smart(dc)
            state_c = c
            # state_b unchanged
        elif orientation == 4:
            state_a, state_b = state_b, state_a
            dc = c - last
            last = c
            face_vertices.write_smart(dc)
            state_c = c
        else:
            raise ValueError(f"Unsupported orientation {orientation}")

    face_priorities = ByteWriter()
    if has_per_face_priority:
        for value in model.face_priorities or []:
            face_priorities.write_u8(value)

    face_labels = ByteWriter()
    if has_face_labels:
        for value in model.face_skins or []:
            face_labels.write_u8(value)

    face_infos = ByteWriter()
    if has_info:
        for value in model.face_infos or []:
            face_infos.write_u8(value)

    face_alphas = ByteWriter()
    if has_alpha:
        for value in model.face_alphas or []:
            face_alphas.write_u8(value)

    face_colors = ByteWriter()
    for color in model.face_colors:
        face_colors.write_u16(color)

    textured = ByteWriter()
    for axis in model.textured_faces:
        if len(axis) != 3:
            raise ValueError(f"Textured face must have 3 axis indices, got {axis!r}")
        textured.write_u16(axis[0])
        textured.write_u16(axis[1])
        textured.write_u16(axis[2])

    # Section order matches Model.unpack offsets.
    body = ByteWriter()
    body.extend(vertex_flags.data)
    body.extend(face_orientations.data)
    if has_per_face_priority:
        body.extend(face_priorities.data)
    if has_face_labels:
        body.extend(face_labels.data)
    if has_info:
        body.extend(face_infos.data)
    if has_vertex_labels:
        body.extend(vertex_labels.data)
    if has_alpha:
        body.extend(face_alphas.data)
    body.extend(face_vertices.data)
    body.extend(face_colors.data)
    body.extend(textured.data)
    body.extend(vertex_x.data)
    body.extend(vertex_y.data)
    body.extend(vertex_z.data)

    trailer = ByteWriter()
    trailer.write_u16(vertex_count)
    trailer.write_u16(face_count)
    trailer.write_u8(textured_count)
    trailer.write_u8(1 if has_info else 0)
    trailer.write_u8(priority_flag)
    trailer.write_u8(1 if has_alpha else 0)
    trailer.write_u8(1 if has_face_labels else 0)
    trailer.write_u8(1 if has_vertex_labels else 0)
    trailer.write_u16(len(vertex_x.data))
    trailer.write_u16(len(vertex_y.data))
    trailer.write_u16(len(vertex_z.data))
    trailer.write_u16(len(face_vertices.data))

    body.extend(trailer.data)
    return bytes(body.data)


def _choose_orientation(
    a: int,
    b: int,
    c: int,
    state_a: int,
    state_b: int,
    state_c: int,
) -> int:
    """Pick a valid face orientation opcode (matches Model.java decode)."""
    if a == state_a and c == state_c and b == state_c:
        return 2
    if a == state_c and b == state_b:
        return 3
    if a == state_b and b == state_a:
        return 4
    return 1


def wrap_model_gzip(data: bytes) -> bytes:
    """Wrap decompressed model bytes the way idx1 stores them (gzip payload)."""
    import gzip

    return gzip.compress(data, compresslevel=9, mtime=0)
