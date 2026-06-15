#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_PATH = ROOT / "packages" / "translume-core" / "src"
if str(PACKAGE_PATH) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PATH))

from translume_core.runtime_validation import (
    RuntimeCommandResult,
    build_runtime_validation_report,
    command_specs_from_config,
    failure_patterns_from_config,
    load_runtime_validation_config,
    redact_sensitive_text,
    render_runtime_report_markdown,
    runtime_report_to_dict,
)

DEFAULT_CONFIG = ROOT / "configs" / "integration" / "live_vm_runtime_validation.json"


def execute_runtime_command(
    spec_name: str,
    argv: tuple[str, ...],
    required: bool,
    timeout_seconds: float,
    secret_names: tuple[str, ...],
    environment: dict[str, str],
) -> RuntimeCommandResult:
    """Execute one real runtime validation command.

    Acceptance criteria:
        1. Executes the provided command vector without shell interpolation.
        2. Captures stdout and stderr.
        3. Redacts configured secret values from captured output.
        4. Converts timeouts into non-zero command results.

    Args:
        spec_name: Human-readable command name.
        argv: Command vector to execute.
        required: Whether this command is required.
        timeout_seconds: Command timeout.
        secret_names: Environment variable names whose values are redacted.
        environment: Environment variables passed to the subprocess.

    Returns:
        Runtime command result.
    """
    start = time.monotonic()
    try:
        completed = subprocess.run(
            list(argv),
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        return_code = int(completed.returncode)
        stdout = completed.stdout
        stderr = completed.stderr
    except subprocess.TimeoutExpired as error:
        return_code = 124
        stdout = error.stdout if isinstance(error.stdout, str) else ""
        stderr = error.stderr if isinstance(error.stderr, str) else ""
        stderr += f"\ncommand timed out after {timeout_seconds} seconds"
    elapsed = time.monotonic() - start
    return RuntimeCommandResult(
        name=spec_name,
        argv=argv,
        return_code=return_code,
        stdout=redact_sensitive_text(stdout, secret_names, environment),
        stderr=redact_sensitive_text(stderr, secret_names, environment),
        required=required,
        elapsed_seconds=elapsed,
    )


def write_runtime_report(
    output_dir: Path,
    report_dict: dict[str, object],
    markdown: str,
) -> tuple[Path, Path]:
    """Write runtime validation report files.

    Acceptance criteria:
        1. Creates output directory if needed.
        2. Writes JSON and Markdown reports.
        3. File names include report ID.
        4. Returns created file paths.
    """
    report_id = str(report_dict["report_id"])
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{report_id}_runtime_report.json"
    markdown_path = output_dir / f"{report_id}_runtime_report.md"
    json_path.write_text(json.dumps(report_dict, indent=2), encoding="utf-8")
    markdown_path.write_text(markdown, encoding="utf-8")
    return json_path, markdown_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run real live-VM Translume validation and diagnostics."
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument(
        "--continue-after-failure",
        action="store_true",
        help="Run remaining diagnostic commands after a required command fails.",
    )
    args = parser.parse_args()
    config = load_runtime_validation_config(args.config)
    environment = dict(os.environ)
    commands = command_specs_from_config(config, environment)
    patterns = failure_patterns_from_config(config)
    secret_names = tuple(str(item) for item in config.get("secret_environment_names", []))
    results: list[RuntimeCommandResult] = []
    for command in commands:
        result = execute_runtime_command(
            spec_name=command.name,
            argv=command.argv,
            required=command.required,
            timeout_seconds=command.timeout_seconds,
            secret_names=secret_names,
            environment=environment,
        )
        results.append(result)
        if (
            command.required
            and result.return_code != 0
            and not args.continue_after_failure
        ):
            break
    report = build_runtime_validation_report(results, patterns)
    report_dict = runtime_report_to_dict(report)
    output_dir = ROOT / str(config.get("report_output_dir", "data/exports/runtime_diagnostics"))
    json_path, markdown_path = write_runtime_report(
        output_dir,
        report_dict,
        render_runtime_report_markdown(report),
    )
    print(
        json.dumps(
            {
                "status": report.status,
                "report_id": report.report_id,
                "json_report": str(json_path),
                "markdown_report": str(markdown_path),
                "findings": [finding.category for finding in report.findings],
            },
            indent=2,
        )
    )
    return 0 if report.status == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
