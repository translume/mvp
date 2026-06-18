#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from translume_core.vendor.repositories import (
    VendorRepositoryError,
    bootstrap_vendor_repo_from_zip,
    load_vendor_repo_specs,
    render_vendor_status,
    inspect_vendor_repos,
    write_manifest,
    zip_bootstrap_manifest_record,
)

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "third_party" / "vendor_repos.json"
ZIP_DIR = ROOT / "third_party" / "zips"
MANIFEST_DIR = ROOT / "third_party" / "manifests"


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Offline bootstrap Harvard MIMS vendors from zip archives. "
            "This is not production-updateable and vendor-status will fail "
            "until real Git clones are installed."
        )
    )
    parser.add_argument("--config", type=Path, default=CONFIG)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--zip-dir", type=Path, default=ZIP_DIR)
    parser.add_argument("--manifest-dir", type=Path, default=MANIFEST_DIR)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    try:
        specs = load_vendor_repo_specs(args.config, args.root)
        for spec in specs:
            zip_path = args.zip_dir / f"{spec.name}.zip"
            state = bootstrap_vendor_repo_from_zip(spec, zip_path, force=args.force)
            path = write_manifest(
                args.manifest_dir,
                zip_bootstrap_manifest_record(spec, zip_path, state),
            )
            print(f"wrote {path}")
        report = inspect_vendor_repos(specs)
        print(render_vendor_status(report))
        print(
            "Offline zip bootstrap completed for inspection only. "
            "Run `make vendor-repos` on a networked VM to create real Git clones."
        )
        return 1
    except (FileNotFoundError, VendorRepositoryError) as error:
        print(str(error))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
