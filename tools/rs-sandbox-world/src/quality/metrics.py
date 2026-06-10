"""Compute geometry and pipeline metrics for a generated candidate."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

from src.mesh.normalize import get_target_profile
from src.mesh.profiles import get_asset_profile
from src.mesh.rs_style import load_rs2model_json
from src.rs2.model_decoder import decode_model, prepare_model_bytes


@dataclass
class ModelMetrics:
    candidate_dir: str
    target: str
    backend: str
    user_prompt: str

    vertex_count: int = 0
    face_count: int = 0
    unique_face_colors: int = 0
    bbox_size: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    longest_axis_ratio: float = 1.0
    degenerate_removed_pct: float = 0.0
    avg_triangle_area: float = 0.0
    silhouette_proxy: float = 0.0

    encode_decode_pass: bool = False
    dev_smoke_pass: bool | None = None

    normalization_warnings: list[str] = field(default_factory=list)
    texture_detail_dropped: bool = False

    bounding_box_fill_ratio: float = 0.0
    dark_pixel_ratio: float = 0.0
    contrast_score: float = 0.0
    silhouette_area_ratio: float = 0.0
    icon_longest_axis_ratio: float = 0.0
    visible_color_cluster_count: int = 0
    icon_readability_score: int | None = None
    icon_warnings: list[str] = field(default_factory=list)

    @property
    def icon_bbox_fill_ratio(self) -> float:
        return self.bounding_box_fill_ratio
    repair_actions: list[str] = field(default_factory=list)
    archetype: str | None = None
    primitive_reconstruction: bool = False
    raw_ai_mesh_used_as_geometry: bool | None = None

    def to_dict(self) -> dict:
        data = asdict(self)
        data["icon_bbox_fill_ratio"] = self.bounding_box_fill_ratio
        return data


def load_prompt_lines(path: Path) -> list[str]:
    lines: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        lines.append(text)
    if not lines:
        raise ValueError(f"No prompts found in {path}")
    return lines


def discover_candidates(root: Path) -> list[Path]:
    """Find candidate directories containing metadata.json."""
    root = root.resolve()
    found: list[Path] = []

    if (root / "metadata.json").is_file():
        return [root]

    for meta in root.rglob("metadata.json"):
        parent = meta.parent
        if parent.name.startswith("_"):
            continue
        if (parent / "previews" / "preview.png").is_file() or (parent / "encoded").is_dir():
            found.append(parent)

    # Batch layout: candidates/*/
    candidates_dir = root / "candidates"
    if candidates_dir.is_dir():
        for child in sorted(candidates_dir.iterdir()):
            if child.is_dir() and (child / "metadata.json").is_file():
                if child not in found:
                    found.append(child)

    found.sort(key=lambda p: str(p).lower())
    return found


def compute_metrics(candidate_dir: Path) -> ModelMetrics:
    candidate_dir = candidate_dir.resolve()
    meta_path = candidate_dir / "metadata.json"
    if not meta_path.is_file():
        raise FileNotFoundError(f"No metadata.json in {candidate_dir}")

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    target = meta.get("target", "object")
    warnings = list(meta.get("normalizationWarnings") or [])

    metrics = ModelMetrics(
        candidate_dir=str(candidate_dir),
        target=target,
        backend=str(meta.get("backend", "")),
        user_prompt=str(meta.get("userPrompt", "")),
        vertex_count=int(meta.get("vertexCount", 0)),
        face_count=int(meta.get("faceCount", 0)),
        encode_decode_pass=bool(meta.get("encodeDecodePass", False)),
        dev_smoke_pass=meta.get("devSmokePass"),
        normalization_warnings=warnings,
        texture_detail_dropped=_has_texture_warning(warnings),
        repair_actions=list(meta.get("repairActions") or []),
        archetype=meta.get("archetype"),
        primitive_reconstruction=bool(meta.get("primitiveReconstruction")),
        raw_ai_mesh_used_as_geometry=meta.get("rawAiMeshUsedAsGeometry"),
        icon_readability_score=meta.get("iconScoreAfter") or meta.get("iconScoreBefore"),
    )

    json_path = candidate_dir / "intermediate" / "normalized.rs2model.json"
    if json_path.is_file():
        model, _ = load_rs2model_json(json_path)
        _fill_geometry_metrics(metrics, model.vertices, model.faces, model.face_colors)
    else:
        dat_path = _find_dat(candidate_dir, meta)
        if dat_path is not None:
            raw = prepare_model_bytes(dat_path.read_bytes())
            decoded = decode_model(-1, raw)
            if decoded is not None:
                metrics.encode_decode_pass = True
                _fill_geometry_metrics(metrics, decoded.vertices, decoded.faces, decoded.face_colors)

    metrics.degenerate_removed_pct = _parse_degenerate_pct(warnings, metrics.face_count)
    if not metrics.encode_decode_pass:
        metrics.encode_decode_pass = _verify_dat_decode(candidate_dir, meta)

    _fill_icon_metrics(candidate_dir, metrics, meta)

    return metrics


def _find_dat(candidate_dir: Path, meta: dict) -> Path | None:
    for key in ("encodedDat",):
        if meta.get(key):
            p = Path(meta[key])
            if p.is_file():
                return p
    encoded = candidate_dir / "encoded"
    if encoded.is_dir():
        dats = sorted(encoded.glob("*.dat"))
        if dats:
            return dats[0]
    return None


def _verify_dat_decode(candidate_dir: Path, meta: dict) -> bool:
    dat = _find_dat(candidate_dir, meta)
    if dat is None:
        return False
    raw = prepare_model_bytes(dat.read_bytes())
    return decode_model(-1, raw) is not None


def _has_texture_warning(warnings: list[str]) -> bool:
    joined = " ".join(warnings).lower()
    return any(
        k in joined
        for k in ("texture", "textured mesh", "material texture", "uv", "pbr")
    )


def _parse_degenerate_pct(warnings: list[str], face_count: int) -> float:
    for w in warnings:
        if "Removed" in w and "degenerate" in w.lower():
            # "Removed 3 degenerate faces."
            parts = w.split()
            for i, part in enumerate(parts):
                if part.isdigit() and i > 0 and parts[i - 1].lower() == "removed":
                    removed = int(part)
                    total = face_count + removed
                    return round(100.0 * removed / total, 2) if total else 0.0
    return 0.0


def _fill_geometry_metrics(
    metrics: ModelMetrics,
    vertices: list[list[int]],
    faces: list[list[int]],
    face_colors: list[int],
) -> None:
    if not vertices or not faces:
        return

    verts = np.asarray(vertices, dtype=np.float64)
    metrics.vertex_count = len(verts)
    metrics.face_count = len(faces)
    metrics.unique_face_colors = len(set(face_colors))

    mins = verts.min(axis=0)
    maxs = verts.max(axis=0)
    extents = maxs - mins
    metrics.bbox_size = [float(x) for x in extents]

    sorted_ext = sorted(extents)
    if sorted_ext[0] > 1e-6:
        metrics.longest_axis_ratio = float(sorted_ext[2] / sorted_ext[0])
    else:
        metrics.longest_axis_ratio = float("inf")

    metrics.avg_triangle_area = _avg_triangle_area(verts, faces)
    metrics.silhouette_proxy = _silhouette_proxy(verts, faces)


def _avg_triangle_area(verts: np.ndarray, faces: list[list[int]]) -> float:
    areas: list[float] = []
    for a, b, c in faces:
        va, vb, vc = verts[a], verts[b], verts[c]
        areas.append(0.5 * float(np.linalg.norm(np.cross(vb - va, vc - va))))
    return float(np.mean(areas)) if areas else 0.0


def _silhouette_proxy(verts: np.ndarray, faces: list[list[int]]) -> float:
    """0–1 fill ratio of vertex XY projection vs bbox (higher = chunkier silhouette)."""
    if len(verts) < 3:
        return 0.0

    scores: list[float] = []
    for axis_pair in ((0, 1), (0, 2), (1, 2)):
        proj = verts[:, axis_pair]
        mins = proj.min(axis=0)
        maxs = proj.max(axis=0)
        span = maxs - mins
        bbox_area = float(span[0] * span[1])
        if bbox_area < 1e-6:
            continue
        # Convex hull area approximation via unique boundary vertices in projection.
        hull_area = _convex_hull_area_2d(proj)
        scores.append(min(1.0, hull_area / bbox_area))
    return float(np.mean(scores)) if scores else 0.0


def _convex_hull_area_2d(points: np.ndarray) -> float:
    pts = np.unique(points, axis=0)
    if len(pts) < 3:
        return 0.0
    hull = _monotone_chain(pts)
    if len(hull) < 3:
        return 0.0
    area = 0.0
    for i in range(len(hull)):
        j = (i + 1) % len(hull)
        area += hull[i][0] * hull[j][1] - hull[j][0] * hull[i][1]
    return abs(area) * 0.5


def _monotone_chain(points: np.ndarray) -> list[np.ndarray]:
    pts = sorted(points, key=lambda p: (p[0], p[1]))

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[np.ndarray] = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper: list[np.ndarray] = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def target_extent(target: str) -> float:
    return get_asset_profile(target).target_extent


def _apply_icon_metrics(metrics: ModelMetrics, icon_m) -> None:
    metrics.bounding_box_fill_ratio = icon_m.bounding_box_fill_ratio
    metrics.dark_pixel_ratio = icon_m.dark_pixel_ratio
    metrics.contrast_score = icon_m.contrast_score
    metrics.silhouette_area_ratio = icon_m.silhouette_area_ratio
    metrics.icon_longest_axis_ratio = icon_m.longest_axis_ratio
    metrics.visible_color_cluster_count = icon_m.visible_color_cluster_count
    metrics.icon_warnings = icon_m.warnings


def _fill_icon_metrics(candidate_dir: Path, metrics: ModelMetrics, meta: dict) -> None:
    json_path = candidate_dir / "intermediate" / "normalized.rs2model.json"
    previews_dir = candidate_dir / "previews"

    if json_path.is_file():
        from src.mesh.icon_readability import compute_icon_metrics
        from src.mesh.profiles import get_asset_profile
        from src.mesh.rs_style import load_rs2model_json
        from src.quality.icon_score import score_icon_metrics

        model, _ = load_rs2model_json(json_path)
        icon_m = compute_icon_metrics(model, previews_dir)
        _apply_icon_metrics(metrics, icon_m)
        profile = get_asset_profile(metrics.target, metrics.archetype)
        if metrics.icon_readability_score is None:
            metrics.icon_readability_score = score_icon_metrics(icon_m, profile).score
    else:
        icon64 = previews_dir / "icon_64.png"
        if icon64.is_file():
            from src.mesh.icon_readability import analyze_icon_image
            from src.mesh.profiles import get_asset_profile
            from src.quality.icon_score import score_icon_metrics

            icon_m = analyze_icon_image(icon64)
            _apply_icon_metrics(metrics, icon_m)
            profile = get_asset_profile(metrics.target, metrics.archetype)
            if metrics.icon_readability_score is None:
                metrics.icon_readability_score = score_icon_metrics(icon_m, profile).score

    qpath = candidate_dir / "quality_score.json"
    if qpath.is_file():
        q = json.loads(qpath.read_text(encoding="utf-8"))
        icon = q.get("iconScore", {})
        if icon:
            metrics.icon_readability_score = icon.get("score", metrics.icon_readability_score)
            metrics.icon_warnings = icon.get("warnings", metrics.icon_warnings)
            im = q.get("iconMetrics", {})
            if im:
                metrics.bounding_box_fill_ratio = im.get(
                    "bounding_box_fill_ratio",
                    im.get("icon_bbox_fill_ratio", metrics.bounding_box_fill_ratio),
                )
                metrics.dark_pixel_ratio = im.get("dark_pixel_ratio", metrics.dark_pixel_ratio)
                metrics.contrast_score = im.get("contrast_score", metrics.contrast_score)
                metrics.silhouette_area_ratio = im.get("silhouette_area_ratio", metrics.silhouette_area_ratio)
                metrics.icon_longest_axis_ratio = im.get("longest_axis_ratio", metrics.icon_longest_axis_ratio)
                metrics.visible_color_cluster_count = im.get(
                    "visible_color_cluster_count", metrics.visible_color_cluster_count
                )
