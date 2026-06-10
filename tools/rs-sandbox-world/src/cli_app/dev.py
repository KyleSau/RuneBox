"""Copy a batch candidate into the Java client dev-models slot."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

from src.config import DEFAULT_CLIENT_DIR, DEFAULT_DEV_MODEL_ID
from src.pipeline.candidate import run_dev_model_smoke


def use_candidate(
    candidate_dir: Path,
    *,
    model_id: int = DEFAULT_DEV_MODEL_ID,
    client_dir: Path | None = None,
    run_smoke: bool = True,
) -> int:
    candidate_dir = candidate_dir.resolve()
    meta_path = candidate_dir / "metadata.json"
    if not meta_path.is_file():
        print(f"No metadata.json in {candidate_dir}", file=sys.stderr)
        return 1

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    gzip_src = meta.get("encodedGzip")
    if not gzip_src or not Path(gzip_src).is_file():
        encoded = candidate_dir / "encoded"
        matches = sorted(encoded.glob("*.dat.gz")) if encoded.is_dir() else []
        if not matches:
            print("No .dat.gz found for candidate", file=sys.stderr)
            return 1
        gzip_src = str(matches[0])

    client = (client_dir or DEFAULT_CLIENT_DIR).resolve()
    dest = client / "dev-models" / f"model_{model_id}.dat.gz"
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(gzip_src, dest)

    print(f"Copied to {dest}")
    if run_smoke:
        ok = run_dev_model_smoke(client, model_id)
        print("DevModelSmoke: PASS" if ok else "DevModelSmoke: FAIL", file=sys.stderr)
        return 0 if ok else 1
    return 0
