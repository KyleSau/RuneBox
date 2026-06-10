"""Offline PNG preview of decoded RS models."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pyrender
import trimesh

from src.rs2.model_decoder import RSModel
from src.rs2.palette import build_palette, hsl_to_rgb


def _face_color_rgba(model: RSModel, face_index: int, palette: list[int]) -> tuple[int, int, int, int]:
    color = model.face_colors[face_index]
    info = model.face_infos[face_index] if model.face_infos else 0

    if color == 65535:
        return (180, 180, 180, 255)

    if info is not None and (info & 2) == 2:
        # Textured face — neutral placeholder until texture decode exists.
        return (160, 140, 120, 255)

    r, g, b = hsl_to_rgb(color, palette)
    return (r, g, b, 255)


def model_to_trimesh(model: RSModel, flat_shaded: bool = True) -> trimesh.Trimesh:
    palette = build_palette()
    vertices = np.array(model.vertices, dtype=np.float64)
    faces = np.array(model.faces, dtype=np.int64)

    face_colors = np.array(
        [_face_color_rgba(model, i, palette) for i in range(len(model.faces))],
        dtype=np.uint8,
    )

    mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
    if flat_shaded:
        mesh = mesh.submesh([np.arange(len(faces))], append=True)
        mesh.visual.face_colors = face_colors
    else:
        mesh.visual.vertex_colors = np.tile(np.array([200, 200, 200, 255], dtype=np.uint8), (len(vertices), 1))
    return mesh


def export_obj(model: RSModel, path: Path) -> None:
    mesh = model_to_trimesh(model)
    path.parent.mkdir(parents=True, exist_ok=True)
    mesh.export(path)


def render_preview(
    model: RSModel,
    output_path: Path,
    width: int = 640,
    height: int = 640,
    camera_distance_scale: float = 2.4,
) -> Path:
    mesh = model_to_trimesh(model)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    scene = pyrender.Scene(ambient_light=[0.35, 0.35, 0.35], bg_color=[24, 20, 16, 255])
    material = pyrender.MetallicRoughnessMaterial(
        baseColorFactor=[1.0, 1.0, 1.0, 1.0],
        metallicFactor=0.0,
        roughnessFactor=1.0,
    )
    scene.add(pyrender.Mesh.from_trimesh(mesh, material=material, smooth=False))

    bounds = mesh.bounds
    center = mesh.centroid
    radius = max(np.linalg.norm(bounds[1] - bounds[0]) / 2.0, 1.0)
    distance = radius * camera_distance_scale

    # 3/4 isometric-ish camera similar to inventory icons.
    camera_pose = _look_at(
        eye=center + np.array([distance * 0.85, distance * 0.55, distance * 0.85]),
        target=center,
        up=np.array([0.0, 1.0, 0.0]),
    )
    camera = pyrender.PerspectiveCamera(yfov=np.pi / 4.0)
    scene.add(camera, pose=camera_pose)

    light_pose = _look_at(
        eye=center + np.array([distance, distance * 1.2, distance * 0.5]),
        target=center,
        up=np.array([0.0, 1.0, 0.0]),
    )
    scene.add(pyrender.DirectionalLight(color=[1.0, 1.0, 1.0], intensity=3.0), pose=light_pose)

    renderer = pyrender.OffscreenRenderer(width, height)
    try:
        color, _ = renderer.render(scene, flags=pyrender.RenderFlags.FLAT)
        from PIL import Image

        Image.fromarray(color).save(output_path)
    finally:
        renderer.delete()

    return output_path


def render_trimesh_preview(
    mesh: trimesh.Trimesh,
    output_path: Path,
    width: int = 640,
    height: int = 640,
    camera_distance_scale: float = 2.4,
) -> Path | None:
    """Render a generic trimesh (e.g. raw AI output) for gallery before/after comparison."""
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        work = mesh.copy()
        if not hasattr(work.visual, "face_colors") or work.visual.face_colors is None:
            work.visual.face_colors = np.tile(
                np.array([150, 150, 160, 255], dtype=np.uint8), (len(work.faces), 1)
            )

        scene = pyrender.Scene(ambient_light=[0.35, 0.35, 0.35], bg_color=[24, 20, 16, 255])
        material = pyrender.MetallicRoughnessMaterial(
            baseColorFactor=[1.0, 1.0, 1.0, 1.0],
            metallicFactor=0.0,
            roughnessFactor=1.0,
        )
        scene.add(pyrender.Mesh.from_trimesh(work, material=material, smooth=False))

        bounds = work.bounds
        center = work.centroid
        radius = max(np.linalg.norm(bounds[1] - bounds[0]) / 2.0, 1.0)
        distance = radius * camera_distance_scale
        camera_pose = _look_at(
            eye=center + np.array([distance * 0.85, distance * 0.55, distance * 0.85]),
            target=center,
            up=np.array([0.0, 1.0, 0.0]),
        )
        camera = pyrender.PerspectiveCamera(yfov=np.pi / 4.0)
        scene.add(camera, pose=camera_pose)
        light_pose = _look_at(
            eye=center + np.array([distance, distance * 1.2, distance * 0.5]),
            target=center,
            up=np.array([0.0, 1.0, 0.0]),
        )
        scene.add(pyrender.DirectionalLight(color=[1.0, 1.0, 1.0], intensity=3.0), pose=light_pose)

        renderer = pyrender.OffscreenRenderer(width, height)
        try:
            color, _ = renderer.render(scene, flags=pyrender.RenderFlags.FLAT)
            from PIL import Image

            Image.fromarray(color).save(output_path)
            return output_path
        finally:
            renderer.delete()
    except Exception:
        return None


def _look_at(eye: np.ndarray, target: np.ndarray, up: np.ndarray) -> np.ndarray:
    forward = target - eye
    forward = forward / np.linalg.norm(forward)
    right = np.cross(forward, up)
    if np.linalg.norm(right) < 1e-8:
        right = np.array([1.0, 0.0, 0.0])
    right = right / np.linalg.norm(right)
    up_vec = np.cross(right, forward)
    pose = np.eye(4)
    pose[:3, 0] = right
    pose[:3, 1] = up_vec
    pose[:3, 2] = -forward
    pose[:3, 3] = eye
    return pose
