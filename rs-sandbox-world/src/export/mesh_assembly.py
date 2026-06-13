"""Assemble exportable triangle soup from RS models / NPC definitions.

Each :class:`Triangle` carries flat RS shading either as a baked RGBA colour or
as a texture id + per-vertex UVs. Coordinates are converted from RS space
(Y-down) to a Y-up convention so models stand upright after glТF import.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.export.uv_baking import planar_uvs
from src.export.texture_archive import TextureSprite
from src.rs2.model_decoder import RSModel, decode_model
from src.rs2.palette import hsl_to_rgb

Vec3 = tuple[float, float, float]
Vec2 = tuple[float, float]

# RS face priority is 0–11 within one model. Stacked NPC component models are
# drawn back-to-front in the client without a depth buffer; our GLB merge uses
# z-buffering so coplanar clothing/body faces z-fight unless later layers get
# a higher effective priority (encoded in material names for polygon offset).
MODEL_LAYER_STRIDE = 12
MAX_DRAW_PRIORITY = 127


def _build_srgb_to_linear_lut() -> list[int]:
    """glТF COLOR_0 is linear; the RS palette is sRGB. Convert once via a LUT."""
    lut = []
    for value in range(256):
        c = value / 255.0
        c = c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
        lut.append(max(0, min(255, round(c * 255.0))))
    return lut


_SRGB_TO_LINEAR = _build_srgb_to_linear_lut()


@dataclass
class Triangle:
    v0: Vec3
    v1: Vec3
    v2: Vec3
    rgba: tuple[int, int, int, int] = (200, 200, 200, 255)
    texture_id: int | None = None
    uv0: Vec2 | None = None
    uv1: Vec2 | None = None
    uv2: Vec2 | None = None
    priority: int = 0
    # Source vertex indices into the (merged) model's vertex array. Populated for
    # animated exports so morph targets can look up each vertex's deformed
    # position per frame. -1 means "no source" (non-animated path).
    i0: int = -1
    i1: int = -1
    i2: int = -1
    face_index: int = -1


@dataclass
class MergedModel:
    """An NPC's component models merged into one labelled model so a single
    skeleton/animation can deform it. Duck-types the fields ``model_to_triangles``
    and ``_face_priority`` read, plus ``vertex_skins`` for animation."""

    vertices: list[list[int]]
    faces: list[tuple[int, int, int]]
    face_colors: list[int]
    face_infos: list[int] | None
    face_alphas: list[int] | None
    textured_faces: list
    face_priorities: list[int] | None
    vertex_skins: list[int]
    face_skins: list[int] | None = None
    priority: int = -1


def _scaled_y_up(vertex: list[int], scale_xy: int, scale_z: int) -> Vec3:
    sx = scale_xy / 128.0
    sz = scale_z / 128.0
    x, y, z = vertex
    # RS Y-down → Y-up; negate Z so rotateY90 facing matches 317 (rot 1 = north/+Z).
    return (float(x) * sx, float(-y) * sz, float(-z) * sx)


def _face_priority(model: RSModel, index: int) -> int:
    """RS draw priority (0-11) for a face: per-face when present, else the
    model's global priority. Used as a draw-time depth bias (not geometry) so
    higher-priority faces (e.g. a hat) occlude lower ones (hair) like the client."""
    if model.face_priorities is not None:
        return model.face_priorities[index]
    if model.priority >= 0:
        return model.priority
    return 0


def _stacked_priority(face_priority: int, model_layer: int) -> int:
    """Effective draw priority for a face on the Nth stacked component model."""
    return min(MAX_DRAW_PRIORITY, face_priority + model_layer * MODEL_LAYER_STRIDE)


def ordered_model_ids(
    base_ids: list[int] | None,
    extra_ids: list[int] | None = None,
) -> list[int]:
    """Base body/NPC models first, equipment/cape add-ons last (317 draw order)."""
    mids = list(base_ids or [])
    for mid in extra_ids or []:
        if mid is None:
            continue
        mid = int(mid)
        if mid >= 0 and mid not in mids:
            mids.append(mid)
    return mids


def model_to_triangles(
    model: RSModel,
    palette: list[int],
    recolor: dict[int, int] | None = None,
    scale_xy: int = 128,
    scale_z: int = 128,
    textures: dict[int, object] | None = None,
    texture_sprites: dict[int, TextureSprite] | None = None,
    *,
    vertices: list[list[int]] | None = None,
    face_alphas: list[int] | None = None,
    model_layer: int = 0,
    flip_winding: bool = False,
) -> list[Triangle]:
    recolor = recolor or {}
    vertices = vertices if vertices is not None else model.vertices
    face_alphas_src = face_alphas if face_alphas is not None else model.face_alphas
    triangles: list[Triangle] = []

    for i, (a, b, c) in enumerate(model.faces):
        if flip_winding:
            a, c = c, a
        info = model.face_infos[i] if model.face_infos else 0
        color = model.face_colors[i]
        alpha_rs = face_alphas_src[i] if face_alphas_src else 0
        textured = info is not None and (info & 2) == 2
        priority = _stacked_priority(_face_priority(model, i), model_layer)
        if isinstance(model, MergedModel) and model.face_priorities is not None:
            priority = model.face_priorities[i]

        p0 = _scaled_y_up(vertices[a], scale_xy, scale_z)
        p1 = _scaled_y_up(vertices[b], scale_xy, scale_z)
        p2 = _scaled_y_up(vertices[c], scale_xy, scale_z)

        a8 = 255 - alpha_rs if alpha_rs else 255

        if textured and textures and (color in textures):
            pqr_index = info >> 2
            if 0 <= pqr_index < len(model.textured_faces):
                p, q, r = model.textured_faces[pqr_index]
                try:
                    uv0, uv1, uv2 = planar_uvs(vertices, p, q, r, a, b, c)
                    sprite = (texture_sprites or {}).get(color)
                    if sprite is not None:
                        uv0 = sprite.remap_uv(*uv0)
                        uv1 = sprite.remap_uv(*uv1)
                        uv2 = sprite.remap_uv(*uv2)
                    triangles.append(
                        Triangle(
                            p0,
                            p1,
                            p2,
                            (255, 255, 255, a8),
                            color,
                            uv0,
                            uv1,
                            uv2,
                            priority=priority,
                            i0=a,
                            i1=b,
                            i2=c,
                            face_index=i,
                        )
                    )
                    continue
                except (ValueError, IndexError):
                    continue

        hsl = recolor.get(color, color)
        r8, g8, b8 = hsl_to_rgb(hsl, palette)
        triangles.append(
            Triangle(
                p0,
                p1,
                p2,
                (
                    _SRGB_TO_LINEAR[r8],
                    _SRGB_TO_LINEAR[g8],
                    _SRGB_TO_LINEAR[b8],
                    max(0, min(255, a8)),
                ),
                priority=priority,
                i0=a,
                i1=b,
                i2=c,
                face_index=i,
            )
        )

    return triangles


def merge_npc_model(npc, cache) -> MergedModel | None:
    """Merge an NPC's component models (convenience wrapper around merge_models)."""
    return merge_models(npc.model_ids or [], cache)


def merge_models(model_ids, cache) -> MergedModel | None:
    """Merge component models into one labelled :class:`MergedModel`,
    concatenating vertices (and per-vertex labels) and offsetting face / textured
    indices. Mirrors the client merging component models before animating
    (used for NPCs, multi-model scenery and assembled players)."""
    vertices: list[list[int]] = []
    faces: list[tuple[int, int, int]] = []
    face_colors: list[int] = []
    face_infos: list[int] = []
    face_alphas: list[int] = []
    textured_faces: list = []
    face_priorities: list[int] = []
    vertex_skins: list[int] = []
    face_skins: list[int] = []

    model_layer = 0
    for model_id in model_ids or []:
        raw = cache.read_model(model_id)
        if raw is None:
            continue
        model = decode_model(model_id, raw)
        if model is None:
            continue

        v_off = len(vertices)
        t_off = len(textured_faces)
        vertices.extend(list(v) for v in model.vertices)
        if model.vertex_skins:
            vertex_skins.extend(model.vertex_skins)
        else:
            vertex_skins.extend([0] * len(model.vertices))

        for tf in model.textured_faces:
            textured_faces.append(tuple(idx + v_off for idx in tf))

        for i, (a, b, c) in enumerate(model.faces):
            faces.append((a + v_off, b + v_off, c + v_off))
            face_colors.append(model.face_colors[i])
            face_alphas.append(model.face_alphas[i] if model.face_alphas else 0)
            face_priorities.append(_stacked_priority(_face_priority(model, i), model_layer))
            face_skins.append(model.face_skins[i] if model.face_skins else 0)

            info = model.face_infos[i] if model.face_infos else 0
            if info is None:
                info = 0
            if (info & 2) == 2:
                # Re-pack the textured face's pqr index with the merge offset.
                info = (((info >> 2) + t_off) << 2) | (info & 3)
            face_infos.append(info)

        model_layer += 1

    if not vertices or not faces:
        return None

    return MergedModel(
        vertices=vertices,
        faces=faces,
        face_colors=face_colors,
        face_infos=face_infos,
        face_alphas=face_alphas,
        textured_faces=textured_faces,
        face_priorities=face_priorities,
        vertex_skins=vertex_skins,
        face_skins=face_skins,
        priority=-1,
    )


def npc_recolor_map(npc) -> dict[int, int]:
    """Build the HSL recolour map for an NPC.

    The client (NPCType.java, opcode 40) stores recolours as *interleaved*
    ``src, dst, src, dst, ...`` pairs. ``src/cache/npc_index.py`` currently
    parses them as two sequential arrays (all srcs, then all dsts), which
    scrambles every pair (e.g. Hans' shirt mapped orange -> white instead of
    orange -> red, and the King Black Dragon's body mapped to red instead of
    black). Concatenating the two halves recovers the original interleaved
    stream, so we re-pair it here. (Fix belongs in npc_index.py, but that module
    sits under a ``cache/`` path excluded by .cursorignore.)
    """
    src = list(npc.color_src or [])
    dst = list(npc.color_dst or [])
    if not src or not dst:
        return {}
    if len(src) == len(dst):
        flat = src + dst
        return dict(zip(flat[0::2], flat[1::2]))
    return dict(zip(src, dst))


def assemble_npc_triangles(
    npc,
    cache,
    palette: list[int],
    textures: dict[int, object] | None = None,
    texture_sprites=None,
) -> list[Triangle]:
    """Merge an NPC's component models into a single recoloured triangle soup."""
    recolor = npc_recolor_map(npc)
    triangles: list[Triangle] = []

    model_layer = 0
    for model_id in npc.model_ids or []:
        raw = cache.read_model(model_id)
        if raw is None:
            continue
        model = decode_model(model_id, raw)
        if model is None:
            continue
        triangles.extend(
            model_to_triangles(
                model,
                palette,
                recolor=recolor,
                scale_xy=npc.scale_xy,
                scale_z=npc.scale_z,
                textures=textures,
                texture_sprites=texture_sprites,
                model_layer=model_layer,
            )
        )
        model_layer += 1

    return triangles
