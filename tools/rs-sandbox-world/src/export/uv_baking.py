"""Planar UV baking for RS textured faces.

Old-school RS models do not store UVs. Textured faces reference a ``PQR``
vertex triple (origin ``P`` plus axes towards ``Q`` and ``R``) that defines the
texture plane. We project each face vertex onto that basis with a small
least-squares solve to recover stable per-vertex UVs.
"""

from __future__ import annotations

import numpy as np


def planar_uvs(
    vertices: list[list[int]],
    p: int,
    q: int,
    r: int,
    a: int,
    b: int,
    c: int,
) -> tuple[tuple[float, float], tuple[float, float], tuple[float, float]]:
    """Return UVs for face vertices (a, b, c) using the PQR texture basis."""
    origin = np.asarray(vertices[p], dtype=np.float64)
    e1 = np.asarray(vertices[q], dtype=np.float64) - origin
    e2 = np.asarray(vertices[r], dtype=np.float64) - origin

    g11 = float(e1 @ e1)
    g12 = float(e1 @ e2)
    g22 = float(e2 @ e2)
    det = g11 * g22 - g12 * g12
    if abs(det) < 1e-9:
        raise ValueError("degenerate texture basis")

    def solve(idx: int) -> tuple[float, float]:
        d = np.asarray(vertices[idx], dtype=np.float64) - origin
        b1 = float(e1 @ d)
        b2 = float(e2 @ d)
        u = (g22 * b1 - g12 * b2) / det
        v = (g11 * b2 - g12 * b1) / det
        return (u, v)

    return solve(a), solve(b), solve(c)
