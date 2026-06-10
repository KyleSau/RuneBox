"""Icon-sized preview rendering and readability metrics."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image

from src.preview.render_preview import render_preview
from src.rs2.model_decoder import RSModel

ICON_SIZES = (128, 64, 32)
BG_COLOR = np.array([24, 20, 16], dtype=np.int16)
DARK_LUM = 40


@dataclass
class IconMetrics:
    bounding_box_fill_ratio: float = 0.0
    dark_pixel_ratio: float = 0.0
    contrast_score: float = 0.0
    edge_detail_score: float = 0.0
    thinness_score: float = 0.0
    longest_axis_ratio: float = 1.0
    silhouette_area_ratio: float = 0.0
    visible_color_cluster_count: int = 0
    color_clusters_32: int = 0
    color_clusters_64: int = 0
    warnings: list[str] = field(default_factory=list)

    # Backward-compatible alias used by older reports/tests.
    @property
    def icon_bbox_fill_ratio(self) -> float:
        return self.bounding_box_fill_ratio

    def to_dict(self) -> dict:
        data = asdict(self)
        data["icon_bbox_fill_ratio"] = self.bounding_box_fill_ratio
        return data


def render_icon_previews(model: RSModel, previews_dir: Path) -> dict[int, Path]:
    previews_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[int, Path] = {}
    for size in ICON_SIZES:
        path = previews_dir / f"icon_{size}.png"
        render_preview(model, path, width=size, height=size, camera_distance_scale=2.2)
        paths[size] = path
    return paths


def analyze_icon_image(path: Path) -> IconMetrics:
    img = np.array(Image.open(path).convert("RGB"))
    return _metrics_from_rgb(img)


def compute_icon_metrics(model: RSModel, previews_dir: Path | None = None) -> IconMetrics:
    if previews_dir is None:
        previews_dir = Path("previews")
    paths = render_icon_previews(model, previews_dir)
    m64 = analyze_icon_image(paths[64])
    m32 = analyze_icon_image(paths[32])
    m64.color_clusters_32 = m32.color_clusters_32
    m64.color_clusters_64 = _count_color_clusters(np.array(Image.open(paths[64]).convert("RGB")), 64)
    m64.visible_color_cluster_count = m64.color_clusters_64
    m64.warnings = _icon_warnings(m64, m32)
    return m64


def _metrics_from_rgb(img: np.ndarray) -> IconMetrics:
    h, w = img.shape[:2]
    fg_mask = ~_is_background(img)
    if not fg_mask.any():
        return IconMetrics(warnings=["icon empty — no foreground pixels"])

    fg = img[fg_mask]
    ys, xs = np.where(fg_mask)
    bbox_area = max(1, (xs.max() - xs.min() + 1) * (ys.max() - ys.min() + 1))
    bbox_fill = float(fg_mask.sum()) / float(bbox_area)

    lum = _luminance(fg)
    dark_ratio = float((lum < DARK_LUM).sum()) / float(len(lum))
    contrast = float(lum.std()) / 128.0

    gray = lum.reshape(-1)
    edge_score = min(1.0, float(np.std(np.diff(np.sort(gray)))) / 64.0) if len(gray) > 2 else 0.0

    bw = xs.max() - xs.min() + 1
    bh = ys.max() - ys.min() + 1
    thinness = min(bw, bh) / max(bw, bh, 1)
    axis_ratio = max(bw, bh) / max(min(bw, bh), 1)

    silhouette_area = float(fg_mask.sum()) / float(bbox_area)
    quantize = max(h, w)

    return IconMetrics(
        bounding_box_fill_ratio=round(bbox_fill, 4),
        dark_pixel_ratio=round(dark_ratio, 4),
        contrast_score=round(contrast, 4),
        edge_detail_score=round(edge_score, 4),
        thinness_score=round(thinness, 4),
        longest_axis_ratio=round(float(axis_ratio), 4),
        silhouette_area_ratio=round(silhouette_area, 4),
        visible_color_cluster_count=_count_color_clusters(img, quantize),
        color_clusters_64=_count_color_clusters(img, 64),
        color_clusters_32=_count_color_clusters(img, 32),
    )


def _icon_warnings(m64: IconMetrics, m32: IconMetrics | None = None) -> list[str]:
    warnings: list[str] = []
    if m64.dark_pixel_ratio > 0.55:
        warnings.append("icon too dark")
    if m64.thinness_score < 0.12 or m64.longest_axis_ratio > 8.0:
        warnings.append("silhouette too thin")
    if m64.contrast_score < 0.25:
        warnings.append("low contrast at 64x64")
    blob = m32 if m32 is not None else m64
    if blob.bounding_box_fill_ratio > 0.92 and blob.edge_detail_score < 0.08:
        warnings.append("collapses into blob at 32x32")
    if m64.longest_axis_ratio > 7.0:
        warnings.append("weapon profile too long/thin")
    return warnings


def _is_background(img: np.ndarray) -> np.ndarray:
    diff = np.abs(img.astype(np.int16) - BG_COLOR)
    return diff.sum(axis=2) < 25


def _luminance(rgb: np.ndarray) -> np.ndarray:
    return 0.2126 * rgb[:, 0] + 0.7152 * rgb[:, 1] + 0.0722 * rgb[:, 2]


def _count_color_clusters(img: np.ndarray, quantize: int) -> int:
    fg = img[~_is_background(img)]
    if len(fg) == 0:
        return 0
    q = (fg // (256 // max(2, quantize // 8))).astype(np.int32)
    keys = q[:, 0] * quantize * quantize + q[:, 1] * quantize + q[:, 2]
    return len(np.unique(keys))
