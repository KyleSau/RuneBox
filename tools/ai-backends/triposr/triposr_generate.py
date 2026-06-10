#!/usr/bin/env python3
"""TripoSR text-to-mesh CLI — lighter fallback for the RS model pipeline.

Contract (same as hunyuan_generate.py):

    python triposr_generate.py --prompt "<prompt>" --output "<output_dir>"

Flow: text → SD-Turbo image → TripoSR mesh (.obj/.glb).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_TRIPOSR_REPO = SCRIPT_DIR / "_vendor" / "TripoSR"


def _triposr_repo() -> Path:
    return Path(os.environ.get("TRIPOSR_REPO", DEFAULT_TRIPOSR_REPO)).resolve()


def _ensure_triposr() -> Path:
    repo = _triposr_repo()
    if not (repo / "tsr").is_dir():
        raise SystemExit(
            "TripoSR is not installed.\n"
            f"Expected repo at: {repo}\n"
            "Run install.ps1 from tools/ai-backends/triposr/"
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
    return "cuda:0" if torch.cuda.is_available() else "cpu"


def _text_to_image(prompt: str, device: str, seed: int) -> "Image.Image":
    import torch
    from diffusers import AutoPipelineForText2Image
    from PIL import Image

    model_id = os.environ.get("TRIPOSR_T2I_MODEL", "stabilityai/sd-turbo")
    print(f"[triposr] text→image ({model_id}) …", file=sys.stderr)

    dtype = torch.float16 if device.startswith("cuda") else torch.float32
    pipe = AutoPipelineForText2Image.from_pretrained(model_id, torch_dtype=dtype)
    pipe.to(device)

    generator = torch.Generator(device=device if device.startswith("cuda") else "cpu").manual_seed(seed)
    image = pipe(
        prompt=prompt,
        num_inference_steps=4 if "turbo" in model_id else 25,
        guidance_scale=0.0 if "turbo" in model_id else 7.5,
        generator=generator,
    ).images[0]

    del pipe
    if device.startswith("cuda"):
        torch.cuda.empty_cache()
    return image.convert("RGB")


def generate(
    prompt: str,
    output_dir: Path,
    *,
    seed: int = 42,
    export_format: str = "obj",
    image_path: Path | None = None,
    device: str | None = None,
    mc_resolution: int | None = None,
    chunk_size: int | None = None,
) -> Path:
    _ensure_triposr()

    import numpy as np
    import torch
    from PIL import Image

    from tsr.system import TSR
    from tsr.utils import remove_background, resize_foreground

    output_dir.mkdir(parents=True, exist_ok=True)
    dev = _resolve_device(device)
    if dev == "cuda":
        dev = "cuda:0"

    fmt = export_format.lower().lstrip(".")
    if fmt not in {"obj", "glb"}:
        raise ValueError(f"TripoSR wrapper supports obj/glb, got {export_format}")

    resolution = mc_resolution if mc_resolution is not None else int(os.environ.get("TRIPOSR_MC_RES", "256"))
    chunks = chunk_size if chunk_size is not None else int(os.environ.get("TRIPOSR_CHUNK_SIZE", "8192"))
    model_id = os.environ.get("TRIPOSR_MODEL", "stabilityai/TripoSR")
    foreground_ratio = float(os.environ.get("TRIPOSR_FOREGROUND_RATIO", "0.85"))

    if image_path is not None:
        image = Image.open(image_path).convert("RGB")
    else:
        image = _text_to_image(prompt, dev, seed)
        preview = output_dir / "t2i_preview.png"
        image.save(preview)
        print(f"[triposr] saved reference image: {preview}", file=sys.stderr)

    print(f"[triposr] image→mesh ({model_id}) …", file=sys.stderr)
    model = TSR.from_pretrained(
        model_id,
        config_name="config.yaml",
        weight_name="model.ckpt",
    )
    model.renderer.set_chunk_size(chunks)
    model.to(dev)

    import rembg

    session = rembg.new_session()
    rgba = remove_background(image, session)
    rgba = resize_foreground(rgba, foreground_ratio)
    arr = np.array(rgba).astype(np.float32) / 255.0
    arr = arr[:, :, :3] * arr[:, :, 3:4] + (1 - arr[:, :, 3:4]) * 0.5
    proc = Image.fromarray((arr * 255.0).astype(np.uint8))

    with torch.no_grad():
        scene_codes = model([proc], device=dev)
        meshes = model.extract_mesh(scene_codes, True, resolution=resolution)

    out_path = output_dir / f"generated.{fmt}"
    meshes[0].export(str(out_path))
    print(str(out_path.resolve()))
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="TripoSR text-to-mesh generator (lighter fallback).")
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--format", default="obj", choices=["obj", "glb"])
    parser.add_argument("--image", type=Path, help="Skip text-to-image")
    parser.add_argument("--device", help="cuda:0 | cpu")
    parser.add_argument("--mc-resolution", type=int)
    parser.add_argument("--chunk-size", type=int)
    args = parser.parse_args(argv)

    try:
        generate(
            args.prompt.strip(),
            args.output.resolve(),
            seed=args.seed,
            export_format=args.format,
            image_path=args.image.resolve() if args.image else None,
            device=args.device,
            mc_resolution=args.mc_resolution,
            chunk_size=args.chunk_size,
        )
    except SystemExit:
        raise
    except Exception as exc:
        print(f"Generation failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
