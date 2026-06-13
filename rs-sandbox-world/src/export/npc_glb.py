"""Build NPC GLB bytes directly from the 377 cache (viewer / API, not Unreal export files)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.export.anim_data import AnimationData
from src.export.animation import compute_seq_morphs, spotanim_posed_vertices
from src.export.gltf_export import build_glb_bytes, build_glb_bytes_multiclip
from src.export.player_glb import _morph_clip
from src.export.mesh_assembly import (
    assemble_npc_triangles,
    merge_models,
    merge_npc_model,
    model_to_triangles,
    npc_recolor_map,
    ordered_model_ids,
)
from src.rs2.model_decoder import decode_model
from src.export.texture_archive import load_texture_images, load_texture_sprites
from src.rs2.palette import build_palette, hsl_to_rgb

if TYPE_CHECKING:
    from src.cache.cache_locator import CacheReader
    from src.cache.npc_index import NPCIndex


@dataclass
class NpcRenderContext:
    cache: "CacheReader"
    index: "NPCIndex"
    anim: AnimationData | None
    palette: list[int]
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


def build_npc_glb_bytes(
    ctx: NpcRenderContext,
    npc_id: int,
    *,
    extra_anims: list[tuple[int, str]] | None = None,
) -> bytes | None:
    """Synthesize one NPC as GLB from cache (idle morphs + RS face alpha)."""
    npc = ctx.index.get(npc_id)
    if npc is None or not npc.model_ids:
        return None

    textures = ctx.ensure_textures()
    texture_sprites = ctx.ensure_texture_sprites()
    recolor = npc_recolor_map(npc)
    frame_deltas = None
    frame_color_deltas = None
    frame_durations = None
    triangles = None
    merged = merge_npc_model(npc, ctx.cache) if ctx.anim else None

    seq = ctx.anim.stand_seq(npc) if ctx.anim else None
    if seq is not None and ctx.anim and merged is not None:
        morphs = compute_seq_morphs(
            merged,
            seq,
            ctx.anim.transforms,
            scale_xy=npc.scale_xy,
            scale_z=npc.scale_z,
        )
        if morphs is not None:
            frame_deltas, frame_color_deltas, frame_durations, export_alphas = morphs
            posed0 = spotanim_posed_vertices(
                merged,
                seq,
                ctx.anim.transforms,
                0,
                scale_xy=npc.scale_xy,
                scale_z=npc.scale_z,
            )
            triangles = model_to_triangles(
                merged,
                ctx.palette,
                recolor=recolor,
                scale_xy=128,
                scale_z=128,
                textures=textures,
                texture_sprites=texture_sprites,
                vertices=posed0,
                face_alphas=export_alphas,
            )

    if extra_anims and ctx.anim and merged is None:
        merged = merge_npc_model(npc, ctx.cache)

    if triangles is None:
        triangles = assemble_npc_triangles(npc, ctx.cache, ctx.palette, textures, texture_sprites)
    if not triangles:
        return None

    clips: list[dict] = []
    if frame_deltas is not None and frame_durations is not None:
        clips.append({
            "frame_deltas": frame_deltas,
            "frame_color_deltas": frame_color_deltas,
            "durations": frame_durations,
            "name": "idle",
            "frame_gap": 1,
            "loop": True,
            "interpolation": "LINEAR",
        })

    if extra_anims and ctx.anim and merged is not None:
        for seq_id, name in extra_anims:
            seq = ctx.anim.seqs.get(seq_id)
            if not seq:
                continue
            clip = _morph_clip(merged, seq, ctx.anim.transforms, name=name)
            if clip is not None:
                clip["loop"] = name == "idle"
                clip["frame_gap"] = 1
                clips.append(clip)

    if len(clips) > 1:
        return build_glb_bytes_multiclip(triangles, textures, smooth=True, clips=clips)
    if clips:
        c0 = clips[0]
        return build_glb_bytes(
            triangles,
            textures,
            smooth=True,
            frame_deltas=c0.get("frame_deltas"),
            frame_color_deltas=c0.get("frame_color_deltas"),
            frame_durations=c0.get("durations"),
            frame_gap=c0.get("frame_gap", 1),
            loop=c0.get("loop", True),
            morph_interpolation=c0.get("interpolation", "LINEAR"),
            anim_name=c0.get("name", "idle"),
        )
    return build_glb_bytes(triangles, textures, smooth=True)


def npc_recolor_pairs_ordered(npc) -> list[tuple[int, int]]:
    """Ordered (src, dst) pairs from the NPC definition (fixes interleaved parse)."""
    recolor = npc_recolor_map(npc)
    if not recolor:
        return []
    src = list(npc.color_src or [])
    dst = list(npc.color_dst or [])
    if len(src) == len(dst) and src:
        flat = src + dst
        pairs: list[tuple[int, int]] = []
        for i in range(0, len(flat), 2):
            if i + 1 < len(flat):
                s = flat[i]
                pairs.append((s, recolor.get(s, flat[i + 1])))
        if pairs:
            return pairs
    return list(recolor.items())


def npc_recolor_pairs(npc) -> list[dict[str, int]]:
    return [{"src": s, "dst": d} for s, d in npc_recolor_pairs_ordered(npc)]


def hsl_rgb_hex(hsl: int, palette: list[int]) -> str:
    r, g, b = hsl_to_rgb(hsl, palette)
    return f"#{r:02x}{g:02x}{b:02x}"


def model_color_slots(model) -> list[int]:
    """Unique recolourable face palette indices on a model (skips textured faces)."""
    slots: set[int] = set()
    for i, color in enumerate(model.face_colors):
        info = model.face_infos[i] if model.face_infos else 0
        if info is not None and (info & 2) == 2:
            continue
        slots.add(color)
    return sorted(slots)


def npc_clone_detail(ctx: NpcRenderContext, npc_id: int) -> dict | None:
    """Per-model parts and recolour slots for the NPC clone editor."""
    npc = ctx.index.get(npc_id)
    if npc is None:
        return None
    palette = ctx.palette
    recolor = npc_recolor_map(npc)
    pairs = npc_recolor_pairs(npc)

    model_parts: list[dict] = []
    for mid in npc.model_ids or []:
        raw = ctx.cache.read_model(mid)
        if raw is None:
            model_parts.append({"id": mid, "missing": True, "slots": []})
            continue
        model = decode_model(mid, raw)
        if model is None:
            model_parts.append({"id": mid, "missing": True, "slots": []})
            continue
        slots = []
        for src in model_color_slots(model):
            dst = recolor.get(src, src)
            slots.append({
                "src": src,
                "dst": dst,
                "srcRgb": hsl_rgb_hex(src, palette),
                "dstRgb": hsl_rgb_hex(dst, palette),
                "recolored": src in recolor,
            })
        model_parts.append({
            "id": mid,
            "missing": False,
            "faceCount": len(model.faces),
            "slots": slots,
        })

    return {
        "id": npc.id,
        "name": npc.name,
        "modelIds": list(npc.model_ids or []),
        "modelParts": model_parts,
        "recolors": [
            {
                "src": p["src"],
                "dst": p["dst"],
                "srcRgb": hsl_rgb_hex(p["src"], palette),
                "dstRgb": hsl_rgb_hex(p["dst"], palette),
            }
            for p in pairs
        ],
        "scaleXY": npc.scale_xy,
        "scaleZ": npc.scale_z,
    }


def model_part_detail(
    ctx: NpcRenderContext,
    model_id: int,
    recolor_overrides: dict[int, int] | None = None,
) -> dict:
    """Colour slots for one model part (NPC override editor)."""
    raw = ctx.cache.read_model(model_id)
    if raw is None:
        return {"id": model_id, "missing": True, "slots": []}
    model = decode_model(model_id, raw)
    if model is None:
        return {"id": model_id, "missing": True, "slots": []}
    recolor = recolor_overrides or {}
    palette = ctx.palette
    slots = []
    for src in model_color_slots(model):
        dst = recolor.get(src, src)
        slots.append({
            "src": src,
            "dst": dst,
            "srcRgb": hsl_rgb_hex(src, palette),
            "dstRgb": hsl_rgb_hex(dst, palette),
            "recolored": src in recolor,
        })
    return {
        "id": model_id,
        "missing": False,
        "faceCount": len(model.faces),
        "slots": slots,
    }


def build_model_glb_bytes(
    ctx: NpcRenderContext,
    model_id: int,
    *,
    recolor: dict[int, int] | None = None,
) -> bytes | None:
    raw = ctx.cache.read_model(model_id)
    if raw is None:
        return None
    model = decode_model(model_id, raw)
    if model is None:
        return None
    textures = ctx.ensure_textures()
    texture_sprites = ctx.ensure_texture_sprites()
    triangles = model_to_triangles(
        model, ctx.palette, recolor=recolor or {}, textures=textures,
        texture_sprites=texture_sprites,
    )
    if not triangles:
        return None
    return build_glb_bytes(triangles, textures, smooth=True)


def assemble_custom_npc_triangles(
    cache,
    palette: list[int],
    model_ids: list[int],
    recolor: dict[int, int],
    *,
    scale_xy: int = 128,
    scale_z: int = 128,
    textures: dict[int, object] | None = None,
    texture_sprites=None,
) -> list:
    triangles = []
    model_layer = 0
    for model_id in model_ids:
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
                scale_xy=scale_xy,
                scale_z=scale_z,
                textures=textures,
                texture_sprites=texture_sprites,
                model_layer=model_layer,
            )
        )
        model_layer += 1
    return triangles


def build_npc_custom_glb_bytes(
    ctx: NpcRenderContext,
    base_id: int,
    *,
    model_ids: list[int] | None = None,
    recolor_overrides: dict[int, int] | None = None,
    extra_model_ids: list[int] | None = None,
    extra_anims: list[tuple[int, str]] | None = None,
) -> bytes | None:
    """Clone an NPC with optional model list / recolour overrides."""
    npc = ctx.index.get(base_id)
    if npc is None:
        return None
    mids = ordered_model_ids(
        model_ids if model_ids is not None else (npc.model_ids or []),
        extra_model_ids,
    )
    if not mids:
        return None

    stock_mids = list(npc.model_ids or [])
    # Walk/attack/death morphs assume the stock model layout; stand idle is safe on
    # any merged layout where compute_seq_morphs succeeds (custom queens, etc.).
    # Trailing add-ons only (e.g. wizard staff) keep the stock prefix for combat anims.
    morph_anims_compatible = (
        mids == stock_mids
        or (
            len(mids) >= len(stock_mids)
            and mids[: len(stock_mids)] == stock_mids
        )
    )

    recolor = npc_recolor_map(npc)
    if recolor_overrides:
        recolor.update({int(k): int(v) for k, v in recolor_overrides.items()})

    textures = ctx.ensure_textures()
    texture_sprites = ctx.ensure_texture_sprites()
    frame_deltas = None
    frame_color_deltas = None
    frame_durations = None
    triangles = None
    merged = None
    seq = None
    if ctx.anim:
        merged = merge_models(mids, ctx.cache)
        seq = ctx.anim.stand_seq(npc)
    if seq is not None and ctx.anim and merged is not None:
        morphs = compute_seq_morphs(
            merged,
            seq,
            ctx.anim.transforms,
            scale_xy=npc.scale_xy,
            scale_z=npc.scale_z,
        )
        if morphs is not None:
            frame_deltas, frame_color_deltas, frame_durations, export_alphas = morphs
            posed0 = spotanim_posed_vertices(
                merged,
                seq,
                ctx.anim.transforms,
                0,
                scale_xy=npc.scale_xy,
                scale_z=npc.scale_z,
            )
            triangles = model_to_triangles(
                merged,
                ctx.palette,
                recolor=recolor,
                scale_xy=128,
                scale_z=128,
                textures=textures,
                texture_sprites=texture_sprites,
                vertices=posed0,
                face_alphas=export_alphas,
            )

    if triangles is None:
        triangles = assemble_custom_npc_triangles(
            ctx.cache,
            ctx.palette,
            mids,
            recolor,
            scale_xy=npc.scale_xy,
            scale_z=npc.scale_z,
            textures=textures,
            texture_sprites=texture_sprites,
        )
    if not triangles:
        return None

    clips: list[dict] = []
    if frame_deltas is not None and frame_durations is not None:
        clips.append({
            "frame_deltas": frame_deltas,
            "frame_color_deltas": frame_color_deltas,
            "durations": frame_durations,
            "name": "idle",
            "frame_gap": 1,
            "loop": True,
            "interpolation": "LINEAR",
        })

    if extra_anims and ctx.anim and morph_anims_compatible:
        if merged is None:
            merged = merge_models(mids, ctx.cache)
        for seq_id, name in extra_anims:
            seq = ctx.anim.seqs.get(seq_id)
            if not seq:
                continue
            clip = _morph_clip(merged, seq, ctx.anim.transforms, name=name)
            if clip is not None:
                clip["loop"] = name == "idle"
                clip["frame_gap"] = 1
                clips.append(clip)

    if len(clips) > 1:
        return build_glb_bytes_multiclip(triangles, textures, smooth=True, clips=clips)
    if clips:
        c0 = clips[0]
        return build_glb_bytes(
            triangles,
            textures,
            smooth=True,
            frame_deltas=c0.get("frame_deltas"),
            frame_color_deltas=c0.get("frame_color_deltas"),
            frame_durations=c0.get("durations"),
            frame_gap=c0.get("frame_gap", 1),
            loop=c0.get("loop", True),
            morph_interpolation=c0.get("interpolation", "LINEAR"),
            anim_name=c0.get("name", "idle"),
        )
    return build_glb_bytes(triangles, textures, smooth=True)


def npc_manifest_entry(npc, anim: AnimationData | None) -> dict:
    """Lightweight NPC row for the viewer list (no disk export)."""
    entry: dict = {
        "id": npc.id,
        "name": npc.name,
        "file": f"/api/npc/{npc.id}.glb",
        "modelIds": list(npc.model_ids or []),
        "recolors": npc_recolor_pairs(npc),
        "scaleXY": npc.scale_xy,
        "scaleZ": npc.scale_z,
        "source": "cache",
    }
    if anim:
        seq = anim.stand_seq(npc)
        if seq and seq.frame_count > 1:
            entry["animated"] = True
            entry["animFrames"] = seq.frame_count
    return entry


def build_npc_manifest(ctx: NpcRenderContext) -> dict:
    npcs = []
    for i in range(ctx.index.count):
        npc = ctx.index.get(i)
        if npc is None or not npc.model_ids:
            continue
        npcs.append(npc_manifest_entry(npc, ctx.anim))
    npcs.sort(key=lambda e: (e.get("name") or "").lower())
    return {
        "source": "377-cache",
        "audioSource": "cache-synth",
        "note": "Models synthesized on demand from cache. Not unreal_exports.",
        "count": len(npcs),
        "npcs": npcs,
    }


def create_render_context(cache: "CacheReader", index: "NPCIndex", anim: AnimationData | None) -> NpcRenderContext:
    return NpcRenderContext(
        cache=cache,
        index=index,
        anim=anim,
        palette=build_palette(),
    )
