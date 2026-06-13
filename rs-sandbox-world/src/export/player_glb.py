"""Assemble a Player GLB from identity kits (idk.dat) + the 377 cache.

A player is 7 static body-part models merged into one labelled model, recoloured
by the design colours, then animated with two baked morph clips (``stand`` and
``walk``) that share one union morph-target set. No equipment / head models.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from src.cache.config_locator import load_config_archive
from src.export.anim_data import AnimationData
from src.export.animation import (
    _scale_int,
    _y_up,
    build_seq_durations,
    spotanim_posed_vertices,
)
from src.export.gltf_export import build_glb_bytes_multiclip
from src.export.mesh_assembly import Triangle, merge_models, model_to_triangles, ordered_model_ids
from src.export.player_design import (
    DEFAULT_SEQ_RUN,
    DEFAULT_SEQ_STAND,
    DEFAULT_SEQ_TURN,
    DEFAULT_SEQ_TURN_AROUND,
    DEFAULT_SEQ_TURN_LEFT,
    DEFAULT_SEQ_TURN_RIGHT,
    DEFAULT_SEQ_WALK,
    DESIGN_PART_COLOR,
    KIT_PARTS,
    default_kits,
    design_recolor,
    kit_model_ids,
)

# Locomotion clips loop while the matching movement state persists (Game.updateMovement).
PLAYER_LOCOMOTION = (
    "stand",
    "turn",
    "walk",
    "turn_around",
    "turn_left",
    "turn_right",
    "run",
)
from src.export.texture_archive import load_texture_images
from src.rs2.idk_decoder import decode_idk_types, idk_recolor_map
from src.rs2.palette import build_palette

if TYPE_CHECKING:
    from src.cache.cache_locator import CacheReader


@dataclass
class PlayerRenderContext:
    cache: "CacheReader"
    idks: list
    anim: AnimationData | None
    palette: list[int]
    stand_seq: int = DEFAULT_SEQ_STAND
    walk_seq: int = DEFAULT_SEQ_WALK
    run_seq: int = DEFAULT_SEQ_RUN
    textures: dict[int, object] | None = None
    _textures_loaded: bool = False

    def ensure_textures(self) -> dict[int, object]:
        if not self._textures_loaded:
            self.textures = load_texture_images(self.cache)
            self._textures_loaded = True
        return self.textures or {}


def _normalize_feet_y(triangles: list[Triangle]) -> None:
    """Shift model so the lowest vertex sits on y=0 (feet on ground)."""
    min_y = min(v[1] for tri in triangles for v in (tri.v0, tri.v1, tri.v2))
    if abs(min_y) < 1e-4:
        return
    for tri in triangles:
        tri.v0 = (tri.v0[0], tri.v0[1] - min_y, tri.v0[2])
        tri.v1 = (tri.v1[0], tri.v1[1] - min_y, tri.v1[2])
        tri.v2 = (tri.v2[0], tri.v2[1] - min_y, tri.v2[2])


def _resolve_kits(idks, gender: int, kit_indices) -> list[int]:
    male = gender == 0
    defaults = default_kits(idks, male)
    if not kit_indices:
        return defaults
    resolved = list(defaults)
    for part in range(KIT_PARTS):
        if part < len(kit_indices):
            value = kit_indices[part]
            if value is not None and value >= 0 and value < len(idks):
                resolved[part] = value
    return resolved


def _morph_clip(model, seq, transforms, *, name: str) -> dict | None:
    """Position morph deltas (relative to the unposed bind pose) for one seq."""
    if seq is None or seq.frame_count <= 1 or not model.vertex_skins:
        return None
    bind = _y_up(_scale_int(model.vertices, 128, 128))
    deltas: list[np.ndarray] = []
    any_motion = False
    for fi in range(seq.frame_count):
        posed = _y_up(spotanim_posed_vertices(model, seq, transforms, fi, scale_xy=128, scale_z=128))
        delta = posed - bind
        if np.abs(delta).max() > 0.01:
            any_motion = True
        deltas.append(delta)
    if not any_motion:
        return None
    return {
        "frame_deltas": deltas,
        "durations": build_seq_durations(seq, transforms),
        "name": name,
        "frame_gap": 0,
        "loop": True,
        "interpolation": "LINEAR",
    }


# Combat animation seqs baked into the player when ``combat=1`` is requested.
# Ports Elvarg cast/attack animation ids (CombatSpells / RangedCombatMethod).
COMBAT_ANIMS: list[tuple[int, str]] = [
    (727, "cast_fire_wave"),
    (711, "cast_fire_blast"),
    (1979, "cast_ice_barrage"),
    (1978, "cast_ice_blitz"),
    (426, "shoot_bow"),
    (427, "shoot_crossbow"),
]

# Emote tab sequences (Elvarg Emotes.java) — loop while standing in the rave zone.
EMOTE_ANIMS: list[tuple[int, str]] = [
    (866, "dance"),
    (2106, "jig"),
    (2108, "headbang"),
]


def build_player_glb_bytes(
    ctx: PlayerRenderContext, *, gender: int = 0, kit_indices=None, colors=None,
    extra_anims: list[tuple[int, str]] | None = None,
    extra_model_ids: list[int] | None = None,
) -> bytes | None:
    colors = list(colors or [0, 0, 0, 0, 0])
    kits = _resolve_kits(ctx.idks, gender, kit_indices)
    model_ids = ordered_model_ids(kit_model_ids(ctx.idks, kits), extra_model_ids)
    if not model_ids:
        return None

    model = merge_models(model_ids, ctx.cache)
    if model is None or not model.faces:
        return None

    recolor = design_recolor(ctx.idks, kits, colors)
    textures = ctx.ensure_textures()

    triangles = model_to_triangles(
        model,
        ctx.palette,
        recolor=recolor,
        scale_xy=128,
        scale_z=128,
        textures=textures,
        vertices=[list(v) for v in model.vertices],
    )
    if not triangles:
        return None

    _normalize_feet_y(triangles)

    clips: list[dict] = []
    if ctx.anim is not None:
        transforms = ctx.anim.transforms
        anim_specs = [
            (ctx.stand_seq, "stand"),
            (DEFAULT_SEQ_TURN, "turn"),
            (ctx.walk_seq, "walk"),
            (DEFAULT_SEQ_TURN_AROUND, "turn_around"),
            (DEFAULT_SEQ_TURN_LEFT, "turn_left"),
            (DEFAULT_SEQ_TURN_RIGHT, "turn_right"),
            (ctx.run_seq, "run"),
        ]
        emote_names = {n for _, n in EMOTE_ANIMS}
        if extra_anims:
            anim_specs.extend(extra_anims)
        locomotion = PLAYER_LOCOMOTION
        for seq_id, name in anim_specs:
            seq = ctx.anim.seqs.get(seq_id)
            clip = _morph_clip(model, seq, transforms, name=name) if seq else None
            if clip is not None:
                # Cast/attack clips play once; locomotion + emotes loop.
                if name not in locomotion and name not in emote_names:
                    clip["loop"] = False
                clips.append(clip)

    if clips:
        return build_glb_bytes_multiclip(triangles, textures, smooth=True, clips=clips)
    return build_glb_bytes(triangles, textures, smooth=True)


def build_kit_preview_glb_bytes(ctx: PlayerRenderContext, kit_id: int) -> bytes | None:
    """Preview a single identity-kit entry (e.g. browse head models)."""
    if kit_id < 0 or kit_id >= len(ctx.idks):
        return None
    idk = ctx.idks[kit_id]
    if not idk.model_ids:
        return None
    model = merge_models(list(idk.model_ids), ctx.cache)
    if model is None or not model.faces:
        return None
    textures = ctx.ensure_textures()
    recolor = idk_recolor_map(idk)
    triangles = model_to_triangles(
        model, ctx.palette, recolor=recolor, scale_xy=128, scale_z=128,
        textures=textures, vertices=[list(v) for v in model.vertices],
    )
    if not triangles:
        return None
    return build_glb_bytes(triangles, textures, smooth=True)


def build_idk_kits_manifest(ctx: PlayerRenderContext) -> dict:
    """Searchable catalog of all identity-kit body parts (heads, torsos, …)."""
    part_names = ["head", "jaw", "torso", "arms", "hands", "legs", "feet"]
    kits: list[dict] = []
    for idk in ctx.idks:
        if not idk.model_ids:
            continue
        if idk.type >= 7:
            gender = "female"
            slot = idk.type - 7
        elif idk.type >= 0:
            gender = "male"
            slot = idk.type
        else:
            gender = "unknown"
            slot = -1
        part = part_names[slot] if 0 <= slot < len(part_names) else f"type_{idk.type}"
        kits.append({
            "id": idk.id,
            "part": part,
            "gender": gender,
            "type": idk.type,
            "selectable": idk.selectable,
            "modelIds": list(idk.model_ids),
            "headModelIds": [h for h in idk.head_model_ids if h is not None and h >= 0],
        })
    return {
        "source": "377-cache",
        "note": "Identity kit (idk.dat) parts for custom NPC / character assembly.",
        "partNames": part_names,
        "count": len(kits),
        "kits": kits,
    }


def build_idk_manifest(ctx: PlayerRenderContext) -> dict:
    """Selectable kit options per body part per gender, plus colour counts."""

    def options_for(gender: int) -> list[list[int]]:
        offset = 0 if gender == 0 else 7
        parts: list[list[int]] = []
        for part in range(KIT_PARTS):
            choices = [
                idk.id
                for idk in ctx.idks
                if not idk.selectable and idk.type == (part + offset) and idk.model_ids
            ]
            parts.append(choices)
        return parts

    return {
        "source": "377-cache",
        "note": "Identity kit (idk.dat) body-part options for player customization.",
        "parts": KIT_PARTS,
        "partNames": ["head", "jaw", "torso", "arms", "hands", "legs", "feet"],
        "colorNames": ["hair", "torso", "legs", "feet", "skin"],
        "colorCounts": [len(DESIGN_PART_COLOR[p]) for p in range(5)],
        "male": {"kits": options_for(0), "defaults": default_kits(ctx.idks, True)},
        "female": {"kits": options_for(1), "defaults": default_kits(ctx.idks, False)},
    }


def create_player_context(cache: "CacheReader", anim: AnimationData | None, *, cache_dir=None) -> PlayerRenderContext:
    from src.config import resolve_cache_dir

    bundle = load_config_archive(cache_dir=resolve_cache_dir(cache_dir))
    idk_dat = bundle.read_member("idk.dat")
    if not idk_dat:
        raise RuntimeError("idk.dat missing from config archive")
    idks = decode_idk_types(idk_dat)
    return PlayerRenderContext(cache=cache, idks=idks, anim=anim, palette=build_palette())
