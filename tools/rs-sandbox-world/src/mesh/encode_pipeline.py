"""Encode RS2 candidate JSON to model bytes with validation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.mesh.icon_readability import render_icon_previews
from src.preview.render_preview import export_obj, render_preview
from src.rs2.model_decoder import RSModel, decode_model
from src.rs2.model_encoder import encode_model, wrap_model_gzip


@dataclass
class EncodeResult:
    model: RSModel
    encoded: bytes
    decoded: RSModel
    gzip_path: Path | None = None
    preview_path: Path | None = None
    icon_paths: dict[int, Path] | None = None


def encode_rs_model(
    model: RSModel,
    out_path: Path,
    *,
    gzip_out: Path | None = None,
    preview_path: Path | None = None,
    obj_path: Path | None = None,
    icon_previews: bool = True,
) -> EncodeResult:
    encoded = encode_model(model)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(encoded)

    decoded = decode_model(model.model_id, encoded)
    if decoded is None:
        raise RuntimeError("Encoded model could not be decoded.")

    gzip_written = None
    if gzip_out is not None:
        gzip_out.parent.mkdir(parents=True, exist_ok=True)
        gzip_out.write_bytes(wrap_model_gzip(encoded))
        gzip_written = gzip_out

    preview_written = None
    icon_paths = None
    if preview_path is not None:
        render_preview(decoded, preview_path)
        preview_written = preview_path
        if icon_previews:
            icon_paths = render_icon_previews(decoded, preview_path.parent)

    if obj_path is not None:
        export_obj(decoded, obj_path)

    return EncodeResult(
        model=model,
        encoded=encoded,
        decoded=decoded,
        gzip_path=gzip_written,
        preview_path=preview_written,
        icon_paths=icon_paths,
    )


def print_validation_report(result: EncodeResult, out_path: Path, gzip_out: Path | None) -> None:
    decoded = result.decoded
    colors_ok = len(decoded.face_colors) == len(decoded.faces) and all(isinstance(c, int) for c in decoded.face_colors)

    print("Generated model validation")
    print(f"Vertices: {len(decoded.vertices)}")
    print(f"Faces: {len(decoded.faces)}")
    print(f"Colors: {'OK' if colors_ok else 'FAIL'}")
    print("Encode/decode: PASS")
    print(f"Output: {out_path}")
    if gzip_out is not None and result.gzip_path is not None:
        print(f"Gzip output: {result.gzip_path}")
    if result.preview_path is not None:
        print(f"Preview: {result.preview_path}")
