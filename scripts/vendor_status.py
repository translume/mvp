#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from translume_core.vendor.repositories import (
    VendorRepositoryError,
    inspect_vendor_repos,
    load_vendor_repo_specs,
    render_vendor_status,
    vendor_status_to_dict,
)

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "third_party" / "vendor_repos.json"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate that Harvard MIMS vendors are real updateable Git clones."
    )
    parser.add_argument("--config", type=Path, default=CONFIG)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--json", action="store_true", help="Print JSON status.")
    args = parser.parse_args()
    try:
        specs = load_vendor_repo_specs(args.config, args.root)
        report = inspect_vendor_repos(specs)
    except (FileNotFoundError, VendorRepositoryError) as error:
        print(str(error))
        return 1
    if args.json:
        print(json.dumps(vendor_status_to_dict(report), indent=2))
    else:
        print(render_vendor_status(report))
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
