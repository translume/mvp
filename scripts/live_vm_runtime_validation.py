#!/usr/bin/env python3
"""Run the real Translume live-VM runtime validation workflow.

This script starts the Docker Compose stack, executes the real full-stack
integration path, and writes a runtime report plus failure diagnostics when the
stack fails. It does not fabricate success, patch runtime state, or use mocked
services.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import time
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from scripts.full_stack_preflight import (
    DEFAULT_REQUIREMENTS,
    PreflightError,
    run_preflight,
)
from scripts.run_full_stack_integration import (
    FullStackIntegrationError,
    run_full_stack_integration,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORTS_DIR = ROOT / "data" / "runtime_validation"
DEFAULT_COMPOSE_PROFILES = ("gpu", "docling")
SENSITIVE_ENV_PARTS = (
    "KEY",
    "PASSWORD",
    "SECRET",
    "TOKEN",
    "DSN",
    "CREDENTIAL",
)


class LiveRuntimeValidationError(RuntimeError):
    """Raised when live VM validation fails."""


@dataclass(frozen=True)
class CommandResult:
    """Represent a completed runtime command.

    Attributes:
        command: Command arguments.
        returncode: Process return code.
        stdout: Captured standard output.
        stderr: Captured standard error.
        elapsed_seconds: Runtime duration in seconds.
    """

    command: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str
    elapsed_seconds: float


@dataclass(frozen=True)
class DiagnosticPaths:
    """Represent generated diagnostic file paths.

    Attributes:
        output_dir: Directory containing runtime validation artifacts.
        report_json: JSON report path.
        report_md: Markdown report path.
        compose_ps_json: Docker Compose ps JSON path, if written.
        compose_logs_txt: Docker Compose logs path, if written.
        redacted_env_json: Redacted environment path, if written.
    """

    output_dir: Path
    report_json: Path
    report_md: Path
    compose_ps_json: Path | None = None
    compose_logs_txt: Path | None = None
    redacted_env_json: Path | None = None


@dataclass(frozen=True)
class LiveRuntimeValidationResult:
    """Represent live VM validation output.

    Attributes:
        status: Either `ok` or `failed`.
        started_at_epoch: Start time in seconds since epoch.
        elapsed_seconds: Runtime duration in seconds.
        report_paths: Generated report and diagnostics paths.
        integration_result: Full-stack result payload when successful.
        error: Failure message when unsuccessful.
    """

    status: str
    started_at_epoch: float
    elapsed_seconds: float
    report_paths: DiagnosticPaths
    integration_result: dict[str, object] | None = None
    error: str | None = None


def load_env_file(path: Path) -> dict[str, str]:
    """Load a simple dotenv file into a dictionary.

    Acceptance criteria:
        1. Determinism: Same file content returns the same mapping.
        2. Validation: Missing files raise `FileNotFoundError`.
        3. Parsing: Blank lines and comments are ignored.
        4. No mutation: Does not modify `os.environ`.

    Args:
        path: Dotenv path.

    Returns:
        Parsed environment mapping.

    Raises:
        FileNotFoundError: If `path` does not exist.
        ValueError: If a non-comment line does not contain `=`.
    """
    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"invalid dotenv line {line_number}: {raw_line}")
        key, value = line.split("=", 1)
        normalized_key = key.strip()
        if not normalized_key:
            raise ValueError(f"empty dotenv key on line {line_number}")
        values[normalized_key] = strip_optional_quotes(value.strip())
    return values


def strip_optional_quotes(value: str) -> str:
    """Return a dotenv value with one matching quote pair removed.

    Acceptance criteria:
        1. Determinism: Same value returns the same result.
        2. No mutation: Does not mutate caller-owned values.
        3. Quote handling: Removes only matching single or double outer quotes.
        4. Preservation: Unquoted values are returned unchanged.

    Args:
        value: Raw dotenv value.

    Returns:
        Normalized value.
    """
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def merged_environment(
    env_file_values: Mapping[str, str],
    process_environment: Mapping[str, str],
) -> dict[str, str]:
    """Return runtime environment with process values taking precedence.

    Acceptance criteria:
        1. Determinism: Same inputs return the same mapping.
        2. Precedence: Existing process environment values override `.env`.
        3. No mutation: Inputs are not mutated.
        4. Completeness: All keys from both mappings are included.

    Args:
        env_file_values: Values parsed from `.env`.
        process_environment: Current process environment.

    Returns:
        Merged environment dictionary.
    """
    merged = dict(env_file_values)
    merged.update(process_environment)
    return merged


def redact_environment(environment: Mapping[str, str]) -> dict[str, str]:
    """Return environment with sensitive values redacted.

    Acceptance criteria:
        1. Determinism: Same environment returns the same redacted mapping.
        2. Safety: Sensitive-looking keys are redacted.
        3. Preservation: Non-sensitive values are preserved.
        4. No mutation: Input mapping is not mutated.

    Args:
        environment: Runtime environment mapping.

    Returns:
        Redacted environment mapping.
    """
    redacted: dict[str, str] = {}
    for key, value in environment.items():
        upper_key = key.upper()
        if any(part in upper_key for part in SENSITIVE_ENV_PARTS):
            redacted[key] = "<redacted>"
        else:
            redacted[key] = value
    return dict(sorted(redacted.items()))


def compose_command(
    compose_args: Sequence[str],
    profiles: Sequence[str],
) -> list[str]:
    """Return a Docker Compose command with profiles.

    Acceptance criteria:
        1. Determinism: Same args and profiles return the same command.
        2. Ordering: Profiles are emitted in supplied order.
        3. No mutation: Inputs are not mutated.
        4. CLI compatibility: Command starts with `docker compose`.

    Args:
        compose_args: Arguments after profiles.
        profiles: Docker Compose profiles to enable.

    Returns:
        Command argument list.
    """
    command = ["docker", "compose"]
    for profile in profiles:
        command.extend(("--profile", profile))
    command.extend(compose_args)
    return command


def run_command(
    command: Sequence[str],
    *,
    cwd: Path,
    environment: Mapping[str, str],
    timeout_seconds: float,
) -> CommandResult:
    """Run a real subprocess command and capture output.

    Acceptance criteria:
        1. Executes the supplied command exactly once.
        2. Captures stdout and stderr.
        3. Does not swallow non-zero return codes.
        4. Does not mutate the supplied environment mapping.

    Args:
        command: Command arguments.
        cwd: Working directory.
        environment: Runtime environment.
        timeout_seconds: Timeout in seconds.

    Returns:
        Captured command result.

    Raises:
        TimeoutError: If the subprocess exceeds the timeout.
    """
    started = time.monotonic()
    completed = subprocess.run(
        list(command),
        cwd=cwd,
        env=dict(environment),
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        check=False,
    )
    return CommandResult(
        command=tuple(command),
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        elapsed_seconds=time.monotonic() - started,
    )


def require_success(result: CommandResult, action: str) -> None:
    """Raise if a runtime command failed.

    Acceptance criteria:
        1. Return code zero passes.
        2. Non-zero return code raises `LiveRuntimeValidationError`.
        3. Error message includes command and captured stderr/stdout.
        4. Function is pure.

    Args:
        result: Command result.
        action: Human-readable command purpose.

    Raises:
        LiveRuntimeValidationError: If return code is non-zero.
    """
    if result.returncode == 0:
        return
    raise LiveRuntimeValidationError(
        f"{action} failed with exit code {result.returncode}: "
        f"command={list(result.command)!r}; stdout={result.stdout!r}; "
        f"stderr={result.stderr!r}"
    )


def prepare_output_dir(base_dir: Path, started_at_epoch: float) -> Path:
    """Create and return a timestamped runtime validation directory.

    Acceptance criteria:
        1. Directory is created if it does not exist.
        2. Directory name is derived from explicit timestamp.
        3. Function writes only under `base_dir`.
        4. Returned path is absolute.

    Args:
        base_dir: Parent diagnostics directory.
        started_at_epoch: Explicit start timestamp.

    Returns:
        Created output directory.
    """
    run_name = time.strftime(
        "%Y%m%dT%H%M%SZ",
        time.gmtime(started_at_epoch),
    )
    output_dir = (base_dir / run_name).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def write_text(path: Path, content: str) -> Path:
    """Write text to a file and return the path.

    Acceptance criteria:
        1. Parent directory is created.
        2. UTF-8 encoding is used.
        3. Content is written exactly as supplied.
        4. Boundary function isolates filesystem writes.

    Args:
        path: Output path.
        content: Text content.

    Returns:
        Written path.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def collect_runtime_diagnostics(
    *,
    output_dir: Path,
    profiles: Sequence[str],
    environment: Mapping[str, str],
    root: Path,
) -> DiagnosticPaths:
    """Collect real Docker Compose diagnostics after a validation failure.

    Acceptance criteria:
        1. Attempts `docker compose ps --format json`.
        2. Attempts `docker compose logs --tail=400`.
        3. Writes redacted environment values.
        4. Diagnostic collection failures are recorded, not hidden.

    Args:
        output_dir: Diagnostics directory.
        profiles: Compose profiles used for the stack.
        environment: Runtime environment.
        root: Repository root.

    Returns:
        Diagnostic path summary.
    """
    ps_path = output_dir / "compose_ps.json"
    logs_path = output_dir / "compose_logs.txt"
    env_path = output_dir / "redacted_environment.json"

    write_text(
        env_path,
        json.dumps(redact_environment(environment), indent=2, sort_keys=True),
    )

    try:
        ps_result = run_command(
            compose_command(("ps", "--format", "json"), profiles),
            cwd=root,
            environment=environment,
            timeout_seconds=60,
        )
        write_text(
            ps_path,
            ps_result.stdout
            or json.dumps(asdict(ps_result), indent=2, default=str),
        )
    except (OSError, subprocess.SubprocessError, TimeoutError) as error:
        write_text(ps_path, json.dumps({"error": str(error)}, indent=2))

    try:
        logs_result = run_command(
            compose_command(("logs", "--tail=400"), profiles),
            cwd=root,
            environment=environment,
            timeout_seconds=120,
        )
        write_text(
            logs_path,
            logs_result.stdout
            + "\n--- STDERR ---\n"
            + logs_result.stderr,
        )
    except (OSError, subprocess.SubprocessError, TimeoutError) as error:
        write_text(logs_path, f"failed to collect logs: {error}\n")

    return DiagnosticPaths(
        output_dir=output_dir,
        report_json=output_dir / "runtime_validation_report.json",
        report_md=output_dir / "runtime_validation_report.md",
        compose_ps_json=ps_path,
        compose_logs_txt=logs_path,
        redacted_env_json=env_path,
    )


def render_report_markdown(result: LiveRuntimeValidationResult) -> str:
    """Render a human-readable live VM validation report.

    Acceptance criteria:
        1. Includes status.
        2. Includes elapsed time.
        3. Includes diagnostics paths.
        4. Includes error details when validation fails.

    Args:
        result: Validation result.

    Returns:
        Markdown report string.
    """
    paths = result.report_paths
    lines = [
        "# Translume Live VM Runtime Validation Report",
        "",
        f"Status: **{result.status}**",
        f"Elapsed seconds: `{result.elapsed_seconds:.2f}`",
        f"Output directory: `{paths.output_dir}`",
        "",
    ]
    if result.integration_result is not None:
        lines.extend(
            [
                "## Integration Result",
                "",
                "```json",
                json.dumps(result.integration_result, indent=2, sort_keys=True),
                "```",
                "",
            ]
        )
    if result.error is not None:
        lines.extend(["## Error", "", result.error, ""])
    lines.extend(
        [
            "## Diagnostic Files",
            "",
            f"- JSON report: `{paths.report_json}`",
            f"- Markdown report: `{paths.report_md}`",
            f"- Compose ps: `{paths.compose_ps_json}`",
            f"- Compose logs: `{paths.compose_logs_txt}`",
            f"- Redacted environment: `{paths.redacted_env_json}`",
            "",
            "## Repair Loop",
            "",
            "1. Open the compose logs and identify the first failing service.",
            "2. Fix configuration, vendor repo, model, GPU, or service error.",
            "3. Re-run `make live-vm-validate`.",
            "4. Do not accept the MVP as demo-ready until this report is ok.",
        ]
    )
    return "\n".join(lines)


def write_runtime_result(result: LiveRuntimeValidationResult) -> DiagnosticPaths:
    """Persist live VM validation result files.

    Acceptance criteria:
        1. Writes JSON result.
        2. Writes Markdown report.
        3. Uses explicit paths in `result.report_paths`.
        4. Boundary function isolates filesystem writes.

    Args:
        result: Live runtime validation result.

    Returns:
        Diagnostic path summary.
    """
    write_text(
        result.report_paths.report_json,
        json.dumps(asdict(result), indent=2, default=str),
    )
    write_text(result.report_paths.report_md, render_report_markdown(result))
    return result.report_paths


async def run_live_vm_validation(
    *,
    root: Path,
    env_file: Path,
    requirements_path: Path,
    output_base_dir: Path,
    profiles: Sequence[str],
    require_gpu: bool,
    leave_up: bool,
    down_on_failure: bool,
    wait_timeout_seconds: float,
    wait_interval_seconds: float,
    api_timeout_seconds: float,
) -> LiveRuntimeValidationResult:
    """Run real live-VM validation and collect diagnostics.

    Acceptance criteria:
        1. Loads `.env` and current process environment.
        2. Runs preflight with Docker and optional GPU requirements.
        3. Runs `docker compose config` against the real compose file.
        4. Starts the real Docker Compose stack.
        5. Runs the real full-stack integration workflow.
        6. Writes runtime report and diagnostics.
        7. Does not fabricate success or mask failures.

    Args:
        root: Repository root.
        env_file: Dotenv path.
        requirements_path: Full-stack requirements path.
        output_base_dir: Parent diagnostics directory.
        profiles: Docker Compose profiles to enable.
        require_gpu: Whether to require `nvidia-smi` in preflight.
        leave_up: Whether to leave containers running after success.
        down_on_failure: Whether to stop containers after failure.
        wait_timeout_seconds: Service wait timeout.
        wait_interval_seconds: Service wait interval.
        api_timeout_seconds: Report-processing timeout.

    Returns:
        Live VM validation result.
    """
    started = time.time()
    output_dir = prepare_output_dir(output_base_dir, started)
    report_paths = DiagnosticPaths(
        output_dir=output_dir,
        report_json=output_dir / "runtime_validation_report.json",
        report_md=output_dir / "runtime_validation_report.md",
    )
    env_values = load_env_file(env_file)
    environment = merged_environment(env_values, os.environ)
    try:
        run_preflight(
            requirements_path=requirements_path,
            environment=environment,
            root=root,
            require_docker=True,
            require_gpu=require_gpu,
        )
        require_success(
            run_command(
                compose_command(("config",), profiles),
                cwd=root,
                environment=environment,
                timeout_seconds=120,
            ),
            "docker compose config",
        )
        require_success(
            run_command(
                compose_command(("up", "--build", "-d"), profiles),
                cwd=root,
                environment=environment,
                timeout_seconds=1800,
            ),
            "docker compose up",
        )
        integration_result = await run_full_stack_integration(
            requirements_path=requirements_path,
            environment=environment,
            root=root,
            wait_timeout_seconds=wait_timeout_seconds,
            wait_interval_seconds=wait_interval_seconds,
            api_timeout_seconds=api_timeout_seconds,
        )
        result = LiveRuntimeValidationResult(
            status="ok",
            started_at_epoch=started,
            elapsed_seconds=time.time() - started,
            report_paths=report_paths,
            integration_result=asdict(integration_result),
        )
        write_runtime_result(result)
        if not leave_up:
            run_command(
                compose_command(("down",), profiles),
                cwd=root,
                environment=environment,
                timeout_seconds=300,
            )
        return result
    except (OSError, subprocess.SubprocessError, TimeoutError, PreflightError,
            FullStackIntegrationError, LiveRuntimeValidationError,
            ValueError) as error:
        diagnostic_paths = collect_runtime_diagnostics(
            output_dir=output_dir,
            profiles=profiles,
            environment=environment,
            root=root,
        )
        result = LiveRuntimeValidationResult(
            status="failed",
            started_at_epoch=started,
            elapsed_seconds=time.time() - started,
            report_paths=diagnostic_paths,
            error=str(error),
        )
        write_runtime_result(result)
        if down_on_failure:
            run_command(
                compose_command(("down",), profiles),
                cwd=root,
                environment=environment,
                timeout_seconds=300,
            )
        return result


def main() -> int:
    """Run live VM validation from the command line."""
    parser = argparse.ArgumentParser(
        description="Run real Translume live-VM Docker/GPU validation."
    )
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--requirements", type=Path, default=DEFAULT_REQUIREMENTS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_REPORTS_DIR)
    parser.add_argument(
        "--profile",
        action="append",
        dest="profiles",
        default=[],
        help="Docker Compose profile to enable. May be supplied multiple times.",
    )
    parser.add_argument("--no-require-gpu", action="store_true")
    parser.add_argument("--leave-up", action="store_true")
    parser.add_argument("--down-on-failure", action="store_true")
    parser.add_argument("--wait-timeout-seconds", type=float, default=600.0)
    parser.add_argument("--wait-interval-seconds", type=float, default=5.0)
    parser.add_argument("--api-timeout-seconds", type=float, default=900.0)
    args = parser.parse_args()
    profiles = tuple(args.profiles) or DEFAULT_COMPOSE_PROFILES
    result = asyncio.run(
        run_live_vm_validation(
            root=ROOT,
            env_file=args.env_file,
            requirements_path=args.requirements,
            output_base_dir=args.output_dir,
            profiles=profiles,
            require_gpu=not args.no_require_gpu,
            leave_up=args.leave_up,
            down_on_failure=args.down_on_failure,
            wait_timeout_seconds=args.wait_timeout_seconds,
            wait_interval_seconds=args.wait_interval_seconds,
            api_timeout_seconds=args.api_timeout_seconds,
        )
    )
    print(json.dumps(asdict(result), indent=2, default=str))
    return 0 if result.status == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
