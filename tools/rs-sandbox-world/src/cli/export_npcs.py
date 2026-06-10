"""Batch-export RS NPC models to GLB + textures + a manifest for Unreal.

Examples:
    python -m src.cli.export_npcs --search goblin
    python -m src.cli.export_npcs --ids 1,2,3 --out exports
    python -m src.cli.export_npcs --all --limit 200
"""

from __future__ import annotations

import argparse
import json
import re
import struct
import sys
from pathlib import Path

from src.cache.cache_locator import CacheReader
from src.cache.config_locator import ConfigNotFoundError
from src.cache.npc_index import NPCIndex
from src.config import DEFAULT_CACHE_DIR, resolve_cache_dir
from src.export.anim_data import load_animation_data
from src.export.animation import compute_seq_morphs, spotanim_posed_vertices
from src.export.gltf_export import export_glb
from src.export.mesh_assembly import (
    assemble_npc_triangles,
    merge_npc_model,
    model_to_triangles,
    npc_recolor_map,
)
from src.export.texture_archive import load_texture_images
from src.rs2.palette import build_palette

_SLUG_RE = re.compile(r"[^a-z0-9]+")
_GLB_NAME_RE = re.compile(r"^(\d+)_(.+)\.glb$", re.IGNORECASE)


def _slug(name: str | None) -> str:
    if not name:
        return "unnamed"
    slug = _SLUG_RE.sub("_", name.lower()).strip("_")
    return slug or "unnamed"


def _glb_summary(path: Path) -> tuple[int, bool, int]:
    """Return (triangle_count, animated, anim_frame_count) from an exported GLB."""
    data = path.read_bytes()
    if len(data) < 20 or data[:4] != b"glTF":
        return 0, False, 0
    jlen = struct.unpack_from("<I", data, 12)[0]
    gltf = json.loads(data[20 : 20 + jlen])
    tris = 0
    meshes = gltf.get("meshes") or []
    accessors = gltf.get("accessors") or []
    if meshes:
        for prim in meshes[0].get("primitives") or []:
            idx = prim.get("indices")
            if idx is not None and idx < len(accessors):
                tris += accessors[idx]["count"] // 3
    frames = 0
    if meshes and meshes[0].get("weights"):
        frames = len(meshes[0]["weights"])
    animated = bool(gltf.get("animations")) or frames > 1
    return tris, animated, frames


def rebuild_manifest(out_root: Path, index: NPCIndex, cache_dir: Path) -> int:
    """Rebuild manifest.json from GLB files already on disk (fast, no re-export)."""
    npc_dir = out_root / "npcs"
    if not npc_dir.is_dir():
        print(f"No npcs folder at {npc_dir}", file=sys.stderr)
        return 1

    tex_dir = out_root / "textures"
    saved_textures = sorted(p.name for p in tex_dir.glob("*.png")) if tex_dir.is_dir() else []

    entries = []
    skipped = 0
    for path in sorted(npc_dir.glob("*.glb")):
        match = _GLB_NAME_RE.match(path.name)
        if not match:
            skipped += 1
            continue
        npc_id = int(match.group(1))
        npc = index.get(npc_id)
        if npc is None:
            skipped += 1
            continue
        tris, animated, anim_frames = _glb_summary(path)
        recolors = None
        if npc.color_src and npc.color_dst:
            recolors = [{"src": s, "dst": d} for s, d in zip(npc.color_src, npc.color_dst)]
        entries.append(
            {
                "id": npc.id,
                "name": npc.name,
                "file": f"npcs/{path.name}",
                "modelIds": npc.model_ids,
                "scaleXY": npc.scale_xy,
                "scaleZ": npc.scale_z,
                "recolors": recolors,
                "standAnimation": npc.seq_stand_id,
                "walkAnimation": npc.seq_walk_id,
                "triangleCount": tris,
                "textured": False,
                "animated": animated,
                "animFrames": anim_frames if animated else 0,
            }
        )

    manifest = {
        "source": str(index.source),
        "cache": str(cache_dir),
        "textures": saved_textures,
        "npcs": entries,
    }
    manifest_path = out_root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Wrote manifest with {len(entries)} NPC(s) to {manifest_path}")
    if skipped:
        print(f"  skipped {skipped} file(s) (unknown id or filename)")
    return 0


def _select_npcs(index: NPCIndex, args) -> list:
    if args.ids:
        ids = [int(x) for x in args.ids.split(",") if x.strip()]
        selected = [index.get(i) for i in ids]
        return [npc for npc in selected if npc is not None]
    if args.search:
        return index.search(args.search)
    # --all
    npcs = [index.get(i) for i in range(index.count)]
    return [npc for npc in npcs if npc is not None and npc.model_ids]


def _save_textures(textures: dict[int, object], out_dir: Path) -> list[str]:
    if not textures:
        return []
    out_dir.mkdir(parents=True, exist_ok=True)
    saved = []
    for texture_id, image in sorted(textures.items()):
        path = out_dir / f"tex_{texture_id}.png"
        try:
            image.save(path)
            saved.append(path.name)
        except Exception:
            continue
    return saved


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export RS NPC models to GLB for Unreal.")
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE_DIR, help="Cache directory")
    parser.add_argument("--out", type=Path, default=Path("exports"), help="Output root directory")
    parser.add_argument(
        "--rebuild-manifest",
        action="store_true",
        help="Rebuild manifest.json from existing GLB files (no re-export)",
    )
    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument("--ids", type=str, help="Comma-separated NPC ids")
    group.add_argument("--search", type=str, help="Case-insensitive name search")
    group.add_argument("--all", action="store_true", help="Export every NPC with models")
    parser.add_argument("--limit", type=int, default=0, help="Cap number of NPCs exported (0 = no cap)")
    parser.add_argument("--no-textures", action="store_true", help="Skip texture decode")
    parser.add_argument(
        "--flat-normals",
        action="store_true",
        help="Export faceted flat normals instead of smoothed (gouraud-style) normals",
    )
    parser.add_argument(
        "--no-anim",
        action="store_true",
        help="Skip baking the NPC idle (stand) animation as glTF morph targets",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="With --all: skip NPCs whose GLB file already exists (then rebuild manifest)",
    )
    args = parser.parse_args(argv)

    cache_dir = resolve_cache_dir(args.cache)

    try:
        index = NPCIndex.from_cache(cache_dir=cache_dir)
    except ConfigNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if args.rebuild_manifest:
        return rebuild_manifest(args.out, index, cache_dir)

    if not args.ids and not args.search and not args.all:
        parser.error("one of --ids, --search, --all, or --rebuild-manifest is required")

    cache = CacheReader(cache_dir)

    print(f"Loaded {index.count} NPC definitions from {index.source}")

    npcs = _select_npcs(index, args)
    if args.limit > 0:
        npcs = npcs[: args.limit]
    if not npcs:
        print("No matching NPCs to export.", file=sys.stderr)
        return 1

    out_root = args.out
    npc_dir = out_root / "npcs"
    tex_dir = out_root / "textures"
    npc_dir.mkdir(parents=True, exist_ok=True)

    palette = build_palette()
    textures: dict[int, object] = {}
    if not args.no_textures:
        textures = load_texture_images(cache)
        print(f"Decoded {len(textures)} texture sprites")
    saved_textures = _save_textures(textures, tex_dir)

    anim = None
    if not args.no_anim:
        print("Loading animation data (sequences + frame transforms)...")
        anim = load_animation_data(cache)
        if anim is None:
            print("  no animation data found; exporting static models")
        else:
            print(f"  {len(anim.seqs)} sequences, {len(anim.transforms)} frame transforms")

    manifest = {
        "source": str(index.source),
        "cache": str(cache_dir),
        "textures": saved_textures,
        "npcs": [],
    }

    exported = 0
    for npc in npcs:
        frame_deltas = None
        frame_color_deltas = None
        frame_durations = None
        triangles = None

        seq = anim.stand_seq(npc) if anim else None
        if seq is not None:
            merged = merge_npc_model(npc, cache)
            if merged is not None:
                morphs = compute_seq_morphs(
                    merged,
                    seq,
                    anim.transforms,
                    scale_xy=npc.scale_xy,
                    scale_z=npc.scale_z,
                )
                if morphs is not None:
                    frame_deltas, frame_color_deltas, frame_durations, export_alphas = morphs
                    posed0 = spotanim_posed_vertices(
                        merged,
                        seq,
                        anim.transforms,
                        0,
                        scale_xy=npc.scale_xy,
                        scale_z=npc.scale_z,
                    )
                    triangles = model_to_triangles(
                        merged,
                        palette,
                        recolor=npc_recolor_map(npc),
                        scale_xy=128,
                        scale_z=128,
                        textures=textures,
                        vertices=posed0,
                        face_alphas=export_alphas,
                    )

        if triangles is None:
            triangles = assemble_npc_triangles(npc, cache, palette, textures)
        if not triangles:
            print(f"  skip NPC {npc.id} ({npc.name}): no geometry")
            continue

        filename = f"{npc.id}_{_slug(npc.name)}.glb"
        path = npc_dir / filename
        if args.skip_existing and path.is_file():
            tris, animated, anim_frames = _glb_summary(path)
            textured = False
            recolors = None
            if npc.color_src and npc.color_dst:
                recolors = [{"src": s, "dst": d} for s, d in zip(npc.color_src, npc.color_dst)]
            manifest["npcs"].append(
                {
                    "id": npc.id,
                    "name": npc.name,
                    "file": f"npcs/{filename}",
                    "modelIds": npc.model_ids,
                    "scaleXY": npc.scale_xy,
                    "scaleZ": npc.scale_z,
                    "recolors": recolors,
                    "standAnimation": npc.seq_stand_id,
                    "walkAnimation": npc.seq_walk_id,
                    "triangleCount": tris,
                    "textured": textured,
                    "animated": animated,
                    "animFrames": anim_frames if animated else 0,
                }
            )
            exported += 1
            continue
        if not export_glb(
            triangles,
            path,
            textures,
            smooth=not args.flat_normals,
            frame_deltas=frame_deltas,
            frame_color_deltas=frame_color_deltas,
            frame_durations=frame_durations,
            frame_gap=1,
            loop=True,
            morph_interpolation="LINEAR",
            anim_name="idle",
        ):
            print(f"  skip NPC {npc.id} ({npc.name}): export produced nothing")
            continue
        animated = frame_deltas is not None

        textured = any(t.texture_id is not None for t in triangles)
        recolors = None
        if npc.color_src and npc.color_dst:
            recolors = [{"src": s, "dst": d} for s, d in zip(npc.color_src, npc.color_dst)]

        manifest["npcs"].append(
            {
                "id": npc.id,
                "name": npc.name,
                "file": f"npcs/{filename}",
                "modelIds": npc.model_ids,
                "scaleXY": npc.scale_xy,
                "scaleZ": npc.scale_z,
                "recolors": recolors,
                "standAnimation": npc.seq_stand_id,
                "walkAnimation": npc.seq_walk_id,
                "triangleCount": len(triangles),
                "textured": textured,
                "animated": animated,
                "animFrames": len(frame_durations) if frame_durations else 0,
            }
        )
        exported += 1
        anim_note = f", idle {len(frame_durations)}f" if animated else ""
        print(
            f"  wrote {path} ({len(triangles)} tris"
            f"{', textured' if textured else ''}{anim_note})"
        )

    manifest_path = out_root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"\nExported {exported} NPC model(s) to {npc_dir}")
    print(f"Manifest: {manifest_path} ({len(manifest['npcs'])} entries)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
