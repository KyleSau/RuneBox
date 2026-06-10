"""Build spotanim (GFX) GLB bytes from the 377 cache."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.cache.config_locator import DEFAULT_CONFIG_ARCHIVE_ID
from src.cache.file_archive import FileArchive
from src.export.anim_data import AnimationData
from src.export.animation import compute_spotanim_morphs, spotanim_posed_vertices
from src.export.gltf_export import build_glb_bytes
from src.export.mesh_assembly import model_to_triangles
from src.export.texture_archive import load_texture_images
from src.rs2.model_decoder import decode_model
from src.rs2.palette import build_palette
from src.rs2.spotanim_decoder import decode_spotanim_types, spotanim_recolor_map

if TYPE_CHECKING:
    from src.cache.cache_locator import CacheReader


@dataclass
class GfxRenderContext:
    cache: "CacheReader"
    anim: AnimationData | None
    spotanims: dict
    palette: list[int]
    textures: dict[int, object] | None = None
    _textures_loaded: bool = False

    def ensure_textures(self) -> dict[int, object]:
        if not self._textures_loaded:
            self.textures = load_texture_images(self.cache)
            self._textures_loaded = True
        return self.textures or {}


def load_spotanim_types(cache: "CacheReader") -> dict:
    raw = cache.read_archive(DEFAULT_CONFIG_ARCHIVE_ID)
    if raw is None:
        return {}
    arch = FileArchive.load(raw)
    data = arch.read("spotanim.dat")
    if not data:
        return {}
    return decode_spotanim_types(data)


def build_spotanim_glb_bytes(ctx: GfxRenderContext, spot_id: int) -> bytes | None:
    """Synthesize one spotanim as GLB (model + seq + scale/rotation like the client)."""
    entry = ctx.spotanims.get(spot_id)
    if entry is None or entry.model_id <= 0:
        return None

    raw = ctx.cache.read_model(entry.model_id)
    if raw is None:
        return None
    model = decode_model(entry.model_id, raw)
    if model is None or not model.faces:
        return None

    textures = ctx.ensure_textures()
    recolor = spotanim_recolor_map(entry)
    seq = None
    if ctx.anim and entry.seq_id >= 0:
        seq = ctx.anim.seqs.get(entry.seq_id)

    frame_deltas = None
    frame_color_deltas = None
    frame_durations = None
    export_alphas = None
    if seq is not None and ctx.anim:
        morphs = compute_spotanim_morphs(
            model,
            seq,
            ctx.anim.transforms,
            scale_xy=entry.scale_xy,
            scale_z=entry.scale_z,
            rotation=entry.rotation,
        )
        if morphs is not None:
            frame_deltas, frame_color_deltas, frame_durations, export_alphas = morphs

    posed0 = None
    if seq is not None and ctx.anim:
        posed0 = spotanim_posed_vertices(
            model,
            seq,
            ctx.anim.transforms,
            0,
            scale_xy=entry.scale_xy,
            scale_z=entry.scale_z,
            rotation=entry.rotation,
        )

    # Posed vertices are already scaled/rotated like SpotAnimEntity.getModel().
    scale_xy = 128 if posed0 is not None else entry.scale_xy
    scale_z = 128 if posed0 is not None else entry.scale_z
    triangles = model_to_triangles(
        model,
        ctx.palette,
        recolor=recolor,
        scale_xy=scale_xy,
        scale_z=scale_z,
        textures=textures,
        vertices=posed0,
        face_alphas=export_alphas,
    )
    if not triangles:
        return None

    return build_glb_bytes(
        triangles,
        textures,
        smooth=True,
        frame_deltas=frame_deltas,
        frame_color_deltas=frame_color_deltas,
        frame_durations=frame_durations,
        frame_gap=1,
        loop=False,
        morph_interpolation="LINEAR",
        anim_name="spotanim",
    )


def spotanim_manifest_entry(entry, anim: AnimationData | None) -> dict:
    row: dict = {
        "id": entry.id,
        "name": f"spotanim_{entry.id}",
        "file": f"/api/spotanim/{entry.id}.glb",
        "modelId": entry.model_id,
        "seqId": entry.seq_id,
        "scaleXY": entry.scale_xy,
        "scaleZ": entry.scale_z,
        "rotation": entry.rotation,
        "source": "cache",
    }
    if anim and entry.seq_id >= 0:
        seq = anim.seqs.get(entry.seq_id)
        if seq and seq.frame_count > 1:
            row["animated"] = True
            row["animFrames"] = seq.frame_count
    return row


def build_spotanim_manifest(ctx: GfxRenderContext) -> dict:
    rows = []
    for sid in sorted(ctx.spotanims):
        entry = ctx.spotanims[sid]
        if entry.model_id <= 0:
            continue
        rows.append(spotanim_manifest_entry(entry, ctx.anim))
    return {
        "source": "377-cache",
        "note": "Spotanims (GFX) synthesized on demand from spotanim.dat + models + seq.dat.",
        "count": len(rows),
        "spotanims": rows,
    }


def create_gfx_context(cache: "CacheReader", anim: AnimationData | None) -> GfxRenderContext:
    return GfxRenderContext(
        cache=cache,
        anim=anim,
        spotanims=load_spotanim_types(cache),
        palette=build_palette(),
    )
