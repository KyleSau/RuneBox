"""RS cache -> glTF/GLB export for Unreal Engine.

Static geometry only (no skeletal animation). NPC models are assembled by
merging their component model ids, applying recolours and scale, baking flat
RS face colours into per-vertex colours, and decoding real texture sprites for
the (rare) textured faces.
"""

from .mesh_assembly import Triangle, assemble_npc_triangles, model_to_triangles
from .gltf_export import build_glb_bytes, export_glb
from .texture_archive import load_texture_images

__all__ = [
    "Triangle",
    "assemble_npc_triangles",
    "model_to_triangles",
    "export_glb",
    "build_glb_bytes",
    "load_texture_images",
]
