"""Loc GLB rotation must match 317 LocType.getModel (no horizontal mirror)."""

from __future__ import annotations

from src.export.loc_glb import _transform
from src.rs2.loc_decoder import LocType


def _point(verts: list[list[int]]) -> tuple[int, int, int]:
    return tuple(verts[0])


def _loc(**kwargs) -> LocType:
    base = dict(
        id=1,
        name="test",
        examine="",
        debug_name="",
        model_kinds=[10],
        model_ids=[1],
        size_x=1,
        size_z=1,
        invert=False,
        scale_x=128,
        scale_y=128,
        scale_z=128,
        translate_x=0,
        translate_y=0,
        translate_z=0,
        seq_id=-1,
        actions=[None] * 5,
        src_color=[],
        dst_color=[],
    )
    base.update(kwargs)
    return LocType(**base)


def test_rotation_matches_java_not_mirrored():
    """rot 1 and rot 3 must differ (old (4-rot)%4 mirror swapped them)."""
    loc = _loc()
    v0 = [[100, 0, 0]]
    v1 = [[100, 0, 0]]
    v3 = [[100, 0, 0]]
    _transform(v0, loc, 0)
    _transform(v1, loc, 1)
    _transform(v3, loc, 3)
    assert _point(v0) == (100, 0, 0)
    assert _point(v1) == (0, 0, -100)
    assert _point(v3) == (0, 0, 100)
    assert _point(v1) != _point(v3)


def test_rotation_above_three_flips_when_inverted():
    loc = _loc(invert=True)
    v = [[100, 0, 0]]
    _transform(v, loc, 4)
    assert _point(v) == (100, 0, 0)


def test_rotate_y180_negates_z_only():
    from src.export.loc_glb import _rotate_y180

    v = [[10, 20, 30]]
    _rotate_y180(v)
    assert _point(v) == (10, 20, -30)


def test_rot1_faces_north_after_y_up_export():
    """317 rot 1 wall must extend +Z after (x,-y,-z) export, not -Z."""
    from src.export.loc_glb import _transform
    from src.export.mesh_assembly import _scaled_y_up

    loc = _loc()
    v = [[100, 0, 0]]
    _transform(v, loc, 1)
    x, y, z = _scaled_y_up(v[0], 128, 128)
    assert z > 0, f"rot 1 should face +Z, got {z}"
    assert abs(x) < abs(z)
