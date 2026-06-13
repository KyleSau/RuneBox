"""Build scenery (LocType / loc.dat) GLB bytes from the 377 cache.

Ports the static parts of LocType.getModel: pick the model for a kind, rotate
(rotateY90 x rotation), recolour, scale (x,y,z) and translate. Terrain
adjustment, occlusion and animation are out of scope for the viewer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from src.cache.config_locator import load_config_archive
from src.export.animation import (
    apply_transform,
    build_label_vertices,
    compute_seq_morphs,
)
from src.export.gltf_export import build_glb_bytes
from src.export.mesh_assembly import merge_models, model_to_triangles
from src.export.texture_archive import load_texture_images, load_texture_sprites
from src.rs2.loc_decoder import LocType, decode_loc_types, loc_display_name, loc_examine_text, loc_is_interactable, loc_menu_name, loc_recolor_map
from src.rs2.model_decoder import decode_model
from src.rs2.palette import build_palette

if TYPE_CHECKING:
    from src.cache.cache_locator import CacheReader
    from src.export.anim_data import AnimationData


def _rotate_y90(verts: list[list[int]]) -> None:
    """Ports Model.rotateY90 (RS clockwise about Y)."""
    for v in verts:
        x, _, z = v
        v[0] = z
        v[2] = -x


def _rotate_y180(verts: list[list[int]]) -> None:
    """317 Model.rotateY180 — negate Z only (not X). Face A/C swap handled at export."""
    for v in verts:
        v[2] = -v[2]


def _transform(verts: list[list[int]], loc: LocType, rotation: int) -> bool:
    """Apply LocType.getModel rotation. Returns True when invert^rot>3 flip was applied."""
    rot = rotation & 0xFF
    flip = bool(loc.invert ^ (rot > 3))
    if flip:
        _rotate_y180(verts)
    for _ in range(rot):
        _rotate_y90(verts)
    if loc.scale_x != 128 or loc.scale_y != 128 or loc.scale_z != 128:
        for v in verts:
            v[0] = v[0] * loc.scale_x // 128
            v[1] = v[1] * loc.scale_y // 128
            v[2] = v[2] * loc.scale_z // 128
    if loc.translate_x or loc.translate_y or loc.translate_z:
        for v in verts:
            v[0] += loc.translate_x
            v[1] += loc.translate_y
            v[2] += loc.translate_z
    return flip


@dataclass
class LocRenderContext:
    cache: "CacheReader"
    locs: dict[int, LocType]
    palette: list[int]
    anim: "AnimationData | None" = None
    textures: dict[int, object] | None = None
    texture_sprites: dict | None = None
    _textures_loaded: bool = False

    def ensure_textures(self) -> dict[int, object]:
        if not self._textures_loaded:
            self.texture_sprites = load_texture_sprites(self.cache)
            self.textures = {tid: s.image for tid, s in self.texture_sprites.items()}
            self._textures_loaded = True
        return self.textures or {}

    def ensure_texture_sprites(self) -> dict:
        self.ensure_textures()
        return self.texture_sprites or {}

    def get(self, loc_id: int) -> LocType | None:
        return self.locs.get(loc_id)

    @property
    def count(self) -> int:
        return len(self.locs)


def _load_model(ctx: LocRenderContext, model_ids: list[int]):
    if not model_ids:
        return None
    if len(model_ids) == 1:
        raw = ctx.cache.read_model(model_ids[0])
        if raw is None:
            return None
        return decode_model(model_ids[0], raw)
    return merge_models(model_ids, ctx.cache)


def build_loc_glb_bytes(
    ctx: LocRenderContext, loc_id: int, *, kind: int | None = None, rotation: int = 0
) -> bytes | None:
    loc = ctx.locs.get(loc_id)
    if loc is None:
        return None

    kinds = loc.kinds()
    if not kinds:
        return None
    if kind is None or kind not in kinds:
        kind = 10 if 10 in kinds else kinds[0]

    # Kind 11 (diagonal centrepiece) uses the kind-10 model + extra scene yaw in the viewer.
    model_kind = 10 if kind == 11 else kind
    if model_kind not in kinds and kind in kinds:
        model_kind = kind

    model_ids = loc.model_ids_for_kind(model_kind)
    model = _load_model(ctx, model_ids)
    if model is None or not model.faces:
        return None

    # Animated scenery (fires, fountains, ...) carries a seq id. Bake it as morph
    # targets the way spotanims do, posing the base model per frame then applying
    # the loc's own rotate/scale/translate so each frame lines up with the static
    # mesh. Without a usable seq this falls back to a single static pose.
    seq = None
    if ctx.anim is not None and loc.seq_id >= 0:
        seq = ctx.anim.seqs.get(loc.seq_id)

    label_vertices = build_label_vertices(model.vertex_skins)
    # Rigid seq locs (e.g. some torches) have no vertex skins; treat all verts as one group.
    if not label_vertices and seq is not None and model.vertices:
        label_vertices = [list(range(len(model.vertices)))]

    def _loc_pose(frame: int) -> list[list[int]]:
        work = [list(v) for v in model.vertices]
        if seq is not None:
            tid = seq.transform_ids[frame] if frame < len(seq.transform_ids) else -1
            if tid >= 0 and ctx.anim is not None:
                transform = ctx.anim.transforms.get(tid)
                if transform is not None:
                    apply_transform(work, label_vertices, transform)
        _transform(work, loc, rotation)
        return work

    verts = _loc_pose(0)
    flipped = bool(loc.invert ^ ((rotation & 0xFF) > 3))

    frame_deltas = frame_color_deltas = frame_durations = export_alphas = None
    if seq is not None and seq.frame_count > 1 and ctx.anim is not None:
        morphs = compute_seq_morphs(
            model,
            seq,
            ctx.anim.transforms,
            scale_xy=128,
            scale_z=128,
            rotation=0,
            pose_fn=_loc_pose,
        )
        if morphs is not None:
            frame_deltas, frame_color_deltas, frame_durations, export_alphas = morphs

    triangles = model_to_triangles(
        model,
        ctx.palette,
        recolor=loc_recolor_map(loc),
        scale_xy=128,
        scale_z=128,
        textures=ctx.ensure_textures(),
        texture_sprites=ctx.ensure_texture_sprites(),
        vertices=verts,
        face_alphas=export_alphas,
        flip_winding=flipped,
    )
    if not triangles:
        return None
    return build_glb_bytes(
        triangles,
        ctx.ensure_textures(),
        smooth=True,
        frame_deltas=frame_deltas,
        frame_color_deltas=frame_color_deltas,
        frame_durations=frame_durations,
        # LocEntity.getModel advances frames by exactly getFrameDuration cycles
        # (no +1), unlike SpotAnimEntity which uses getFrameDuration + 1. Match the
        # client so animated scenery (fires, etc.) runs at its true 317 cadence.
        frame_gap=0,
        loop=True,
        morph_interpolation="STEP",
        anim_name="loc",
    )


def loc_manifest_entry(loc: LocType) -> dict:
    kinds = loc.kinds()
    default_kind = 10 if 10 in kinds else (kinds[0] if kinds else -1)
    return {
        "id": loc.id,
        "menuName": loc_menu_name(loc) or "",
        "name": loc_display_name(loc),
        "file": f"/api/loc/{loc.id}.glb",
        "kinds": kinds,
        "defaultKind": default_kind,
        "sizeX": loc.size_x,
        "sizeZ": loc.size_z,
        "modelIds": list(loc.model_ids or []),
        "actions": [a for a in (loc.actions or []) if a],
        "examine": loc_examine_text(loc),
        "interactable": loc_is_interactable(loc),
        "debugName": loc.debug_name or "",
        "source": "cache",
    }


def build_loc_manifest(ctx: LocRenderContext) -> dict:
    rows = []
    for loc_id in sorted(ctx.locs):
        loc = ctx.locs[loc_id]
        if not loc.kinds():
            continue
        rows.append(loc_manifest_entry(loc))
    rows.sort(key=lambda e: (e.get("name") or "").lower())
    return {
        "source": "377-cache",
        "note": "Scenery (loc.dat) synthesized on demand - kind model + rotation + recolor.",
        "count": len(rows),
        "locs": rows,
    }


def create_loc_context(
    cache: "CacheReader", anim: "AnimationData | None" = None, *, cache_dir=None
) -> LocRenderContext:
    from src.config import resolve_cache_dir

    bundle = load_config_archive(cache_dir=resolve_cache_dir(cache_dir))
    loc_dat = bundle.read_member("loc.dat")
    loc_idx = bundle.read_member("loc.idx")
    if not loc_dat or not loc_idx:
        raise RuntimeError("loc.dat / loc.idx missing from config archive")
    locs = decode_loc_types(loc_dat, loc_idx)
    return LocRenderContext(cache=cache, locs=locs, palette=build_palette(), anim=anim)
