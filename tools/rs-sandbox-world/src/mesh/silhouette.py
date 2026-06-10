"""Silhouette analysis and thickness repair for RS icon readability."""

from __future__ import annotations

import numpy as np
import trimesh


def principal_axes(mesh: trimesh.Trimesh) -> tuple[np.ndarray, np.ndarray]:
    """Return (centroid, 3x3 axis matrix columns = principal directions)."""
    verts = np.asarray(mesh.vertices, dtype=np.float64)
    center = verts.mean(axis=0)
    centered = verts - center
    if len(centered) < 3:
        return center, np.eye(3)
    cov = np.cov(centered.T)
    eigvals, eigvecs = np.linalg.eigh(cov)
    order = np.argsort(eigvals)[::-1]
    axes = eigvecs[:, order]
    return center, axes


def bbox_extents_along_axes(mesh: trimesh.Trimesh) -> tuple[float, float, float]:
    extents = mesh.bounds[1] - mesh.bounds[0]
    sorted_ext = sorted(float(x) for x in extents)
    return sorted_ext[0], sorted_ext[1], sorted_ext[2]


def analyze_silhouette(mesh: trimesh.Trimesh) -> dict[str, float]:
    thin, mid, long = bbox_extents_along_axes(mesh)
    ratio = long / thin if thin > 1e-8 else float("inf")
    return {
        "min_extent": thin,
        "mid_extent": mid,
        "max_extent": long,
        "longest_axis_ratio": ratio,
        "thickness_ratio": thin / long if long > 1e-8 else 0.0,
    }


def thicken_silhouette(
    mesh: trimesh.Trimesh,
    *,
    min_thickness_ratio: float = 0.08,
    max_axis_ratio: float = 8.0,
) -> tuple[trimesh.Trimesh, list[str]]:
    """Scale thickness axes so the model is chunky enough for RS icons."""
    warnings: list[str] = []
    work = mesh.copy()
    stats = analyze_silhouette(work)
    long = stats["max_extent"]
    thin = stats["min_extent"]
    mid = stats["mid_extent"]

    if long < 1e-8:
        return work, warnings

    min_thick = long * min_thickness_ratio
    scales = np.ones(3, dtype=np.float64)
    extents = work.bounds[1] - work.bounds[0]

    for axis in range(3):
        if extents[axis] < min_thick and extents[axis] > 1e-8:
            scales[axis] = min_thick / extents[axis]

    # If still too thin relative to longest bbox axis, scale Y/Z uniformly from center.
    new_extents = extents * scales
    thin_new = float(min(new_extents))
    if thin_new / long < min_thickness_ratio:
        boost = (long * min_thickness_ratio) / max(thin_new, 1e-8)
        for axis in range(3):
            if axis != int(np.argmax(extents)):
                scales[axis] *= boost

    if stats["longest_axis_ratio"] > max_axis_ratio:
        # Compress longest axis slightly while keeping thickness.
        longest_axis = int(np.argmax(extents))
        target_long = thin * max_axis_ratio if thin > 1e-8 else long
        if extents[longest_axis] > target_long:
            scales[longest_axis] = target_long / extents[longest_axis]
            warnings.append(f"compressed longest axis to ratio {max_axis_ratio:.1f}")

    if not np.allclose(scales, 1.0):
        center = work.centroid
        transform = np.eye(4)
        transform[:3, 3] = -center
        work.apply_transform(transform)
        scale_mat = np.diag([scales[0], scales[1], scales[2], 1.0])
        work.apply_transform(scale_mat)
        work.apply_translation(center)
        max_scale = float(np.max(scales))
        if max_scale > 1.01:
            warnings.append(f"increased thickness axis by {max_scale:.2f}x")

    return work, warnings
