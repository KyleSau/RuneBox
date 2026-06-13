"""Invoke the 317 client's Java cache/decompression code via devtools.CacheBridge."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from src.config import resolve_java_client_dir, resolve_java_exe


class JavaBridgeError(RuntimeError):
    pass


def _client_root() -> Path | None:
    root = resolve_java_client_dir()
    return root.resolve() if root else None


def client_root() -> Path:
    root = _client_root()
    if root is None:
        raise JavaBridgeError("Java client not configured (set RS_JAVA_CLIENT_DIR)")
    return root


def is_available() -> bool:
    root = _client_root()
    return root is not None and root.is_dir() and (root / "pom.xml").exists()


def ensure_built() -> None:
    if not is_available():
        raise JavaBridgeError("Java client not configured (set RS_JAVA_CLIENT_DIR)")
    root = client_root()
    class_dir = root / "target" / "classes"
    cp_file = root / "cp.txt"
    if class_dir.is_dir() and cp_file.is_file():
        return
    _build(root)


def _build(client_root_path: Path) -> None:
    subprocess.run(
        ["mvn", "-q", "compile", "dependency:build-classpath", "-Dmdep.pathSeparator=;", "-Dmdep.outputFile=cp.txt"],
        cwd=client_root_path,
        check=True,
    )


def classpath() -> str:
    ensure_built()
    root = client_root()
    class_dir = root / "target" / "classes"
    cp_file = root / "cp.txt"
    deps = cp_file.read_text(encoding="utf-8").strip()
    return f"{class_dir};{deps}" if deps else str(class_dir)


def run(cache_dir: Path, *args: str) -> subprocess.CompletedProcess[str]:
    ensure_built()
    cmd = [
        resolve_java_exe(),
        "-cp",
        classpath(),
        "CacheBridge",
        str(cache_dir),
        *args,
    ]
    return subprocess.run(cmd, capture_output=True, text=True, cwd=client_root())


def _temp_output() -> Path:
    handle = tempfile.NamedTemporaryFile(delete=False)
    path = Path(handle.name)
    handle.close()
    return path


def read_cache_file(cache_dir: Path, store_idx: int, file_id: int) -> bytes | None:
    out = _temp_output()
    try:
        result = run(cache_dir, "read-file", "--store", str(store_idx), "--id", str(file_id), "--output", str(out))
        if result.returncode != 0:
            return None
        return out.read_bytes()
    finally:
        out.unlink(missing_ok=True)


def read_archive_member(cache_dir: Path, archive_id: int, member_name: str) -> bytes | None:
    out = _temp_output()
    try:
        result = run(
            cache_dir,
            "read-member",
            "--archive",
            str(archive_id),
            "--name",
            member_name,
            "--output",
            str(out),
        )
        if result.returncode != 0:
            return None
        return out.read_bytes()
    finally:
        out.unlink(missing_ok=True)


def read_model_bytes(cache_dir: Path, model_id: int) -> bytes | None:
    """idx1 payload after OnDemand-style gzip decompression."""
    out = _temp_output()
    try:
        result = run(cache_dir, "model-bytes", "--id", str(model_id), "--output", str(out))
        if result.returncode != 0:
            return None
        return out.read_bytes()
    finally:
        out.unlink(missing_ok=True)


def search_npcs(cache_dir: Path, query: str) -> list[dict]:
    result = run(cache_dir, "npc", "--search", query)
    if result.returncode != 0:
        raise JavaBridgeError(result.stderr.strip() or "npc search failed")
    return json.loads(result.stdout)


def get_npc(cache_dir: Path, npc_id: int) -> dict:
    result = run(cache_dir, "npc", "--id", str(npc_id))
    if result.returncode != 0:
        raise JavaBridgeError(result.stderr.strip() or f"npc {npc_id} not found")
    return json.loads(result.stdout)


def search_items(cache_dir: Path, query: str) -> list[dict]:
    result = run(cache_dir, "item", "--search", query)
    if result.returncode != 0:
        raise JavaBridgeError(result.stderr.strip() or "item search failed")
    return json.loads(result.stdout)


def get_item(cache_dir: Path, item_id: int) -> dict:
    result = run(cache_dir, "item", "--id", str(item_id))
    if result.returncode != 0:
        raise JavaBridgeError(result.stderr.strip() or f"item {item_id} not found")
    return json.loads(result.stdout)
