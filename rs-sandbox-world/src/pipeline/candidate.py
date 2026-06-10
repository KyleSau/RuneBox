"""Generate a single RS2 model candidate from a text prompt."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from src.ai.generator_backend import BackendNotConfiguredError, GenerationResult, get_backend
from src.ai.prompt_templates import build_prompt
from src.config import resolve_java_exe
from src.mesh.encode_pipeline import EncodeResult, encode_rs_model
from src.quality.report import score_candidate_dir
from src.mesh.importers import load_mesh
from src.mesh.reconstruct import StylerOptions
from src.mesh.rs_style import mesh_to_rs_model, save_rs2model_json
from src.pipeline.styler_options import build_styler_options
from src.preview.render_preview import render_trimesh_preview


@dataclass
class CandidateResult:
    run_dir: Path
    user_prompt: str
    full_prompt: str
    target: str
    backend: str
    metadata: dict
    encode: EncodeResult
    client_dev_path: Path | None
    dev_smoke_pass: bool | None


def slugify(text: str) -> str:
    slug = re.sub(r"[^\w\s-]", "", text.lower())
    slug = re.sub(r"[-\s]+", "_", slug).strip("_")
    return (slug[:48] or "generated").strip("_")


def ensure_layout(run_dir: Path, raw_mesh: Path) -> dict[str, Path]:
    raw_dir = run_dir / "raw"
    intermediate = run_dir / "intermediate"
    encoded = run_dir / "encoded"
    previews = run_dir / "previews"
    for d in (raw_dir, intermediate, encoded, previews):
        d.mkdir(parents=True, exist_ok=True)

    dest = raw_dir / raw_mesh.name
    if raw_mesh.resolve() != dest.resolve():
        shutil.copy2(raw_mesh, dest)
        for sidecar in raw_mesh.parent.glob(raw_mesh.stem + ".*"):
            if sidecar.suffix.lower() in {".mtl", ".png", ".jpg"}:
                shutil.copy2(sidecar, raw_dir / sidecar.name)

    return {
        "raw": raw_dir,
        "intermediate": intermediate,
        "encoded": encoded,
        "previews": previews,
    }


def run_dev_model_smoke(client_dir: Path, model_id: int) -> bool:
    from src.cache import java_bridge

    client_dir = client_dir.resolve()
    try:
        if client_dir == java_bridge.client_root().resolve():
            java_bridge.ensure_built()
            cp = java_bridge.classpath()
        else:
            classes = client_dir / "target" / "classes"
            cp_file = client_dir / "cp.txt"
            if not classes.is_dir():
                return False
            cp = str(classes)
            if cp_file.exists():
                cp = f"{cp};{cp_file.read_text(encoding='utf-8').strip()}"
    except Exception:
        return False

    result = subprocess.run(
        [resolve_java_exe(), "-cp", cp, "DevModelSmoke", str(model_id)],
        cwd=str(client_dir),
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def _save_raw_ai_preview(raw_mesh: Path, previews_dir: Path) -> str | None:
    """Render pre-stylizer AI mesh preview for gallery comparison."""
    try:
        imported = load_mesh(raw_mesh)
        out = previews_dir / "preview_raw.png"
        if render_trimesh_preview(imported.mesh, out):
            return str(out.resolve())
    except Exception:
        pass
    return None


def generate_candidate(
    user_prompt: str,
    target: str,
    backend_name: str,
    run_dir: Path,
    *,
    max_faces: int | None = None,
    model_id: int | None = None,
    client_dir: Path | None = None,
    copy_to_client: bool = False,
    skip_dev_smoke: bool = True,
    variant_index: int | None = None,
    styler: StylerOptions | None = None,
    score: bool = True,
) -> CandidateResult:
    run_dir = run_dir.resolve()
    raw_work_dir = run_dir / "_generation"
    raw_work_dir.mkdir(parents=True, exist_ok=True)

    user_prompt = user_prompt.strip()
    full_prompt = build_prompt(user_prompt, target)

    backend = get_backend(backend_name)
    gen: GenerationResult = backend.generate(full_prompt, raw_work_dir, image_path=None)

    (run_dir / "prompt.txt").write_text(user_prompt + "\n", encoding="utf-8")
    (run_dir / "full_prompt.txt").write_text(full_prompt + "\n", encoding="utf-8")

    styler_opts = styler or build_styler_options(ai_generated=True)
    layout = ensure_layout(run_dir, gen.raw_mesh_path)
    raw_mesh = layout["raw"] / gen.raw_mesh_path.name
    previews_dir = layout["previews"]
    raw_preview = _save_raw_ai_preview(raw_mesh, previews_dir) if styler_opts.ai_generated else None

    normalized = mesh_to_rs_model(
        raw_mesh,
        target,
        max_faces,
        styler=styler_opts,
        user_prompt=user_prompt,
        previews_dir=previews_dir,
    )
    json_path = layout["intermediate"] / "normalized.rs2model.json"
    save_rs2model_json(json_path, normalized.model, normalized.metadata)

    encoded_name = f"model_{model_id}.dat" if model_id is not None else "model.dat"
    gzip_name = f"model_{model_id}.dat.gz" if model_id is not None else "model.dat.gz"
    dat_path = layout["encoded"] / encoded_name
    gzip_path = layout["encoded"] / gzip_name
    preview_path = layout["previews"] / "preview.png"

    enc = encode_rs_model(
        normalized.model,
        dat_path,
        gzip_out=gzip_path,
        preview_path=preview_path,
    )

    client_dev_path: Path | None = None
    dev_smoke_pass: bool | None = None
    if copy_to_client and client_dir is not None and model_id is not None:
        client_dev_path = client_dir.resolve() / "dev-models" / gzip_name
        client_dev_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(gzip_path, client_dev_path)
        if not skip_dev_smoke:
            dev_smoke_pass = run_dev_model_smoke(client_dir, model_id)

    metadata = {
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "userPrompt": user_prompt,
        "fullPrompt": full_prompt,
        "target": target,
        "backend": gen.backend,
        "maxFaces": max_faces,
        "modelId": model_id,
        "variantIndex": variant_index,
        "rawMesh": str(raw_mesh.resolve()),
        "normalizedJson": str(json_path.resolve()),
        "encodedDat": str(dat_path.resolve()),
        "encodedGzip": str(gzip_path.resolve()),
        "preview": str(preview_path.resolve()),
        "previewRaw": raw_preview,
        "clientDevModel": str(client_dev_path.resolve()) if client_dev_path else None,
        "generation": gen.metadata,
        "normalizationWarnings": normalized.warnings,
        "repairActions": normalized.metadata.get("repairActions", []),
        "archetype": normalized.metadata.get("archetype"),
        "iconScoreBefore": normalized.metadata.get("iconScoreBefore"),
        "iconScoreAfter": normalized.metadata.get("iconScoreAfter"),
        "styler": normalized.metadata.get("styler"),
        "vertexCount": len(enc.decoded.vertices),
        "faceCount": len(enc.decoded.faces),
        "encodeDecodePass": True,
        "devSmokePass": dev_smoke_pass,
    }
    (run_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    if score:
        score_candidate_dir(run_dir)

    return CandidateResult(
        run_dir=run_dir,
        user_prompt=user_prompt,
        full_prompt=full_prompt,
        target=target,
        backend=gen.backend,
        metadata=metadata,
        encode=enc,
        client_dev_path=client_dev_path,
        dev_smoke_pass=dev_smoke_pass,
    )
