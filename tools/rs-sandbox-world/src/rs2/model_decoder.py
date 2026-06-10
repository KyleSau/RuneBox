"""RS317/377 model container decode (matches Model.unpack + Model(int id))."""

from __future__ import annotations

import gzip
import zlib
from dataclasses import dataclass, field

from .buffer import Buffer


def prepare_model_bytes(data: bytes) -> bytes:
    """Decompress gzip model payloads (OnDemand.poll applies this before Model.unpack)."""
    if len(data) >= 2 and data[0] == 0x1F and data[1] == 0x8B:
        try:
            return gzip.decompress(data)
        except OSError:
            # OpenRS2/377 dumps often omit gzip CRC; zlib accepts them.
            return zlib.decompress(data, zlib.MAX_WBITS | 32)
    return data


@dataclass
class ModelHeader:
    vertex_count: int = 0
    face_count: int = 0
    textured_face_count: int = 0
    vertex_flags_offset: int = 0
    vertex_x_offset: int = 0
    vertex_y_offset: int = 0
    vertex_z_offset: int = 0
    vertex_labels_offset: int = -1
    face_vertices_offset: int = 0
    face_orientations_offset: int = 0
    face_colors_offset: int = 0
    face_infos_offset: int = -1
    face_priorities_offset: int = -1
    face_alphas_offset: int = -1
    face_labels_offset: int = -1
    face_texture_axis_offset: int = 0
    priority: int = -1


@dataclass
class RSModel:
    model_id: int
    vertices: list[list[int]]
    faces: list[list[int]]
    face_colors: list[int]
    face_infos: list[int] | None = None
    face_priorities: list[int] | None = None
    face_alphas: list[int] | None = None
    vertex_skins: list[int] | None = None
    face_skins: list[int] | None = None
    textured_faces: list[list[int]] = field(default_factory=list)
    priority: int = -1
    raw_size: int = 0

    def to_json_dict(self) -> dict:
        face_textures: list[int | None] = []
        if self.face_infos is not None:
            for info, color in zip(self.face_infos, self.face_colors):
                if (info & 2) == 2:
                    face_textures.append(color)
                else:
                    face_textures.append(None)
        else:
            face_textures = [None] * len(self.face_colors)

        return {
            "modelId": self.model_id,
            "vertices": self.vertices,
            "faces": self.faces,
            "faceColors": self.face_colors,
            "faceTextures": face_textures,
            "facePriorities": self.face_priorities,
            "faceAlphas": self.face_alphas,
            "vertexSkins": self.vertex_skins,
            "faceSkins": self.face_skins,
            "texturedFaces": self.textured_faces,
            "metadata": {
                "source": "377 cache",
                "format": "317/377 Model.dat (Jagex compressed mesh)",
                "vertexCount": len(self.vertices),
                "faceCount": len(self.faces),
                "texturedFaceCount": len(self.textured_faces),
                "globalPriority": self.priority if self.priority >= 0 else None,
                "rawByteSize": self.raw_size,
            },
        }


def parse_header(data: bytes) -> ModelHeader | None:
    if not data:
        return None
    buf = Buffer(data)
    buf.position = len(data) - 18
    header = ModelHeader()
    header.vertex_count = buf.read_u16()
    header.face_count = buf.read_u16()
    header.textured_face_count = buf.read_u8()
    has_info = buf.read_u8()
    priority_flag = buf.read_u8()
    has_alpha = buf.read_u8()
    has_face_labels = buf.read_u8()
    has_vertex_labels = buf.read_u8()
    data_length_x = buf.read_u16()
    data_length_y = buf.read_u16()
    data_length_z = buf.read_u16()
    data_length_face_orientations = buf.read_u16()

    offset = 0
    header.vertex_flags_offset = offset
    offset += header.vertex_count

    header.face_orientations_offset = offset
    offset += header.face_count

    if priority_flag == 255:
        header.face_priorities_offset = offset
        offset += header.face_count
    else:
        header.face_priorities_offset = -priority_flag - 1
        # Java Model(int id): priority = -facePrioritiesOffset - 1 == priority_flag
        header.priority = priority_flag

    if has_face_labels == 1:
        header.face_labels_offset = offset
        offset += header.face_count
    else:
        header.face_labels_offset = -1

    if has_info == 1:
        header.face_infos_offset = offset
        offset += header.face_count
    else:
        header.face_infos_offset = -1

    if has_vertex_labels == 1:
        header.vertex_labels_offset = offset
        offset += header.vertex_count
    else:
        header.vertex_labels_offset = -1

    if has_alpha == 1:
        header.face_alphas_offset = offset
        offset += header.face_count
    else:
        header.face_alphas_offset = -1

    header.face_vertices_offset = offset
    offset += data_length_face_orientations

    header.face_colors_offset = offset
    offset += header.face_count * 2

    header.face_texture_axis_offset = offset
    offset += header.textured_face_count * 6

    header.vertex_x_offset = offset
    offset += data_length_x
    header.vertex_y_offset = offset
    offset += data_length_y
    header.vertex_z_offset = offset
    return header


def decode_model(model_id: int, data: bytes) -> RSModel | None:
    data = prepare_model_bytes(data)
    header = parse_header(data)
    if header is None or header.vertex_count == 0:
        return None

    buf0 = Buffer(data)
    buf0.position = header.vertex_flags_offset
    buf1 = Buffer(data)
    buf1.position = header.vertex_x_offset
    buf2 = Buffer(data)
    buf2.position = header.vertex_y_offset
    buf3 = Buffer(data)
    buf3.position = header.vertex_z_offset
    buf4 = Buffer(data)
    if header.vertex_labels_offset >= 0:
        buf4.position = header.vertex_labels_offset

    vertices: list[list[int]] = []
    vertex_skins: list[int] | None = [] if header.vertex_labels_offset >= 0 else None
    x = y = z = 0

    for _ in range(header.vertex_count):
        flags = buf0.read_u8()
        dx = buf1.read_smart() if flags & 1 else 0
        dy = buf2.read_smart() if flags & 2 else 0
        dz = buf3.read_smart() if flags & 4 else 0
        x += dx
        y += dy
        z += dz
        vertices.append([x, y, z])
        if vertex_skins is not None:
            vertex_skins.append(buf4.read_u8())

    buf0.position = header.face_colors_offset
    buf1.position = header.face_infos_offset if header.face_infos_offset >= 0 else 0
    buf2.position = header.face_priorities_offset if header.face_priorities_offset >= 0 else 0
    buf3.position = header.face_alphas_offset if header.face_alphas_offset >= 0 else 0
    buf4.position = header.face_labels_offset if header.face_labels_offset >= 0 else 0

    face_colors: list[int] = []
    face_infos: list[int] | None = [] if header.face_infos_offset >= 0 else None
    face_priorities: list[int] | None = [] if header.face_priorities_offset >= 0 else None
    face_alphas: list[int] | None = [] if header.face_alphas_offset >= 0 else None
    face_skins: list[int] | None = [] if header.face_labels_offset >= 0 else None

    for _ in range(header.face_count):
        face_colors.append(buf0.read_u16())
        if face_infos is not None:
            face_infos.append(buf1.read_u8())
        if face_priorities is not None:
            face_priorities.append(buf2.read_u8())
        if face_alphas is not None:
            face_alphas.append(buf3.read_u8())
        if face_skins is not None:
            face_skins.append(buf4.read_u8())

    buf0.position = header.face_vertices_offset
    buf1.position = header.face_orientations_offset

    faces: list[list[int]] = []
    a = b = c = 0
    last = 0

    for _ in range(header.face_count):
        orientation = buf1.read_u8()
        if orientation == 1:
            a = buf0.read_smart() + last
            last = a
            b = buf0.read_smart() + last
            last = b
            c = buf0.read_smart() + last
            last = c
        elif orientation == 2:
            b = c
            c = buf0.read_smart() + last
            last = c
        elif orientation == 3:
            a = c
            c = buf0.read_smart() + last
            last = c
        elif orientation == 4:
            a, b = b, a
            c = buf0.read_smart() + last
            last = c
        faces.append([a, b, c])

    buf0.position = header.face_texture_axis_offset
    textured_faces: list[list[int]] = []
    for _ in range(header.textured_face_count):
        textured_faces.append([buf0.read_u16(), buf0.read_u16(), buf0.read_u16()])

    return RSModel(
        model_id=model_id,
        vertices=vertices,
        faces=faces,
        face_colors=face_colors,
        face_infos=face_infos,
        face_priorities=face_priorities,
        face_alphas=face_alphas,
        vertex_skins=vertex_skins,
        face_skins=face_skins,
        textured_faces=textured_faces,
        priority=header.priority,
        raw_size=len(data),
    )
