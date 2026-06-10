"""Pipeline configuration defaults."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

PIPELINE_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = PIPELINE_ROOT.parent.parent
OUTPUT_ROOT = PIPELINE_ROOT / "outputs"
GENERATED_DIR = OUTPUT_ROOT / "generated"
GENERATED_CONCEPTS_DIR = OUTPUT_ROOT / "generated_concepts"
PREVIEWS_DIR = OUTPUT_ROOT / "previews"
INTERMEDIATE_DIR = OUTPUT_ROOT / "intermediate"
ROUNDTRIP_DIR = OUTPUT_ROOT / "roundtrip"

INPUTS_DIR = PIPELINE_ROOT / "inputs"
MOCK_MESH_SOURCE = INPUTS_DIR / "test_axe.obj"

# Default cache path (377 OpenRS2 dump in project root).
DEFAULT_CACHE_ROOT = (
    PROJECT_ROOT
    / "cache-runescape-live-en-b377-2006-05-02-00-00-00-openrs2#657"
)
DEFAULT_CACHE_DIR = DEFAULT_CACHE_ROOT / "cache"

# Java client dev-model defaults (relative to pipeline root).
DEFAULT_CLIENT_DIR = PROJECT_ROOT / "RuneScape-317-client"
DEFAULT_DEV_MODEL_ID = 90000

# AI backends — pluggable command wrappers; no training/fine-tuning.
DEFAULT_BACKEND = "mock"
HUNYUAN3D_COMMAND: str | None = None
SHAPE_E_ENABLED = False
SHAPE_E_COMMAND: str | None = None
TRIPOSR_COMMAND: str | None = None


def _load_dotenv_files() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return

    candidates = [
        PROJECT_ROOT / ".env.local",
        PROJECT_ROOT / ".env",
        PIPELINE_ROOT / ".env.local",
        PIPELINE_ROOT / ".env",
    ]
    for path in candidates:
        if path.is_file():
            load_dotenv(path, override=False)


_load_dotenv_files()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_IMAGE_MODEL = os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-1")
DEFAULT_CONCEPT_BACKEND = os.getenv("TEXT2RS_CONCEPT_BACKEND", "manual")


def resolve_hunyuan3d_command() -> str | None:
    env = os.environ.get("RS_HUNYUAN3D_COMMAND")
    if env:
        return env.strip() or None
    return HUNYUAN3D_COMMAND


def resolve_triposr_command() -> str | None:
    env = os.environ.get("RS_TRIPOSR_COMMAND")
    if env:
        return env.strip() or None
    return TRIPOSR_COMMAND


def resolve_cache_dir(path: Path) -> Path:
    """Accept either the OpenRS2 parent folder or the inner cache/ folder."""
    path = path.resolve()
    if (path / "main_file_cache.dat").exists():
        return path
    if (path / "cache" / "main_file_cache.dat").exists():
        return path / "cache"
    return path


def resolve_java_exe() -> str:
    """Prefer Java 17+ for the 317 client; PATH shims may point at an older JRE."""
    java_home = os.environ.get("JAVA_HOME")
    if java_home:
        for name in ("java.exe", "java"):
            candidate = Path(java_home) / "bin" / name
            if candidate.is_file():
                return str(candidate)

    if os.name == "nt":
        java_root = Path(r"C:\Program Files\Java")
        if java_root.is_dir():
            jdks = sorted(java_root.glob("jdk-*"), key=lambda p: p.name, reverse=True)
            for jdk in jdks:
                candidate = jdk / "bin" / "java.exe"
                if candidate.is_file():
                    return str(candidate)

    found = shutil.which("java")
    return found or "java"


# OnDemand store -> FileStore slot in client (see README cache map).
ONDEMAND_STORE_TO_FILESTORE = {
    0: 1,  # models -> idx1
    1: 2,  # animations -> idx2
    2: 3,  # midi -> idx3
    3: 4,  # maps -> idx4
}

# Main cache archives in idx0 / filestores[0].
ARCHIVE_CONFIG = 2
ARCHIVE_VERSIONLIST = 5
