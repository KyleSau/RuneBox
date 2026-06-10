"""Score a single generated candidate."""

from __future__ import annotations

import sys
from pathlib import Path

from src.quality.report import print_report, score_candidate_dir


def run_score(candidate_dir: Path) -> int:
    candidate_dir = candidate_dir.resolve()
    if not (candidate_dir / "metadata.json").is_file():
        print(f"Not a candidate directory: {candidate_dir}", file=sys.stderr)
        return 1
    metrics, style = score_candidate_dir(candidate_dir)
    print_report(metrics, style)
    print(f"Wrote {candidate_dir / 'quality_score.json'}")
    print(f"Wrote {candidate_dir / 'quality_report.txt'}")
    return 0
