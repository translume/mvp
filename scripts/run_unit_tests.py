"""Run all application and downstream test suites inside the CPU test image."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    suites = (
        (ROOT, ("tests",)),
        (ROOT / "precision_oncology_json_pipeline", ("tests",)),
        (ROOT / "dynamic_pathway_analyzer", (".",)),
    )
    for directory, paths in suites:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", *paths],
            cwd=directory,
            check=False,
        )
        if result.returncode:
            return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
