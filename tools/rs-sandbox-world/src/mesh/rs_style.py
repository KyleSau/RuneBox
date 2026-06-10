"""Convert generic meshes into RS2 candidate models with RS stylizer/reconstruction."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import trimesh

from src.mesh.cleanup import cleanup_mesh
from src.mesh.color_repair import repair_face_colors, repair_mesh_colors
from src.mesh.decimate import decimate_mesh
from src.mesh.icon_readability import compute_icon_metrics
from src.mesh.importers import load_mesh
from src.mesh.normalize import normalize_geometry
from src.mesh.profiles import get_asset_profile, profile_to_target_profile
from src.mesh.quantize import quantize_face_colors
from src.mesh.reconstruct import StylerOptions, StylerReport, apply_pre_normalize_stylizer, build_primitive_weapon, save_reconstructed_preview
from src.mesh.silhouette import thicken_silhouette
from src.mesh.weapon_rebuilder import can_rebuild, infer_archetype
from src.quality.icon_score import score_icon_metrics
from src.rs2.model_decoder import RSModel


@dataclass
class NormalizeResult:
    model: RSModel
    warnings: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    styler_report: StylerReport | None = None


def mesh_to_rs_model(
    input_path: Path,
    target: str,
    max_faces: int | None = None,
    *,
    styler: StylerOptions | None = None,
    user_prompt: str = "",
    previews_dir: Path | None = None,
) -> NormalizeResult:
    opts = styler or StylerOptions.for_roundtrip()
    imported = load_mesh(input_path)
    return _finalize_rs_model(
        imported.mesh,
        list(imported.warnings),
        target,
        max_faces,
        opts=opts,
        user_prompt=user_prompt,
        previews_dir=previews_dir,
        source=str(input_path.resolve()),
    )


def trimesh_to_rs_model(
    target: str,
    max_faces: int | None = None,
    *,
    styler: StylerOptions | None = None,
    user_prompt: str = "",
    previews_dir: Path | None = None,
    archetype: str | None = None,
) -> NormalizeResult:
    """Encode a procedural mesh without reading AI geometry from disk."""
    opts = styler or StylerOptions.for_roundtrip()
    arch = archetype or infer_archetype(user_prompt, None if opts.archetype == "auto" else opts.archetype)
    if not arch:
        raise ValueError("archetype required for trimesh_to_rs_model")
    mesh, _, report_seed = build_primitive_weapon(arch, target, options=opts)
    result = _finalize_rs_model(
        mesh,
        [],
        target,
        max_faces,
        opts=opts,
        user_prompt=user_prompt,
        previews_dir=previews_dir,
        source=f"procedural:{arch}",
        prebuilt_report=report_seed,
    )
    return result


def _finalize_rs_model(
    mesh: trimesh.Trimesh,
    import_warnings: list[str],
    target: str,
    max_faces: int | None,
    *,
    opts: StylerOptions,
    user_prompt: str,
    previews_dir: Path | None,
    source: str,
    prebuilt_report: StylerReport | None = None,
) -> NormalizeResult:
    warnings = list(import_warnings)

    mesh, w1 = cleanup_mesh(mesh)
    warnings.extend(w1)

    profile = get_asset_profile(target)
    report = prebuilt_report or StylerReport()

    if prebuilt_report is None and (
        opts.reconstruct != "off" or opts.repair_silhouette or opts.ai_generated or opts.primitive_only
    ):
        mesh, profile, report = apply_pre_normalize_stylizer(mesh, target, opts, user_prompt)

    archetype = report.archetype or infer_archetype(user_prompt, None if opts.archetype == "auto" else opts.archetype)
    budget = max_faces if max_faces is not None else profile.max_faces_default
    preserve_palette = report.primitive_reconstruction or opts.primitive_only

    post_cleanup_mesh = mesh.copy()

    def _pipeline(source_mesh: trimesh.Trimesh) -> tuple[RSModel, list[str]]:
        local_w: list[str] = []
        m, dw = decimate_mesh(source_mesh, budget)
        local_w.extend(dw)
        tp = profile_to_target_profile(profile)
        m, nw = normalize_geometry(m, tp)
        local_w.extend(nw)
        face_colors = quantize_face_colors(
            m,
            tp.name,
            local_w,
            profile=profile,
            repair=opts.repair_colors,
            preserve_palette=preserve_palette,
        )
        if opts.repair_colors and not preserve_palette:
            face_colors, cw = repair_face_colors(
                face_colors,
                profile=profile,
                target_colors=opts.target_colors or profile.target_colors,
            )
            local_w.extend(cw)
        model = RSModel(
            model_id=-1,
            vertices=np.asarray(m.vertices, dtype=np.int32).tolist(),
            faces=np.asarray(m.faces, dtype=np.int32).tolist(),
            face_colors=face_colors,
            priority=0,
        )
        return model, local_w

    model, pipe_warnings = _pipeline(mesh)
    warnings.extend(pipe_warnings)

    if opts.icon_check and previews_dir is not None:
        model, report = _icon_repair_loop(
            model,
            mesh=post_cleanup_mesh,
            rebuilt_mesh=mesh,
            target=target,
            opts=opts,
            profile=profile,
            report=report,
            archetype=archetype,
            budget=budget,
            previews_dir=previews_dir,
            pipeline_fn=_pipeline,
        )
        warnings.extend(report.warnings)

    metadata = {
        "source": source,
        "format": "rs2model-candidate-v1",
        "target": target,
        "targetExtent": profile.target_extent,
        "maxFaces": budget,
        "vertexCount": len(model.vertices),
        "faceCount": len(model.faces),
        "globalPriority": 0,
        "warnings": warnings,
        "stubProfile": profile.stub,
        "archetype": archetype,
        "primitiveReconstruction": report.primitive_reconstruction,
        "rawAiMeshUsedAsGeometry": report.raw_ai_mesh_used_as_geometry,
        "styler": {
            "reconstruct": opts.reconstruct,
            "repairColors": opts.repair_colors,
            "repairSilhouette": opts.repair_silhouette,
            "iconCheck": opts.icon_check,
            "forceReadableIcon": opts.force_readable_icon,
            "primitiveOnly": opts.primitive_only,
        },
        "repairActions": report.repair_actions,
        "iconScoreBefore": report.icon_score_before,
        "iconScoreAfter": report.icon_score_after,
    }

    return NormalizeResult(model=model, warnings=warnings, metadata=metadata, styler_report=report)


def _icon_repair_loop(
    model: RSModel,
    *,
    mesh: trimesh.Trimesh,
    rebuilt_mesh: trimesh.Trimesh,
    target: str,
    opts: StylerOptions,
    profile,
    report: StylerReport,
    archetype: str | None,
    budget: int,
    previews_dir: Path,
    pipeline_fn,
) -> tuple[RSModel, StylerReport]:
    icon_m = compute_icon_metrics(model, previews_dir)
    icon_score = score_icon_metrics(icon_m, profile)
    report.icon_score_before = icon_score.score
    report.warnings.extend(icon_m.warnings)

    if icon_score.score >= 70 and not opts.force_readable_icon:
        report.icon_score_after = icon_score.score
        return model, report

    # 1. Color repair on existing model
    if opts.repair_colors:
        repaired, cw = repair_face_colors(
            model.face_colors,
            profile=profile,
            target_colors=opts.target_colors or profile.target_colors,
        )
        if repaired != model.face_colors:
            model = RSModel(
                model_id=model.model_id,
                vertices=model.vertices,
                faces=model.faces,
                face_colors=repaired,
                priority=model.priority,
            )
            report.repair_actions.extend(cw)
            icon_m = compute_icon_metrics(model, previews_dir)
            icon_score = score_icon_metrics(icon_m, profile)
            if icon_score.score >= 70:
                report.icon_score_after = icon_score.score
                return model, report

    # 2. Silhouette thickening
    if opts.repair_silhouette:
        thickened, sw = thicken_silhouette(
            rebuilt_mesh,
            min_thickness_ratio=profile.min_thickness_ratio,
            max_axis_ratio=profile.max_axis_ratio,
        )
        if sw:
            report.repair_actions.extend(sw)
            model, _ = pipeline_fn(thickened)
            icon_m = compute_icon_metrics(model, previews_dir)
            icon_score = score_icon_metrics(icon_m, profile)
            if icon_score.score >= 70:
                report.icon_score_after = icon_score.score
                return model, report

    # 3. Archetype primitive reconstruction
    if target == "weapon" and can_rebuild(archetype) and (not report.used_primitive or opts.force_readable_icon):
        primitive, _, prim_report = build_primitive_weapon(archetype, target)
        report.repair_actions.extend(prim_report.repair_actions)
        report.used_primitive = True
        report.reconstructed = True
        report.primitive_reconstruction = True
        report.raw_ai_mesh_used_as_geometry = False
        recon_path = previews_dir.parent / "intermediate" / "reconstructed.glb"
        save_reconstructed_preview(primitive, recon_path)
        model, _ = pipeline_fn(primitive)
        icon_m = compute_icon_metrics(model, previews_dir)
        icon_score = score_icon_metrics(icon_m, profile)
        report.icon_score_after = icon_score.score
        return model, report

    report.icon_score_after = icon_score.score
    return model, report


def rs_model_to_json_dict(model: RSModel, metadata: dict | None = None) -> dict:
    payload = model.to_json_dict()
    payload["metadata"].update(metadata or {})
    payload["metadata"]["format"] = "rs2model-candidate-v1"
    return payload


def save_rs2model_json(path: Path, model: RSModel, metadata: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rs_model_to_json_dict(model, metadata), indent=2), encoding="utf-8")


def load_rs2model_json(path: Path) -> tuple[RSModel, dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    meta = data.get("metadata", {})
    priority = meta.get("globalPriority")
    if priority is None:
        priority = 0

    model = RSModel(
        model_id=int(data.get("modelId", -1)),
        vertices=[list(map(int, v)) for v in data["vertices"]],
        faces=[list(map(int, f)) for f in data["faces"]],
        face_colors=[int(c) for c in data["faceColors"]],
        face_infos=_optional_int_list(data.get("faceInfos") or data.get("faceRenderTypes")),
        face_priorities=_optional_int_list(data.get("facePriorities")),
        face_alphas=_optional_int_list(data.get("faceAlphas")),
        vertex_skins=_optional_int_list(data.get("vertexSkins")),
        face_skins=_optional_int_list(data.get("faceSkins")),
        textured_faces=[list(map(int, t)) for t in data.get("texturedFaces", [])],
        priority=int(priority),
    )
    return model, meta


def _optional_int_list(value) -> list[int] | None:
    if value is None:
        return None
    return [int(v) for v in value]
