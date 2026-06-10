"""Mesh cleanup: triangulate, remove degenerates, merge vertices."""

from __future__ import annotations

import numpy as np
import trimesh


def cleanup_mesh(mesh: trimesh.Trimesh) -> tuple[trimesh.Trimesh, list[str]]:
    warnings: list[str] = []
    work = mesh.copy()

    if not work.is_winding_consistent:
        trimesh.repair.fix_winding(work)
        warnings.append("Fixed inconsistent face winding.")

    if len(work.faces) > 0 and work.faces.shape[1] != 3:
        work = work.triangulate()
        warnings.append("Triangulated non-triangle faces.")

    # Remove zero-area faces.
    areas = work.area_faces
    keep = areas > 1e-12
    if not np.all(keep):
        work.update_faces(keep)
        warnings.append(f"Removed {(~keep).sum()} degenerate faces.")

    work.remove_unreferenced_vertices()
    work.merge_vertices(digits_vertex=6)
    work.remove_unreferenced_vertices()

    if len(work.vertices) == 0 or len(work.faces) == 0:
        raise ValueError("Mesh is empty after cleanup.")

    return work, warnings
