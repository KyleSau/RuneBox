"""Face budget reduction for RS-style low-poly meshes."""

from __future__ import annotations

import numpy as np
import trimesh


def decimate_mesh(mesh: trimesh.Trimesh, max_faces: int) -> tuple[trimesh.Trimesh, list[str]]:
    warnings: list[str] = []
    if len(mesh.faces) <= max_faces:
        return mesh.copy(), warnings

    target = max(4, int(max_faces))
    work = mesh.copy()
    source_colors = _copy_face_colors(work)

    try:
        simplified = work.simplify_quadric_decimation(face_count=target)
        if len(simplified.faces) <= target * 1.05:
            warnings.append(f"Decimated {len(mesh.faces)} → {len(simplified.faces)} faces (quadric).")
            simplified.remove_unreferenced_vertices()
            _restore_face_colors(mesh, simplified, source_colors)
            return simplified, warnings
    except Exception as exc:
        warnings.append(f"Quadric decimation unavailable ({exc}); using fallback subsample.")

    return _fallback_decimate(work, target, source_colors), warnings


def _copy_face_colors(mesh: trimesh.Trimesh) -> np.ndarray | None:
    colors = getattr(mesh.visual, "face_colors", None)
    if colors is None or len(mesh.faces) == 0:
        return None
    arr = np.asarray(colors)
    if len(arr) < len(mesh.faces):
        return None
    return arr[: len(mesh.faces)].copy()


def _restore_face_colors(
    source: trimesh.Trimesh,
    decimated: trimesh.Trimesh,
    source_colors: np.ndarray | None,
) -> None:
    """Map decimated faces to nearest source face color by centroid."""
    if source_colors is None or len(source.faces) == 0 or len(decimated.faces) == 0:
        return

    src_centroids = source.triangles_center
    dst_centroids = decimated.triangles_center
    # Nearest source face per decimated face (chunked for large meshes).
    mapped = np.empty((len(decimated.faces), 4), dtype=np.uint8)
    chunk = 512
    for start in range(0, len(dst_centroids), chunk):
        end = min(start + chunk, len(dst_centroids))
        diff = dst_centroids[start:end, np.newaxis, :] - src_centroids[np.newaxis, :, :]
        dist = np.sum(diff * diff, axis=2)
        nearest = np.argmin(dist, axis=1)
        mapped[start:end] = source_colors[nearest]

    decimated.visual.face_colors = mapped


def _fallback_decimate(
    mesh: trimesh.Trimesh,
    max_faces: int,
    source_colors: np.ndarray | None = None,
) -> trimesh.Trimesh:
    """Uniform face subsample when fast_simplification is missing."""
    if len(mesh.faces) <= max_faces:
        return mesh

    step = max(1, len(mesh.faces) // max_faces)
    keep_idx = np.arange(0, len(mesh.faces), step)[:max_faces]
    faces = mesh.faces[keep_idx]
    out = trimesh.Trimesh(vertices=mesh.vertices.copy(), faces=faces, process=False)

    if source_colors is not None and len(source_colors) == len(mesh.faces):
        out.visual.face_colors = source_colors[keep_idx]
    elif hasattr(mesh.visual, "face_colors") and mesh.visual.face_colors is not None:
        colors = np.asarray(mesh.visual.face_colors)
        if len(colors) == len(mesh.faces):
            out.visual.face_colors = colors[keep_idx]

    out.remove_unreferenced_vertices()
    return out
