"""Serve the RS web viewer with on-demand cache APIs (models + sounds).

Models and sounds are synthesized from the 377 cache at request time.
The legacy ``outputs/unreal_exports/`` GLB folder is not used by the viewer.
"""

from __future__ import annotations

import argparse
import json
import re
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from src.cache.cache_locator import CacheReader
from src.cache.npc_index import NPCIndex
from src.config import DEFAULT_CACHE_DIR, cache_setup_hint, discover_cache_dir
from src.export.anim_data import load_animation_data
from src.export.npc_glb import (
    build_model_glb_bytes,
    build_npc_custom_glb_bytes,
    build_npc_glb_bytes,
    npc_clone_detail,
    npc_recolor_pairs,
    build_npc_manifest,
    create_render_context,
)
from src.export.item_glb import (
    build_object_glb_bytes,
    build_object_manifest,
    create_object_context,
)
from src.export.loc_glb import (
    build_loc_glb_bytes,
    build_loc_manifest,
    create_loc_context,
)
from src.export.player_glb import (
    COMBAT_ANIMS,
    EMOTE_ANIMS,
    build_idk_kits_manifest,
    build_idk_manifest,
    build_kit_preview_glb_bytes,
    build_player_glb_bytes,
    create_player_context,
)
from src.export.spotanim_glb import (
    build_spotanim_glb_bytes,
    build_spotanim_manifest,
    create_gfx_context,
)
from src.export.sprite_archive import build_sprite_context, build_sprite_manifest
from src.export.texture_archive import build_texture_context, build_texture_manifest
from src.export.font_archive import (
    build_font_context,
    build_font_manifest,
    render_font_png,
)
from src.export.interface_render import (
    build_interface_render_context,
    build_interface_manifest,
    render_interface_png,
)
from src.rs2.sound_bank import has_sound, load_sounds, render_wav, sound_count

_SOUND_API = re.compile(r"^/api/sound/(\d+)\.wav$")
_NPC_API = re.compile(r"^/api/npc/(\d+)\.glb$")
_NPC_CLONE_JSON = re.compile(r"^/api/npc/(\d+)/clone\.json$")
_MODEL_API = re.compile(r"^/api/model/(\d+)\.glb$")
_HSL_RGB_JSON = "/api/hsl-rgb.json"
_SPOT_API = re.compile(r"^/api/spotanim/(\d+)\.glb$")
_OBJECT_API = re.compile(r"^/api/object/(\d+)\.glb$")
_ITEM_API = re.compile(r"^/api/item/(\d+)\.glb$")
_LOC_API = re.compile(r"^/api/loc/(\d+)\.glb$")
_SPRITE_API = re.compile(r"^/api/sprite/([a-z0-9_]+)/(\d+)\.png$")
_FONT_API = re.compile(r"^/api/font/([a-z0-9_]+)\.png$")
_INTERFACE_API = re.compile(r"^/api/interface/(\d+)\.png$")
_TEXTURE_API = re.compile(r"^/api/texture/(\d+)\.png$")
_PLAYER_API = "/api/player.glb"
_SOUND_PING = "/api/sound/ping"
_API_PING = "/api/ping.json"
_NPCS_JSON = "/api/npcs.json"
_SPOTANIMS_JSON = "/api/spotanims.json"
_OBJECTS_JSON = "/api/objects.json"
_ITEMS_JSON = "/api/items.json"
_LOCS_JSON = "/api/locs.json"
_IDK_JSON = "/api/idk.json"
_IDK_KITS_JSON = "/api/idk-kits.json"
_CUSTOM_API = "/api/custom.glb"
_NPC_CUSTOM_API = "/api/npc-custom.glb"
_IDK_KIT_API = re.compile(r"^/api/idk-kit/(\d+)\.glb$")
_SPRITES_JSON = "/api/sprites.json"
_FONTS_JSON = "/api/fonts.json"
_INTERFACES_JSON = "/api/interfaces.json"
_TEXTURES_JSON = "/api/textures.json"
_VIEWER_BUILD = "serve-viewer-5"
_AUDIO_SOURCE = "cache-synth"
_MODEL_SOURCE = "cache-synth"
_BLOCKED_STATIC_AUDIO = (".mp3", ".ogg", ".m4a", ".flac")


def _parse_npc_anims(query: str) -> list[tuple[int, str]]:
    """Parse ``anims=727:cast_wave,407:attack_2h`` query pairs."""
    out: list[tuple[int, str]] = []
    raw = parse_qs(query).get("anims", [""])[0]
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if ":" in part:
            sid, name = part.split(":", 1)
        else:
            sid, name = part, f"seq_{part}"
        try:
            out.append((int(sid), name.strip() or f"seq_{sid}"))
        except ValueError:
            continue
    return out


class ViewerHandler(SimpleHTTPRequestHandler):
    _sounds_ready = False
    _npc_ctx = None
    _npc_manifest: bytes | None = None
    _gfx_ctx = None
    _spot_manifest: bytes | None = None
    _obj_ctx = None
    _obj_manifest: bytes | None = None
    _loc_ctx = None
    _loc_manifest: bytes | None = None
    _player_ctx = None
    _idk_manifest: bytes | None = None
    _idk_kits_manifest: bytes | None = None
    _sprite_ctx: dict | None = None
    _sprite_manifest: bytes | None = None
    _font_ctx: dict | None = None
    _font_manifest: bytes | None = None
    _font_cache: dict | None = None
    _iface_ctx = None
    _iface_manifest: bytes | None = None
    _iface_cache: dict | None = None
    _tex_ctx: dict | None = None
    _tex_manifest: bytes | None = None

    def __init__(self, *args, directory: str | None = None, **kwargs):
        super().__init__(*args, directory=directory, **kwargs)

    def do_HEAD(self) -> None:
        self._route_api(head_only=True)

    def do_GET(self) -> None:
        self._route_api(head_only=False)

    def _route_api(self, *, head_only: bool) -> None:
        path = self.path.split("?", 1)[0]
        if path == _API_PING:
            body = json.dumps(
                {
                    "ok": True,
                    "build": _VIEWER_BUILD,
                    "npcs": ViewerHandler._npc_manifest is not None,
                    "objects": ViewerHandler._obj_manifest is not None,
                    "spotanims": ViewerHandler._spot_manifest is not None,
                    "locs": ViewerHandler._loc_manifest is not None,
                    "player": ViewerHandler._player_ctx is not None,
                    "sprites": ViewerHandler._sprite_ctx is not None,
                    "sounds": ViewerHandler._sounds_ready,
                }
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if not head_only:
                self.wfile.write(body)
            return
        if path == _SOUND_PING:
            body = (
                b'{"ok":true,"sounds":true,"audioSource":"'
                + _AUDIO_SOURCE.encode("ascii")
                + b'"}'
            )
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if not head_only:
                self.wfile.write(body)
            return
        if path == _NPCS_JSON:
            self._serve_npc_manifest(head_only=head_only)
            return
        if path == _SPOTANIMS_JSON:
            self._serve_spotanim_manifest(head_only=head_only)
            return
        if path in (_OBJECTS_JSON, _ITEMS_JSON):
            self._serve_object_manifest(head_only=head_only)
            return
        if path == _LOCS_JSON:
            self._serve_loc_manifest(head_only=head_only)
            return
        if path == _IDK_JSON:
            self._serve_idk_manifest(head_only=head_only)
            return
        if path == _IDK_KITS_JSON:
            self._serve_idk_kits_manifest(head_only=head_only)
            return
        if path == _SPRITES_JSON:
            self._serve_sprite_manifest(head_only=head_only)
            return
        if path == _FONTS_JSON:
            self._serve_font_manifest(head_only=head_only)
            return
        if path == _INTERFACES_JSON:
            self._serve_interface_manifest(head_only=head_only)
            return
        if path == _TEXTURES_JSON:
            self._serve_texture_manifest(head_only=head_only)
            return
        if path == _PLAYER_API:
            self._serve_player(head_only=head_only)
            return
        if path == _CUSTOM_API:
            self._serve_custom(head_only=head_only)
            return
        if path == _NPC_CUSTOM_API:
            self._serve_npc_custom(head_only=head_only)
            return
        if path == _HSL_RGB_JSON:
            self._serve_hsl_rgb(head_only=head_only)
            return
        match = _IDK_KIT_API.match(path)
        if match:
            self._serve_idk_kit(int(match.group(1)), head_only=head_only)
            return
        match = _SPRITE_API.match(path)
        if match:
            self._serve_sprite(match.group(1), int(match.group(2)), head_only=head_only)
            return
        match = _FONT_API.match(path)
        if match:
            self._serve_font(match.group(1), head_only=head_only)
            return
        match = _INTERFACE_API.match(path)
        if match:
            self._serve_interface(int(match.group(1)), head_only=head_only)
            return
        match = _TEXTURE_API.match(path)
        if match:
            self._serve_texture(int(match.group(1)), head_only=head_only)
            return
        match = _LOC_API.match(path)
        if match:
            self._serve_loc(int(match.group(1)), head_only=head_only)
            return
        match = _SOUND_API.match(path)
        if match:
            self._serve_sound(int(match.group(1)), head_only=head_only)
            return
        match = _NPC_CLONE_JSON.match(path)
        if match:
            self._serve_npc_clone_json(int(match.group(1)), head_only=head_only)
            return
        match = _MODEL_API.match(path)
        if match:
            self._serve_model_glb(int(match.group(1)), head_only=head_only)
            return
        match = _NPC_API.match(path)
        if match:
            self._serve_npc(int(match.group(1)), head_only=head_only)
            return
        match = _SPOT_API.match(path)
        if match:
            self._serve_spotanim(int(match.group(1)), head_only=head_only)
            return
        match = _OBJECT_API.match(path) or _ITEM_API.match(path)
        if match:
            self._serve_object(int(match.group(1)), head_only=head_only)
            return
        lower = path.lower()
        if lower.endswith(_BLOCKED_STATIC_AUDIO):
            self.send_error(403, "Static audio files are disabled; use /api/sound/<id>.wav")
            return
        if head_only:
            super().do_HEAD()
        else:
            super().do_GET()

    def _serve_npc_manifest(self, *, head_only: bool = False) -> None:
        if ViewerHandler._npc_manifest is None:
            self.send_error(503, "NPC index not loaded")
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("X-RS-Model-Source", _MODEL_SOURCE)
        self.send_header("Content-Length", str(len(ViewerHandler._npc_manifest)))
        self.send_header("Cache-Control", "public, max-age=300")
        self.end_headers()
        if not head_only:
            self.wfile.write(ViewerHandler._npc_manifest)

    def _serve_npc(self, npc_id: int, *, head_only: bool = False) -> None:
        ctx = ViewerHandler._npc_ctx
        if ctx is None:
            self.send_error(503, "NPC renderer not ready")
            return
        if ctx.index.get(npc_id) is None:
            self.send_error(404, f"NPC {npc_id} not in cache")
            return
        query = urlparse(self.path).query
        extra_anims = _parse_npc_anims(query) or None
        glb = build_npc_glb_bytes(ctx, npc_id, extra_anims=extra_anims)
        if not glb:
            self.send_error(404, f"NPC {npc_id} has no geometry")
            return
        self.send_response(200)
        self.send_header("Content-Type", "model/gltf-binary")
        self.send_header("X-RS-Model-Source", _MODEL_SOURCE)
        self.send_header("X-RS-GLB-Build", "npc-v2")
        self.send_header("Content-Length", str(len(glb)))
        self.send_header("Cache-Control", "no-store, must-revalidate")
        self.end_headers()
        if not head_only:
            self.wfile.write(glb)

    def _serve_object_manifest(self, *, head_only: bool = False) -> None:
        if ViewerHandler._obj_manifest is None:
            self.send_error(503, "Object index not loaded")
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("X-RS-Model-Source", _MODEL_SOURCE)
        self.send_header("Content-Length", str(len(ViewerHandler._obj_manifest)))
        self.send_header("Cache-Control", "public, max-age=300")
        self.end_headers()
        if not head_only:
            self.wfile.write(ViewerHandler._obj_manifest)

    def _serve_object(self, item_id: int, *, head_only: bool = False) -> None:
        ctx = ViewerHandler._obj_ctx
        if ctx is None:
            self.send_error(503, "Object renderer not ready")
            return
        if item_id < 0 or item_id >= ctx.items.count:
            self.send_error(404, f"Object {item_id} not in cache")
            return
        glb = build_object_glb_bytes(ctx, item_id)
        if not glb:
            self.send_error(404, f"Object {item_id} has no geometry")
            return
        self.send_response(200)
        self.send_header("Content-Type", "model/gltf-binary")
        self.send_header("X-RS-Model-Source", _MODEL_SOURCE)
        self.send_header("X-RS-GLB-Build", "object-v1")
        self.send_header("Content-Length", str(len(glb)))
        self.send_header("Cache-Control", "no-store, must-revalidate")
        self.end_headers()
        if not head_only:
            self.wfile.write(glb)

    def _query(self) -> dict:
        return parse_qs(urlparse(self.path).query)

    def _serve_loc_manifest(self, *, head_only: bool = False) -> None:
        if ViewerHandler._loc_manifest is None:
            self.send_error(503, "Loc index not loaded")
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("X-RS-Model-Source", _MODEL_SOURCE)
        self.send_header("Content-Length", str(len(ViewerHandler._loc_manifest)))
        self.send_header("Cache-Control", "public, max-age=300")
        self.end_headers()
        if not head_only:
            self.wfile.write(ViewerHandler._loc_manifest)

    def _serve_loc(self, loc_id: int, *, head_only: bool = False) -> None:
        ctx = ViewerHandler._loc_ctx
        if ctx is None:
            self.send_error(503, "Loc renderer not ready")
            return
        if ctx.get(loc_id) is None:
            self.send_error(404, f"Loc {loc_id} not in cache")
            return
        q = self._query()
        kind = int(q["kind"][0]) if "kind" in q else None
        rotation = int(q["rot"][0]) if "rot" in q else 0
        glb = build_loc_glb_bytes(ctx, loc_id, kind=kind, rotation=rotation)
        if not glb:
            self.send_error(404, f"Loc {loc_id} has no geometry")
            return
        self.send_response(200)
        self.send_header("Content-Type", "model/gltf-binary")
        self.send_header("X-RS-Model-Source", _MODEL_SOURCE)
        self.send_header("X-RS-GLB-Build", "loc-v1")
        self.send_header("Content-Length", str(len(glb)))
        self.send_header("Cache-Control", "no-store, must-revalidate")
        self.end_headers()
        if not head_only:
            self.wfile.write(glb)

    def _serve_idk_manifest(self, *, head_only: bool = False) -> None:
        if ViewerHandler._idk_manifest is None:
            self.send_error(503, "Identity kit index not loaded")
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("X-RS-Model-Source", _MODEL_SOURCE)
        self.send_header("Content-Length", str(len(ViewerHandler._idk_manifest)))
        self.send_header("Cache-Control", "public, max-age=300")
        self.end_headers()
        if not head_only:
            self.wfile.write(ViewerHandler._idk_manifest)

    def _serve_idk_kits_manifest(self, *, head_only: bool = False) -> None:
        if ViewerHandler._idk_kits_manifest is None:
            self.send_error(503, "Identity kit catalog not loaded")
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("X-RS-Model-Source", _MODEL_SOURCE)
        self.send_header("Content-Length", str(len(ViewerHandler._idk_kits_manifest)))
        self.send_header("Cache-Control", "public, max-age=300")
        self.end_headers()
        if not head_only:
            self.wfile.write(ViewerHandler._idk_kits_manifest)

    def _parse_player_query(self, q) -> tuple[int, list[int], list[int], list[int], list[tuple[int, str]] | None]:
        def _int(name: str, default: int) -> int:
            try:
                return int(q[name][0])
            except (KeyError, ValueError, IndexError):
                return default

        gender = _int("gender", 0)
        kit_indices = [_int(f"k{i}", -1) for i in range(7)]
        colors = [_int(f"c{i}", 0) for i in range(5)]
        extra_models: list[int] = []
        if "extra" in q:
            for part in q["extra"][0].split(","):
                part = part.strip()
                if part:
                    try:
                        extra_models.append(int(part))
                    except ValueError:
                        pass
        extra_anims: list[tuple[int, str]] | None = None
        if _int("combat", 0):
            extra_anims = list(COMBAT_ANIMS)
        if _int("emotes", 0):
            extra_anims = (extra_anims or []) + list(EMOTE_ANIMS)
        return gender, kit_indices, colors, extra_models, extra_anims

    def _serve_player(self, *, head_only: bool = False) -> None:
        ctx = ViewerHandler._player_ctx
        if ctx is None:
            self.send_error(503, "Player renderer not ready")
            return
        gender, kit_indices, colors, _, extra_anims = self._parse_player_query(self._query())
        glb = build_player_glb_bytes(
            ctx, gender=gender, kit_indices=kit_indices, colors=colors, extra_anims=extra_anims
        )
        if not glb:
            self.send_error(404, "Player has no geometry")
            return
        self.send_response(200)
        self.send_header("Content-Type", "model/gltf-binary")
        self.send_header("X-RS-Model-Source", _MODEL_SOURCE)
        self.send_header("X-RS-GLB-Build", "player-v2")
        self.send_header("Content-Length", str(len(glb)))
        self.send_header("Cache-Control", "no-store, must-revalidate")
        self.end_headers()
        if not head_only:
            self.wfile.write(glb)

    def _parse_recolor_query(self, query: str) -> dict[int, int]:
        from urllib.parse import parse_qs

        params = parse_qs(query, keep_blank_values=False)
        recolor_overrides: dict[int, int] = {}
        if "recolor" in params and params["recolor"][0].strip():
            for pair in params["recolor"][0].split(","):
                if ":" not in pair:
                    continue
                src_s, dst_s = pair.split(":", 1)
                if src_s.strip().isdigit() and dst_s.strip().isdigit():
                    recolor_overrides[int(src_s)] = int(dst_s)
        return recolor_overrides

    def _parse_npc_custom_query(self, query: str) -> tuple[int, list[int] | None, list[int] | None, dict[int, int]]:
        from urllib.parse import parse_qs

        params = parse_qs(query, keep_blank_values=False)
        base = int(params.get("base", ["0"])[0])
        models: list[int] | None = None
        if "models" in params and params["models"][0].strip():
            models = [int(x) for x in params["models"][0].split(",") if x.strip().isdigit()]
        extra: list[int] | None = None
        if "extra" in params and params["extra"][0].strip():
            extra = [int(x) for x in params["extra"][0].split(",") if x.strip().isdigit()]
        recolor_overrides = self._parse_recolor_query(query)
        if "dst" in params and params["dst"][0].strip():
            dsts = [int(x) for x in params["dst"][0].split(",") if x.strip().isdigit()]
            ctx = ViewerHandler._npc_ctx
            if ctx is not None:
                npc = ctx.index.get(base)
                if npc is not None:
                    pairs = npc_recolor_pairs(npc)
                    for i, dst in enumerate(dsts):
                        if i < len(pairs):
                            recolor_overrides[pairs[i]["src"]] = dst
        return base, models, extra, recolor_overrides

    def _serve_npc_clone_json(self, npc_id: int, *, head_only: bool = False) -> None:
        ctx = ViewerHandler._npc_ctx
        if ctx is None:
            self.send_error(503, "NPC renderer not ready")
            return
        detail = npc_clone_detail(ctx, npc_id)
        if detail is None:
            self.send_error(404, f"NPC {npc_id} not in cache")
            return
        body = json.dumps(detail).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("X-RS-Model-Source", _MODEL_SOURCE)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "public, max-age=300")
        self.end_headers()
        if not head_only:
            self.wfile.write(body)

    def _serve_model_glb(self, model_id: int, *, head_only: bool = False) -> None:
        ctx = ViewerHandler._npc_ctx
        if ctx is None:
            self.send_error(503, "Model renderer not ready")
            return
        recolor = self._parse_recolor_query(self._query())
        glb = build_model_glb_bytes(ctx, model_id, recolor=recolor or None)
        if not glb:
            self.send_error(404, f"Model {model_id} has no geometry")
            return
        self.send_response(200)
        self.send_header("Content-Type", "model/gltf-binary")
        self.send_header("X-RS-Model-Source", _MODEL_SOURCE)
        self.send_header("X-RS-GLB-Build", "model-v1")
        self.send_header("Content-Length", str(len(glb)))
        self.send_header("Cache-Control", "no-store, must-revalidate")
        self.end_headers()
        if not head_only:
            self.wfile.write(glb)

    def _serve_hsl_rgb(self, *, head_only: bool = False) -> None:
        from src.rs2.palette import build_palette
        from src.export.npc_glb import hsl_rgb_hex

        from urllib.parse import parse_qs

        params = parse_qs(self._query(), keep_blank_values=False)
        raw = params.get("i", [""])[0]
        indices = [int(x) for x in raw.split(",") if x.strip().isdigit()]
        palette = build_palette()
        colors = {str(i): hsl_rgb_hex(i, palette) for i in indices[:256]}
        body = json.dumps({"colors": colors}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "public, max-age=3600")
        self.end_headers()
        if not head_only:
            self.wfile.write(body)

    def _serve_npc_custom(self, *, head_only: bool = False) -> None:
        ctx = ViewerHandler._npc_ctx
        if ctx is None:
            self.send_error(503, "NPC renderer not ready")
            return
        base, models, extra, recolor_overrides = self._parse_npc_custom_query(self._query())
        if base <= 0 or ctx.index.get(base) is None:
            self.send_error(400, "Missing or invalid base NPC id")
            return
        extra_anims = self._parse_npc_anims(self._query())
        glb = build_npc_custom_glb_bytes(
            ctx,
            base,
            model_ids=models,
            recolor_overrides=recolor_overrides or None,
            extra_model_ids=extra,
            extra_anims=extra_anims or None,
        )
        if not glb:
            self.send_error(404, "Custom NPC has no geometry")
            return
        self.send_response(200)
        self.send_header("Content-Type", "model/gltf-binary")
        self.send_header("X-RS-Model-Source", _MODEL_SOURCE)
        self.send_header("X-RS-GLB-Build", "npc-custom-v1")
        self.send_header("Content-Length", str(len(glb)))
        self.send_header("Cache-Control", "no-store, must-revalidate")
        self.end_headers()
        if not head_only:
            self.wfile.write(glb)

    def _serve_custom(self, *, head_only: bool = False) -> None:
        ctx = ViewerHandler._player_ctx
        if ctx is None:
            self.send_error(503, "Custom character renderer not ready")
            return
        gender, kit_indices, colors, extra_models, extra_anims = self._parse_player_query(self._query())
        glb = build_player_glb_bytes(
            ctx,
            gender=gender,
            kit_indices=kit_indices,
            colors=colors,
            extra_anims=extra_anims,
            extra_model_ids=extra_models or None,
        )
        if not glb:
            self.send_error(404, "Custom character has no geometry")
            return
        self.send_response(200)
        self.send_header("Content-Type", "model/gltf-binary")
        self.send_header("X-RS-Model-Source", _MODEL_SOURCE)
        self.send_header("X-RS-GLB-Build", "custom-v1")
        self.send_header("Content-Length", str(len(glb)))
        self.send_header("Cache-Control", "no-store, must-revalidate")
        self.end_headers()
        if not head_only:
            self.wfile.write(glb)

    def _serve_idk_kit(self, kit_id: int, *, head_only: bool = False) -> None:
        ctx = ViewerHandler._player_ctx
        if ctx is None:
            self.send_error(503, "Identity kit preview not ready")
            return
        glb = build_kit_preview_glb_bytes(ctx, kit_id)
        if not glb:
            self.send_error(404, f"Kit {kit_id} has no geometry")
            return
        self.send_response(200)
        self.send_header("Content-Type", "model/gltf-binary")
        self.send_header("X-RS-Model-Source", _MODEL_SOURCE)
        self.send_header("X-RS-GLB-Build", "idk-kit-v1")
        self.send_header("Content-Length", str(len(glb)))
        self.send_header("Cache-Control", "no-store, must-revalidate")
        self.end_headers()
        if not head_only:
            self.wfile.write(glb)

    def _serve_sprite_manifest(self, *, head_only: bool = False) -> None:
        if ViewerHandler._sprite_manifest is None:
            self.send_error(503, "Sprites not loaded")
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(ViewerHandler._sprite_manifest)))
        self.send_header("Cache-Control", "public, max-age=300")
        self.end_headers()
        if not head_only:
            self.wfile.write(ViewerHandler._sprite_manifest)

    def _serve_sprite(self, name: str, index: int, *, head_only: bool = False) -> None:
        ctx = ViewerHandler._sprite_ctx
        if ctx is None:
            self.send_error(503, "Sprites not loaded")
            return
        frames = ctx.get(name)
        if not frames or index < 0 or index >= len(frames):
            self.send_error(404, f"Sprite {name}/{index} not in cache")
            return
        png = frames[index]
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("X-RS-Model-Source", _MODEL_SOURCE)
        self.send_header("Content-Length", str(len(png)))
        self.send_header("Cache-Control", "public, max-age=86400")
        self.end_headers()
        if not head_only:
            self.wfile.write(png)

    def _serve_texture_manifest(self, *, head_only: bool = False) -> None:
        if ViewerHandler._tex_manifest is None:
            self.send_error(503, "Textures not loaded")
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("X-RS-Model-Source", _MODEL_SOURCE)
        self.send_header("Content-Length", str(len(ViewerHandler._tex_manifest)))
        self.send_header("Cache-Control", "public, max-age=300")
        self.end_headers()
        if not head_only:
            self.wfile.write(ViewerHandler._tex_manifest)

    def _serve_texture(self, tex_id: int, *, head_only: bool = False) -> None:
        ctx = ViewerHandler._tex_ctx
        if ctx is None:
            self.send_error(503, "Textures not loaded")
            return
        png = ctx.get(tex_id)
        if png is None:
            self.send_error(404, f"Texture {tex_id} not in cache")
            return
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("X-RS-Model-Source", _MODEL_SOURCE)
        self.send_header("Content-Length", str(len(png)))
        self.send_header("Cache-Control", "public, max-age=86400")
        self.end_headers()
        if not head_only:
            self.wfile.write(png)

    def _serve_font_manifest(self, *, head_only: bool = False) -> None:
        if ViewerHandler._font_manifest is None:
            self.send_error(503, "Fonts not loaded")
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("X-RS-Model-Source", _MODEL_SOURCE)
        self.send_header("Content-Length", str(len(ViewerHandler._font_manifest)))
        self.send_header("Cache-Control", "public, max-age=300")
        self.end_headers()
        if not head_only:
            self.wfile.write(ViewerHandler._font_manifest)

    def _serve_font(self, name: str, *, head_only: bool = False) -> None:
        ctx = ViewerHandler._font_ctx
        if ctx is None:
            self.send_error(503, "Fonts not loaded")
            return
        q = self._query()
        text = q["text"][0] if "text" in q else ""
        try:
            rgb = int(q["rgb"][0], 16) if "rgb" in q else 0xFFFFFF
        except (ValueError, IndexError):
            rgb = 0xFFFFFF
        cache = ViewerHandler._font_cache
        if cache is None:
            cache = ViewerHandler._font_cache = {}
        key = (name, text, rgb)
        png = cache.get(key)
        if png is None:
            png = render_font_png(ctx, name, text, rgb=rgb)
            if png is None:
                self.send_error(404, f"Font {name!r} / text {text!r} not renderable")
                return
            cache[key] = png
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("X-RS-Model-Source", _MODEL_SOURCE)
        self.send_header("Content-Length", str(len(png)))
        self.send_header("Cache-Control", "public, max-age=86400")
        self.end_headers()
        if not head_only:
            self.wfile.write(png)

    def _serve_interface_manifest(self, *, head_only: bool = False) -> None:
        if ViewerHandler._iface_manifest is None:
            self.send_error(503, "Interfaces not loaded")
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("X-RS-Model-Source", _MODEL_SOURCE)
        self.send_header("Content-Length", str(len(ViewerHandler._iface_manifest)))
        self.send_header("Cache-Control", "public, max-age=300")
        self.end_headers()
        if not head_only:
            self.wfile.write(ViewerHandler._iface_manifest)

    def _serve_interface(self, iface_id: int, *, head_only: bool = False) -> None:
        ctx = ViewerHandler._iface_ctx
        if ctx is None:
            self.send_error(503, "Interfaces not loaded")
            return
        cache = ViewerHandler._iface_cache
        if cache is None:
            cache = ViewerHandler._iface_cache = {}
        png = cache.get(iface_id)
        if png is None:
            png = render_interface_png(ctx, iface_id)
            if png is None:
                self.send_error(404, f"Interface {iface_id} not found")
                return
            cache[iface_id] = png
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("X-RS-Model-Source", _MODEL_SOURCE)
        self.send_header("Content-Length", str(len(png)))
        self.send_header("Cache-Control", "public, max-age=86400")
        self.end_headers()
        if not head_only:
            self.wfile.write(png)

    def _serve_spotanim_manifest(self, *, head_only: bool = False) -> None:
        if ViewerHandler._spot_manifest is None:
            self.send_error(503, "Spotanim index not loaded")
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("X-RS-Model-Source", _MODEL_SOURCE)
        self.send_header("Content-Length", str(len(ViewerHandler._spot_manifest)))
        self.send_header("Cache-Control", "public, max-age=300")
        self.end_headers()
        if not head_only:
            self.wfile.write(ViewerHandler._spot_manifest)

    def _serve_spotanim(self, spot_id: int, *, head_only: bool = False) -> None:
        ctx = ViewerHandler._gfx_ctx
        if ctx is None:
            self.send_error(503, "GFX renderer not ready")
            return
        if spot_id not in ctx.spotanims:
            self.send_error(404, f"Spotanim {spot_id} not in cache")
            return
        glb = build_spotanim_glb_bytes(ctx, spot_id)
        if not glb:
            self.send_error(404, f"Spotanim {spot_id} has no geometry")
            return
        self.send_response(200)
        self.send_header("Content-Type", "model/gltf-binary")
        self.send_header("X-RS-Model-Source", _MODEL_SOURCE)
        self.send_header("X-RS-GLB-Build", "spotanim-v3")
        self.send_header("Content-Length", str(len(glb)))
        self.send_header("Cache-Control", "no-store, must-revalidate")
        self.end_headers()
        if not head_only:
            self.wfile.write(glb)

    def _serve_sound(self, sound_id: int, *, head_only: bool = False) -> None:
        if not ViewerHandler._sounds_ready:
            self.send_error(503, "Sound bank not loaded")
            return
        if not has_sound(sound_id):
            self.send_error(404, f"Sound {sound_id} not in 377 cache")
            return
        wav = render_wav(sound_id, loop_count=1)
        if not wav:
            self.send_error(500, "Synthesis failed")
            return
        self.send_response(200)
        self.send_header("Content-Type", "audio/wav")
        self.send_header("X-RS-Audio-Source", _AUDIO_SOURCE)
        self.send_header("Content-Length", str(len(wav)))
        self.send_header("Cache-Control", "public, max-age=86400")
        self.end_headers()
        if not head_only:
            self.wfile.write(wav)

    def log_message(self, format: str, *args) -> None:
        if (
            self.path.startswith("/api/sound/")
            or self.path.startswith("/api/npc/")
            or self.path.startswith("/api/spotanim/")
            or self.path.startswith("/api/object/")
            or self.path.startswith("/api/loc/")
            or self.path.startswith("/api/player.glb")
            or self.path.startswith("/api/custom.glb")
            or self.path.startswith("/api/idk-kit/")
            or self.path.startswith("/api/sprite/")
            or self.path.startswith("/api/font/")
            or self.path.startswith("/api/interface/")
            or self.path.startswith("/api/texture/")
        ):
            return
        super().log_message(format, *args)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Serve RS viewer + cache model/sound APIs.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8848)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument(
        "--web",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "web",
    )
    args = parser.parse_args(argv)

    web = args.web.resolve()
    root = web.parent
    print(f"Web root: {root}")
    print(f"Open: http://{args.host}:{args.port}/web/rs_viewer.html")
    print("NPCs, objects, spotanims (GFX), sounds: synthesized from cache on demand")

    cache_dir = discover_cache_dir(args.cache)
    if not (cache_dir / "main_file_cache.dat").exists():
        print(f"ERROR: No cache found at {cache_dir}")
        print(cache_setup_hint())
        return 1
    print(f"Cache: {cache_dir}")
    cache = CacheReader(cache_dir)
    index = NPCIndex.from_cache(cache_dir=cache_dir)
    print(f"NPC defs: {index.count}")

    print("Loading animation data...")
    anim = load_animation_data(cache)
    if anim:
        print(f"  {len(anim.seqs)} sequences, {len(anim.transforms)} frame transforms")
    else:
        print("  (no animation data — static poses only)")

    ViewerHandler._npc_ctx = create_render_context(cache, index, anim)
    manifest = build_npc_manifest(ViewerHandler._npc_ctx)
    ViewerHandler._npc_manifest = json.dumps(manifest).encode("utf-8")
    print(f"NPC list API: {manifest['count']} entries with models")

    ViewerHandler._gfx_ctx = create_gfx_context(cache, anim)
    spot_manifest = build_spotanim_manifest(ViewerHandler._gfx_ctx)
    ViewerHandler._spot_manifest = json.dumps(spot_manifest).encode("utf-8")
    print(f"Spotanim API: {spot_manifest['count']} GFX entries")

    try:
        ViewerHandler._obj_ctx = create_object_context(cache, cache_dir=cache_dir)
        obj_manifest = build_object_manifest(ViewerHandler._obj_ctx)
        ViewerHandler._obj_manifest = json.dumps(obj_manifest).encode("utf-8")
        print(f"Object API: {obj_manifest['count']} obj.dat entries with models")
    except Exception as exc:
        ViewerHandler._obj_ctx = None
        ViewerHandler._obj_manifest = None
        print(f"Object API: FAILED ({exc})")

    try:
        ViewerHandler._loc_ctx = create_loc_context(cache, anim, cache_dir=cache_dir)
        loc_manifest = build_loc_manifest(ViewerHandler._loc_ctx)
        ViewerHandler._loc_manifest = json.dumps(loc_manifest).encode("utf-8")
        print(f"Loc (scenery) API: {loc_manifest['count']} loc.dat entries with models")
    except Exception as exc:
        ViewerHandler._loc_ctx = None
        ViewerHandler._loc_manifest = None
        print(f"Loc API: FAILED ({exc})")

    try:
        ViewerHandler._player_ctx = create_player_context(cache, anim, cache_dir=cache_dir)
        idk_manifest = build_idk_manifest(ViewerHandler._player_ctx)
        ViewerHandler._idk_manifest = json.dumps(idk_manifest).encode("utf-8")
        kits_manifest = build_idk_kits_manifest(ViewerHandler._player_ctx)
        ViewerHandler._idk_kits_manifest = json.dumps(kits_manifest).encode("utf-8")
        print(f"Player API: {len(ViewerHandler._player_ctx.idks)} identity kits loaded")
        print(f"IDK catalog: {kits_manifest['count']} searchable body parts")
    except Exception as exc:
        ViewerHandler._player_ctx = None
        ViewerHandler._idk_manifest = None
        ViewerHandler._idk_kits_manifest = None
        print(f"Player API: FAILED ({exc})")

    try:
        ViewerHandler._sprite_ctx = build_sprite_context(cache)
        sprite_manifest = build_sprite_manifest(ViewerHandler._sprite_ctx)
        ViewerHandler._sprite_manifest = json.dumps(sprite_manifest).encode("utf-8")
        print(f"Sprite API: {sprite_manifest['sprites']}")
    except Exception as exc:
        ViewerHandler._sprite_ctx = None
        ViewerHandler._sprite_manifest = None
        print(f"Sprite API: FAILED ({exc})")

    try:
        ViewerHandler._font_ctx = build_font_context(cache)
        font_manifest = build_font_manifest(ViewerHandler._font_ctx)
        ViewerHandler._font_manifest = json.dumps(font_manifest).encode("utf-8")
        print(f"Font API: {font_manifest['fonts']}")
    except Exception as exc:
        ViewerHandler._font_ctx = None
        ViewerHandler._font_manifest = None
        print(f"Font API: FAILED ({exc})")

    try:
        ViewerHandler._iface_ctx = build_interface_render_context(cache)
        iface_manifest = build_interface_manifest(ViewerHandler._iface_ctx)
        ViewerHandler._iface_manifest = json.dumps(iface_manifest).encode("utf-8")
        print(f"Interface API: {iface_manifest['tabs']}")
    except Exception as exc:
        ViewerHandler._iface_ctx = None
        ViewerHandler._iface_manifest = None
        print(f"Interface API: FAILED ({exc})")

    try:
        ViewerHandler._tex_ctx = build_texture_context(cache)
        tex_manifest = build_texture_manifest(ViewerHandler._tex_ctx)
        ViewerHandler._tex_manifest = json.dumps(tex_manifest).encode("utf-8")
        print(f"Texture API: {tex_manifest['count']} ground/material textures")
    except Exception as exc:
        ViewerHandler._tex_ctx = None
        ViewerHandler._tex_manifest = None
        print(f"Texture API: FAILED ({exc})")

    load_sounds(cache)
    ViewerHandler._sounds_ready = True
    print(f"Sound bank: {sound_count()} effects (IDs 0–2726)")

    sounds_json = root / "outputs" / "unreal_exports" / "sounds.json"
    if not sounds_json.is_file():
        print("Tip: run  python -m src.cli.build_sound_index --wiki <wiki.md>  for searchable names")

    handler = lambda *a, **kw: ViewerHandler(*a, directory=str(root), **kw)
    server = ThreadingHTTPServer((args.host, args.port), handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
