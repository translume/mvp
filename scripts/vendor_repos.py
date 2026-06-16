#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from translume_core.vendor.repositories import (
    VendorRepositoryError,
    clone_or_pull_vendor_repo,
    inspect_vendor_repos,
    load_vendor_repo_specs,
    manifest_record,
    render_vendor_status,
    vendor_status_to_dict,
    write_manifest,
)

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "third_party" / "vendor_repos.json"
MANIFEST_DIR = ROOT / "third_party" / "manifests"


def update_vendor_repos(config_path: Path, root: Path, manifest_dir: Path) -> int:
    """Clone or fast-forward pull all configured vendor repositories.

    Acceptance criteria:
        1. Uses Git clone or `git pull --ff-only` only.
        2. Does not use zip archives or fallback source directories.
        3. Fails if an existing target is not a Git repository.
        4. Writes git update manifests only after successful updates.

    Args:
        config_path: Vendor repository configuration.
        root: Project root.
        manifest_dir: Output manifest directory.

    Returns:
        Process exit code.
    """
    specs = load_vendor_repo_specs(config_path, root)
    states = tuple(clone_or_pull_vendor_repo(spec) for spec in specs)
    for state in states:
        path = write_manifest(manifest_dir, manifest_record(state))
        print(f"wrote {path}")
    report = inspect_vendor_repos(specs)
    print(render_vendor_status(report))
    return 0 if report.ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Clone or fast-forward pull Harvard MIMS vendor repositories. "
            "This command never unpacks zip archives."
        )
    )
    parser.add_argument("--config", type=Path, default=CONFIG)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--manifest-dir", type=Path, default=MANIFEST_DIR)
    args = parser.parse_args()
    try:
        return update_vendor_repos(args.config, args.root, args.manifest_dir)
    except VendorRepositoryError as error:
        print(str(error))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
