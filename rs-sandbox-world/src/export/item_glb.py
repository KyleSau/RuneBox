"""Build item/object GLB bytes from obj.dat (ports ObjType.getModel)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.cache.item_index import ItemIndex
from src.export.gltf_export import build_glb_bytes
from src.export.mesh_assembly import model_to_triangles
from src.export.texture_archive import load_texture_images
from src.rs2.model_decoder import decode_model
from src.rs2.palette import build_palette

if TYPE_CHECKING:
    from src.cache.cache_locator import CacheReader


def item_recolor_map(item) -> dict[int, int]:
    if item.src_color and item.dst_color:
        return dict(zip(item.src_color, item.dst_color))
    return {}


@dataclass
class ObjectRenderContext:
    cache: "CacheReader"
    items: ItemIndex
    palette: list[int]
    textures: dict[int, object] | None = None
    _textures_loaded: bool = False

    def ensure_textures(self) -> dict[int, object]:
        if not self._textures_loaded:
            self.textures = load_texture_images(self.cache)
            self._textures_loaded = True
        return self.textures or {}


def build_object_glb_bytes(ctx: ObjectRenderContext, item_id: int) -> bytes | None:
    """Synthesize one inventory/ground object model as GLB."""
    item = ctx.items.get(item_id)
    if item is None or item.model_id <= 0:
        return None

    raw = ctx.cache.read_model(item.model_id)
    if raw is None:
        return None
    model = decode_model(item.model_id, raw)
    if model is None or not model.faces:
        return None

    triangles = model_to_triangles(
        model,
        ctx.palette,
        recolor=item_recolor_map(item),
        scale_xy=item.scale_x,
        scale_z=item.scale_y,
        textures=ctx.ensure_textures(),
    )
    if not triangles:
        return None

    return build_glb_bytes(triangles, ctx.ensure_textures(), smooth=True)


def object_manifest_entry(item) -> dict:
    worn = item.worn_model_ids()
    return {
        "id": item.id,
        "name": item.name or f"object_{item.id}",
        "file": f"/api/object/{item.id}.glb",
        "modelId": item.model_id,
        "wornModelIds": worn or None,
        "hasWornModels": bool(worn),
        "source": "cache",
    }


def item_detail_entry(item) -> dict:
    """Full item detail for equip / NPC override tooling."""
    entry = item.to_dict()
    entry["id"] = item.id
    entry["file"] = f"/api/item/{item.id}.glb"
    entry["detailUrl"] = f"/api/item/{item.id}.json"
    return entry


def search_items(ctx: ObjectRenderContext, query: str, *, limit: int = 30) -> list[dict]:
    """Name/id search for equippable items (worn models preferred in sort)."""
    q = (query or "").strip().lower()
    if not q:
        return []
    limit = max(1, min(limit, 100))
    scored: list[tuple[int, int, dict]] = []
    id_query: int | None = None
    if q.isdigit():
        id_query = int(q)

    for item_id in range(ctx.items.count):
        item = ctx.items.get(item_id)
        if item is None or not item.name:
            continue
        name_l = item.name.lower()
        worn = item.worn_model_ids()
        if id_query is not None:
            if item_id != id_query and q not in name_l:
                continue
            rank = 0 if item_id == id_query else 1
        elif q not in name_l:
            continue
        else:
            rank = 0 if name_l.startswith(q) else (1 if name_l.split()[0].startswith(q) else 2)
        scored.append((rank, item_id, item_detail_entry(item)))

    scored.sort(key=lambda t: (t[0], (t[2].get("name") or "").lower(), t[1]))
    return [entry for _, _, entry in scored[:limit]]


def build_object_manifest(ctx: ObjectRenderContext) -> dict:
    rows = []
    for item_id in range(ctx.items.count):
        item = ctx.items.get(item_id)
        if item is None or item.model_id <= 0:
            continue
        rows.append(object_manifest_entry(item))
    rows.sort(key=lambda e: (e.get("name") or "").lower())
    return {
        "source": "377-cache",
        "note": "Objects (obj.dat items) synthesized on demand — ground model + recolor.",
        "count": len(rows),
        "objects": rows,
    }


def create_object_context(cache: "CacheReader", *, cache_dir=None) -> ObjectRenderContext:
    from src.config import resolve_cache_dir

    return ObjectRenderContext(
        cache=cache,
        items=ItemIndex.from_cache(cache_dir=resolve_cache_dir(cache_dir)),
        palette=build_palette(),
    )
