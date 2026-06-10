#!/usr/bin/env python3
"""Hunyuan3D text-to-shape CLI for the RS model pipeline.

Contract (used by rs-model-pipeline Hunyuan3DBackend):

    python hunyuan_generate.py --prompt "<prompt>" --output "<output_dir>"

Writes a mesh (.glb by default) into ``output_dir`` and prints the path.
Shape-only by default — RS normalization handles decimation and flat colors.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_REPO = SCRIPT_DIR / "_vendor" / "Hunyuan3D-2"
MESH_SUFFIXES = {".obj", ".glb", ".ply", ".stl"}


def _repo_path() -> Path:
    return Path(os.environ.get("HUNYUAN3D_REPO", DEFAULT_REPO)).resolve()


def _ensure_hy3dgen() -> Path:
    repo = _repo_path()
    if not (repo / "hy3dgen").is_dir():
        raise SystemExit(
            "Hunyuan3D is not installed.\n"
            f"Expected repo at: {repo}\n"
            "Run install.ps1 from tools/ai-backends/hunyuan3d/:\n"
            "  cd tools/ai-backends/hunyuan3d\n"
            "  .\\install.ps1"
        )
    repo_str = str(repo)
    if repo_str not in sys.path:
        sys.path.insert(0, repo_str)
    return repo


def _resolve_device(requested: str | None) -> str:
    import torch

    if requested:
        if requested.startswith("cuda") and not torch.cuda.is_available():
            print("CUDA requested but unavailable; falling back to CPU.", file=sys.stderr)
            return "cpu"
        return requested
    return "cuda" if torch.cuda.is_available() else "cpu"


def _find_mesh(output_dir: Path) -> Path | None:
    candidates = [
        p
        for p in output_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in MESH_SUFFIXES
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def generate(
    prompt: str,
    output_dir: Path,
    *,
    seed: int = 42,
    steps: int | None = None,
    octree_resolution: int | None = None,
    export_format: str = "glb",
    image_path: Path | None = None,
    skip_t2i: bool = False,
    device: str | None = None,
) -> Path:
    _ensure_hy3dgen()

    import torch
    from PIL import Image

    from hy3dgen.rembg import BackgroundRemover
    from hy3dgen.shapegen import Hunyuan3DDiTFlowMatchingPipeline

    output_dir.mkdir(parents=True, exist_ok=True)
    dev = _resolve_device(device)

    model_path = os.environ.get("HUNYUAN3D_MODEL", "tencent/Hunyuan3D-2mini")
    subfolder = os.environ.get("HUNYUAN3D_SUBFOLDER", "hunyuan3d-dit-v2-mini-turbo")
    infer_steps = steps if steps is not None else int(os.environ.get("HUNYUAN3D_STEPS", "5"))
    resolution = octree_resolution if octree_resolution is not None else int(
        os.environ.get("HUNYUAN3D_OCTREE_RES", "256")
    )
    num_chunks = int(os.environ.get("HUNYUAN3D_NUM_CHUNKS", "12000"))

    fmt = export_format.lower().lstrip(".")
    if fmt not in {"glb", "obj", "ply", "stl"}:
        raise ValueError(f"Unsupported export format: {export_format}")

    # --- optional text → reference image ---
    if image_path is not None:
        image = Image.open(image_path).convert("RGBA")
    elif skip_t2i:
        raise ValueError("--skip-t2i requires --image")
    else:
        try:
            from hy3dgen.text2image import HunyuanDiTPipeline
        except ImportError as exc:
            raise SystemExit(
                "HunyuanDiT text-to-image module not available.\n"
                "Ensure hy3dgen is installed (pip install -e _vendor/Hunyuan3D-2).\n"
                f"Import error: {exc}"
            ) from exc

        t2i_model = os.environ.get(
            "HUNYUAN3D_T2I_MODEL",
            "Tencent-Hunyuan/HunyuanDiT-v1.1-Diffusers-Distilled",
        )
        print(f"[hunyuan] text→image ({t2i_model}) …", file=sys.stderr)
        t2i = HunyuanDiTPipeline(t2i_model, device=dev)
        image = t2i(prompt, seed=seed)
        del t2i
        if dev.startswith("cuda"):
            torch.cuda.empty_cache()

        preview = output_dir / "t2i_preview.png"
        image.save(preview)
        print(f"[hunyuan] saved reference image: {preview}", file=sys.stderr)

    rembg = BackgroundRemover()
    if image.mode == "RGB":
        image = rembg(image.convert("RGBA"))

    # --- image → shape (mini turbo + FlashVDM for lower VRAM) ---
    print(f"[hunyuan] shape generation ({model_path}/{subfolder}) …", file=sys.stderr)
    pipeline = Hunyuan3DDiTFlowMatchingPipeline.from_pretrained(
        model_path,
        subfolder=subfolder,
        use_safetensors=True,
        device=dev,
    )
    try:
        pipeline.enable_flashvdm(topk_mode="merge")
    except Exception as exc:
        print(f"[hunyuan] FlashVDM unavailable ({exc}); continuing without it.", file=sys.stderr)

    generator = torch.Generator(dev if dev != "cpu" else "cpu").manual_seed(seed)
    mesh = pipeline(
        image=image,
        num_inference_steps=infer_steps,
        octree_resolution=resolution,
        num_chunks=num_chunks,
        generator=generator,
        output_type="trimesh",
    )[0]

    out_path = output_dir / f"generated.{fmt}"
    mesh.export(str(out_path))
    print(str(out_path.resolve()))
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Hunyuan3D text-to-shape mesh generator.")
    parser.add_argument("--prompt", required=True, help="Text description of the object")
    parser.add_argument("--output", required=True, type=Path, help="Output directory for mesh file")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--steps", type=int, help="Shape inference steps (default: 5)")
    parser.add_argument("--octree-resolution", type=int, help="Shape octree resolution (default: 256)")
    parser.add_argument(
        "--format",
        default=os.environ.get("HUNYUAN3D_FORMAT", "glb"),
        choices=["glb", "obj", "ply", "stl"],
        help="Mesh export format",
    )
    parser.add_argument("--image", type=Path, help="Skip text-to-image; use this reference image")
    parser.add_argument("--skip-t2i", action="store_true", help="Require --image; skip HunyuanDiT")
    parser.add_argument("--device", help="cuda | cpu (default: auto)")
    args = parser.parse_args(argv)

    try:
        generate(
            args.prompt.strip(),
            args.output.resolve(),
            seed=args.seed,
            steps=args.steps,
            octree_resolution=args.octree_resolution,
            export_format=args.format,
            image_path=args.image.resolve() if args.image else None,
            skip_t2i=args.skip_t2i,
            device=args.device,
        )
    except SystemExit:
        raise
    except Exception as exc:
        print(f"Generation failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
