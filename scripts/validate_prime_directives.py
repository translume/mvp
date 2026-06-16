#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from translume_core.prime_directives import (
    find_project_root,
    merge_environment_file,
    render_prime_directives_report,
    validate_prime_directives,
    write_prime_directives_reports,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate Translume PRIME_DIRECTIVES production/demo gate. "
            "This command never fabricates readiness; it reports missing real "
            "dependencies and exits non-zero on violations."
        )
    )
    parser.add_argument(
        "--env-file",
        default=".env",
        help="Environment file to merge before process env overrides.",
    )
    parser.add_argument(
        "--output-dir",
        default="data/exports/runtime_diagnostics",
        help="Directory for JSON/Markdown diagnostics.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Validate even if TRANSLUME_ENV is local.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = find_project_root(Path(__file__))
    environment = merge_environment_file(
        env_file=(root / args.env_file).resolve(),
        process_environment=os.environ,
    )
    report = validate_prime_directives(
        environment=environment,
        root=root,
        force=bool(args.force),
    )
    write_prime_directives_reports(
        report=report,
        output_dir=(root / args.output_dir).resolve(),
    )
    print(render_prime_directives_report(report))
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
