"""Minimal, dependency-free glTF 2.0 (GLB) writer.

Unreal's Interchange glTF importer builds empty static meshes from primitives
that lack NORMAL / TEXCOORD_0, so every primitive we emit carries POSITION,
NORMAL (flat per-face), TEXCOORD_0, COLOR_0 and a material. One mesh with one
primitive per material group keeps the import as a single multi-slot static mesh.
"""

from __future__ import annotations

import io
import json
import struct

import numpy as np

# glTF constants.
_FLOAT = 5126
_UBYTE = 5121
_UINT = 5125
_ARRAY_BUFFER = 34962
_ELEMENT_ARRAY_BUFFER = 34963
_TRIANGLES = 4


class GLBBuilder:
    def __init__(self) -> None:
        self._bin = bytearray()
        self.buffer_views: list[dict] = []
        self.accessors: list[dict] = []
        self.images: list[dict] = []
        self.samplers: list[dict] = []
        self.textures: list[dict] = []
        self.materials: list[dict] = []
        self.primitives: list[dict] = []
        self.morph_target_count = 0
        self._animations: list[dict] = []

    def _align(self, alignment: int = 4) -> None:
        while len(self._bin) % alignment:
            self._bin.append(0)

    def _add_view(self, data: bytes, target: int | None = None) -> int:
        self._align(4)
        offset = len(self._bin)
        self._bin += data
        view = {"buffer": 0, "byteOffset": offset, "byteLength": len(data)}
        if target is not None:
            view["target"] = target
        self.buffer_views.append(view)
        return len(self.buffer_views) - 1

    def _add_accessor(
        self,
        data: bytes,
        count: int,
        type_: str,
        component_type: int,
        *,
        normalized: bool = False,
        mins=None,
        maxs=None,
        target: int | None = None,
    ) -> int:
        view = self._add_view(data, target)
        accessor = {
            "bufferView": view,
            "componentType": component_type,
            "count": count,
            "type": type_,
        }
        if normalized:
            accessor["normalized"] = True
        if mins is not None:
            accessor["min"] = mins
        if maxs is not None:
            accessor["max"] = maxs
        self.accessors.append(accessor)
        return len(self.accessors) - 1

    def add_color_material(self, name: str, *, blend: bool = False) -> int:
        mat: dict = {
            "name": name,
            "pbrMetallicRoughness": {
                "baseColorFactor": [1.0, 1.0, 1.0, 1.0],
                "metallicFactor": 0.0,
                "roughnessFactor": 1.0,
            },
            "doubleSided": blend,
        }
        if blend:
            mat["alphaMode"] = "BLEND"
        self.materials.append(mat)
        return len(self.materials) - 1

    def add_texture_material(self, name: str, pil_image, *, blend: bool = False) -> int:
        buffer = io.BytesIO()
        pil_image.convert("RGBA").save(buffer, format="PNG")
        view = self._add_view(buffer.getvalue())
        self.images.append({"bufferView": view, "mimeType": "image/png", "name": name})
        image_index = len(self.images) - 1

        if not self.samplers:
            self.samplers.append(
                {"magFilter": 9729, "minFilter": 9987, "wrapS": 10497, "wrapT": 10497}
            )
        self.textures.append({"source": image_index, "sampler": 0})
        texture_index = len(self.textures) - 1

        mat: dict = {
            "name": name,
            "pbrMetallicRoughness": {
                "baseColorTexture": {"index": texture_index},
                "metallicFactor": 0.0,
                "roughnessFactor": 1.0,
            },
            "doubleSided": blend,
        }
        if blend:
            mat["alphaMode"] = "BLEND"
        self.materials.append(mat)
        return len(self.materials) - 1

    def add_primitive(
        self,
        positions: np.ndarray,
        normals: np.ndarray,
        uvs: np.ndarray,
        colors: np.ndarray,
        material_index: int | None,
        morph_targets: list[tuple[np.ndarray | None, np.ndarray | None]] | None = None,
    ) -> None:
        count = len(positions)
        pos = np.ascontiguousarray(positions, dtype="<f4")
        pos_min = pos.min(axis=0).tolist()
        pos_max = pos.max(axis=0).tolist()

        a_pos = self._add_accessor(
            pos.tobytes(), count, "VEC3", _FLOAT, mins=pos_min, maxs=pos_max, target=_ARRAY_BUFFER
        )
        a_nrm = self._add_accessor(
            np.ascontiguousarray(normals, dtype="<f4").tobytes(), count, "VEC3", _FLOAT, target=_ARRAY_BUFFER
        )
        a_uv = self._add_accessor(
            np.ascontiguousarray(uvs, dtype="<f4").tobytes(), count, "VEC2", _FLOAT, target=_ARRAY_BUFFER
        )
        a_col = self._add_accessor(
            np.ascontiguousarray(colors, dtype="u1").tobytes(),
            count,
            "VEC4",
            _UBYTE,
            normalized=True,
            target=_ARRAY_BUFFER,
        )
        indices = np.arange(count, dtype="<u4")
        a_idx = self._add_accessor(
            indices.tobytes(), count, "SCALAR", _UINT, target=_ELEMENT_ARRAY_BUFFER
        )

        primitive = {
            "attributes": {
                "POSITION": a_pos,
                "NORMAL": a_nrm,
                "TEXCOORD_0": a_uv,
                "COLOR_0": a_col,
            },
            "indices": a_idx,
            "mode": _TRIANGLES,
        }
        if material_index is not None:
            primitive["material"] = material_index

        if morph_targets:
            targets = []
            for pos_delta, col_delta in morph_targets:
                entry: dict = {}
                if pos_delta is not None:
                    delta = np.ascontiguousarray(pos_delta, dtype="<f4")
                    t_min = delta.min(axis=0).tolist()
                    t_max = delta.max(axis=0).tolist()
                    entry["POSITION"] = self._add_accessor(
                        delta.tobytes(), count, "VEC3", _FLOAT, mins=t_min, maxs=t_max,
                        target=_ARRAY_BUFFER,
                    )
                if col_delta is not None:
                    cd = np.ascontiguousarray(col_delta, dtype="<f4")
                    c_min = cd.min(axis=0).tolist()
                    c_max = cd.max(axis=0).tolist()
                    entry["COLOR_0"] = self._add_accessor(
                        cd.tobytes(), count, "VEC4", _FLOAT, mins=c_min, maxs=c_max,
                        target=_ARRAY_BUFFER,
                    )
                if entry:
                    targets.append(entry)
            if targets:
                primitive["targets"] = targets
                self.morph_target_count = max(self.morph_target_count, len(targets))

        self.primitives.append(primitive)

    def set_morph_animation(
        self,
        times: list[float],
        keyframe_targets: list[int],
        name: str = "idle",
        *,
        interpolation: str = "LINEAR",
    ) -> None:
        """Define a weight-track animation (replaces any existing clips).
        ``times`` are keyframe seconds; ``keyframe_targets[k]`` is the morph
        target fully active at keyframe k (others 0). Use ``STEP`` for RS
        spotanims (hold each frame, no crossfade)."""
        self._animations = []
        self.add_morph_animation(times, keyframe_targets, name, interpolation=interpolation)

    def add_morph_animation(
        self,
        times: list[float],
        keyframe_targets: list[int],
        name: str = "idle",
        *,
        interpolation: str = "LINEAR",
    ) -> None:
        """Append a weight-track animation clip. Multiple clips share the one
        union morph-target set on the mesh; each clip activates its own targets
        and leaves the rest at 0 (e.g. a player's ``stand`` and ``walk``)."""
        self._animations.append(
            {
                "times": list(times),
                "keyframe_targets": list(keyframe_targets),
                "name": name,
                "interpolation": interpolation,
            }
        )

    def _build_animation(self, gltf: dict) -> None:
        if not self._animations or self.morph_target_count == 0:
            return
        n_targets = self.morph_target_count
        animations: list[dict] = []
        for anim in self._animations:
            times = anim["times"]
            keyframe_targets = anim["keyframe_targets"]
            n_keys = len(times)

            time_arr = np.asarray(times, dtype="<f4")
            a_time = self._add_accessor(
                time_arr.tobytes(), n_keys, "SCALAR", _FLOAT,
                mins=[float(time_arr.min())], maxs=[float(time_arr.max())],
            )

            weights = np.zeros((n_keys, n_targets), dtype="<f4")
            for k, target in enumerate(keyframe_targets):
                if 0 <= target < n_targets:
                    weights[k, target] = 1.0
            a_weights = self._add_accessor(
                weights.reshape(-1).tobytes(), n_keys * n_targets, "SCALAR", _FLOAT,
            )

            animations.append(
                {
                    "name": anim["name"],
                    "samplers": [
                        {
                            "input": a_time,
                            "output": a_weights,
                            "interpolation": anim.get("interpolation", "LINEAR"),
                        }
                    ],
                    "channels": [
                        {"sampler": 0, "target": {"node": 0, "path": "weights"}}
                    ],
                }
            )

        gltf["animations"] = animations

    def build(self) -> bytes:
        mesh: dict = {"name": "RSModel", "primitives": self.primitives}
        if self.morph_target_count > 0:
            mesh["weights"] = [0.0] * self.morph_target_count
        gltf = {
            "asset": {"version": "2.0", "generator": "rs-sandbox-world"},
            "scene": 0,
            "scenes": [{"nodes": [0]}],
            "nodes": [{"mesh": 0, "name": "RSModel"}],
            "meshes": [mesh],
            "accessors": self.accessors,
            "bufferViews": self.buffer_views,
            "buffers": [{}],
        }
        self._build_animation(gltf)
        gltf["buffers"] = [{"byteLength": len(self._bin)}]
        if self.materials:
            gltf["materials"] = self.materials
        if self.images:
            gltf["images"] = self.images
        if self.samplers:
            gltf["samplers"] = self.samplers
        if self.textures:
            gltf["textures"] = self.textures

        json_bytes = json.dumps(gltf, separators=(",", ":")).encode("utf-8")
        while len(json_bytes) % 4:
            json_bytes += b" "
        bin_bytes = bytes(self._bin)
        while len(bin_bytes) % 4:
            bin_bytes += b"\x00"

        total = 12 + 8 + len(json_bytes) + 8 + len(bin_bytes)
        out = bytearray()
        out += struct.pack("<III", 0x46546C67, 2, total)  # "glTF", version 2
        out += struct.pack("<II", len(json_bytes), 0x4E4F534A)  # "JSON"
        out += json_bytes
        out += struct.pack("<II", len(bin_bytes), 0x004E4942)  # "BIN\0"
        out += bin_bytes
        return bytes(out)
