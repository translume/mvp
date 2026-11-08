#!/usr/bin/env python3
"""Optional developer orchestration of the real Docker/CPU/OpenAI workflow.

All application checks execute inside the deployed containers. This host helper
uses Python's standard library and the repository's pure report helpers; the
end-user workflow in README requires Docker only. It never substitutes fixtures
for the report, reference data, OpenAI calls, or downstream verification.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_PATH = ROOT / "packages" / "translume-core" / "src"
if str(PACKAGE_PATH) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PATH))

from translume_core.runtime_validation import (
    RuntimeCommandResult,
    RuntimeCommandSpec,
    build_runtime_validation_report,
    command_specs_from_config,
    failure_patterns_from_config,
    load_runtime_validation_config,
    render_runtime_report_markdown,
    runtime_report_to_dict,
)

DEFAULT_CONFIG = ROOT / "configs" / "integration" / "live_vm_runtime_validation.json"
SENSITIVE_ENV_PARTS = ("KEY", "PASSWORD", "SECRET", "TOKEN", "DSN", "CREDENTIAL")


class LiveRuntimeValidationError(RuntimeError):
    """The real command plan could not be executed or verified."""


def strip_optional_quotes(value: str) -> str:
    """Remove one matching quote pair without modifying an unquoted value."""
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def load_env_file(path: Path) -> dict[str, str]:
    """Read dotenv values for redaction, never for shell evaluation.

    Acceptance criteria:
        1. Missing or malformed files raise without printing their contents.
        2. Comments and matching quotes are removed from ordinary dotenv values.
        3. The caller's process environment is not mutated.
        4. Docker Compose remains responsible for actual dotenv interpolation.
    """
    values: dict[str, str] = {}
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            raise ValueError(f"Invalid dotenv assignment on line {line_number}.")
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            raise ValueError(f"Invalid dotenv key on line {line_number}.")
        if value.startswith(("'", '"')):
            quote = value[0]
            match = re.fullmatch(rf"{quote}(.*?)(?<!\\){quote}\s*(?:#.*)?", value)
            if match is None:
                raise ValueError(f"Invalid quoted dotenv value on line {line_number}.")
            value = match.group(1)
        else:
            value = re.split(r"\s+#", value, maxsplit=1)[0].rstrip()
        values[key] = value
    return values


def merged_environment(
    env_file_values: Mapping[str, str], process_environment: Mapping[str, str]
) -> dict[str, str]:
    """Copy both mappings, with process values taking Compose precedence."""
    return {**env_file_values, **process_environment}


def redact_environment(environment: Mapping[str, str]) -> dict[str, str]:
    """Copy an environment mapping while concealing sensitive-looking values."""
    return {
        key: "<redacted>" if _sensitive_name(key) else value
        for key, value in sorted(environment.items())
    }


def _sensitive_name(name: str) -> bool:
    return any(part in name.upper() for part in SENSITIVE_ENV_PARTS)


def redact_output(
    value: str,
    *,
    environment: Mapping[str, str],
    secret_names: Sequence[str] = (),
) -> str:
    """Remove known credentials and common credential syntax from diagnostics.

    Acceptance criteria:
        1. Credentials supplied only in the dotenv file are also redacted.
        2. Longer secrets are replaced before overlapping shorter values.
        3. Bearer tokens, OpenAI keys, and URL credentials have syntax backstops.
        4. The input text and environment mapping are not modified.
    """
    names = set(secret_names)
    names.update(name for name in environment if _sensitive_name(name))
    secrets = sorted(
        {environment[name] for name in names if environment.get(name)},
        key=len,
        reverse=True,
    )
    result = value
    for secret in secrets:
        result = result.replace(secret, "<redacted>")
    result = re.sub(r"sk-[A-Za-z0-9_-]{8,}", "<redacted>", result)
    result = re.sub(r"(?i)(bearer\s+)[^\s\"']+", r"\1<redacted>", result)
    return re.sub(
        r"([A-Za-z][A-Za-z0-9+.-]*://)[^\s/:@]+:[^\s/@]+@",
        r"\1<redacted>@",
        result,
    )


def compose_command(
    compose_args: Sequence[str], profiles: Sequence[str] = ()
) -> list[str]:
    """Build a Compose command; the normal CPU stack needs no profile."""
    command = ["docker", "compose"]
    for profile in profiles:
        command.extend(("--profile", profile))
    return [*command, *compose_args]


def _compose_with_env_file(argv: Sequence[str], env_file: Path) -> tuple[str, ...]:
    if tuple(argv[:2]) != ("docker", "compose"):
        raise LiveRuntimeValidationError(
            "Runtime checks must run through Docker Compose."
        )
    return (*argv[:2], "--env-file", str(env_file.resolve()), *argv[2:])


def _output_text(value: str | bytes | None) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value or ""


def execute_runtime_command(
    spec: RuntimeCommandSpec,
    *,
    root: Path,
    env_file: Path,
    process_environment: Mapping[str, str],
    redaction_environment: Mapping[str, str],
    secret_names: Sequence[str],
) -> RuntimeCommandResult:
    """Execute one finite real subprocess and redact every captured channel.

    Acceptance criteria:
        1. Arguments are passed without a shell and Compose reads the given file.
        2. Missing Docker returns 127; timeouts return 124 with partial output.
        3. Failed commands remain failed and preserve their real diagnostics.
        4. No secret appears in recorded command arguments, stdout, or stderr.
    """
    if not math.isfinite(spec.timeout_seconds) or spec.timeout_seconds <= 0:
        raise LiveRuntimeValidationError(
            "Command timeouts must be positive and finite."
        )
    argv = _compose_with_env_file(spec.argv, env_file)
    started = time.monotonic()
    try:
        completed = subprocess.run(
            list(argv),
            cwd=root,
            env=dict(process_environment),
            capture_output=True,
            text=True,
            timeout=spec.timeout_seconds,
            check=False,
        )
        return_code = completed.returncode
        stdout, stderr = completed.stdout, completed.stderr
    except subprocess.TimeoutExpired as error:
        return_code = 124
        stdout, stderr = _output_text(error.stdout), _output_text(error.stderr)
        stderr += f"\nCommand timed out after {spec.timeout_seconds:g} seconds."
    except OSError as error:
        return_code, stdout = 127, ""
        stderr = f"Could not execute Docker Compose: {type(error).__name__}: {error}"

    def safe(text: str) -> str:
        return redact_output(
            text, environment=redaction_environment, secret_names=secret_names
        )

    return RuntimeCommandResult(
        name=spec.name,
        argv=tuple(safe(item) for item in argv),
        return_code=int(return_code),
        stdout=safe(stdout),
        stderr=safe(stderr),
        required=spec.required,
        elapsed_seconds=time.monotonic() - started,
    )


def _write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False
        ) as stream:
            temporary = Path(stream.name)
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def write_runtime_report(
    output_dir: Path, report_dict: Mapping[str, Any], markdown: str
) -> tuple[Path, Path]:
    """Atomically save the actual command report in JSON and Markdown."""
    report_id = str(report_dict["report_id"])
    json_path = output_dir / f"{report_id}_runtime_report.json"
    markdown_path = output_dir / f"{report_id}_runtime_report.md"
    _write_atomic(json_path, json.dumps(dict(report_dict), indent=2) + "\n")
    _write_atomic(markdown_path, markdown)
    return json_path, markdown_path


def run_validation(
    *,
    root: Path,
    env_file: Path,
    config: Mapping[str, Any],
    process_environment: Mapping[str, str],
    continue_after_failure: bool = False,
) -> dict[str, Any]:
    """Run the configured real stack, container checks, and full verification.

    Acceptance criteria:
        1. The plan includes a required verification command, never empty success.
        2. Required failures stop subsequent work unless explicitly overridden.
        3. Optional diagnostic commands still run after a required failure.
        4. Reports include skipped command names without inventing their results.
        5. Only observed command exits determine success; containers stay running.
    """
    file_environment = load_env_file(env_file)
    environment = merged_environment(file_environment, process_environment)
    commands = command_specs_from_config(config, environment)
    if not any(
        spec.name == "integration_full_stack" and spec.required for spec in commands
    ):
        raise LiveRuntimeValidationError(
            "Plan must require integration_full_stack verification."
        )
    for spec in commands:
        _compose_with_env_file(spec.argv, env_file)
        if not math.isfinite(spec.timeout_seconds) or spec.timeout_seconds <= 0:
            raise LiveRuntimeValidationError(
                "Command timeouts must be positive and finite."
            )
    secret_names = tuple(
        str(name) for name in config.get("secret_environment_names", [])
    )
    results: list[RuntimeCommandResult] = []
    skipped: list[str] = []
    failed_required = False
    for spec in commands:
        if failed_required and spec.required and not continue_after_failure:
            skipped.append(spec.name)
            continue
        print(f"Running {spec.name} ...", flush=True)
        result = execute_runtime_command(
            spec,
            root=root,
            env_file=env_file,
            process_environment=process_environment,
            redaction_environment=environment,
            secret_names=secret_names,
        )
        results.append(result)
        failed_required = failed_required or (spec.required and result.return_code != 0)
        print(f"{spec.name}: exit={result.return_code}", flush=True)
    # Historical log messages do not describe a failure of a successful run.
    patterns = (
        failure_patterns_from_config(config)
        if any(result.return_code != 0 for result in results)
        else ()
    )
    report = build_runtime_validation_report(results, patterns)
    payload = runtime_report_to_dict(report)
    payload["skipped_commands"] = skipped
    output_dir = root / str(config.get("report_output_dir", "data/runtime_validation"))
    markdown = render_runtime_report_markdown(report)
    if skipped:
        markdown += "\n## Skipped after a required failure\n\n"
        markdown += "\n".join(f"- `{name}`" for name in skipped) + "\n"
    json_path, markdown_path = write_runtime_report(output_dir, payload, markdown)
    return {
        "status": report.status,
        "report_id": report.report_id,
        "json_report": str(json_path),
        "markdown_report": str(markdown_path),
        "skipped_commands": skipped,
        "findings": [finding.category for finding in report.findings],
    }


def main() -> int:
    """Run the optional developer validation helper; Docker remains mandatory."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument(
        "--continue-after-failure",
        action="store_true",
        help="Attempt remaining required checks after failure; diagnostics always run.",
    )
    args = parser.parse_args()
    try:
        config = load_runtime_validation_config(args.config)
        if args.output_dir is not None:
            config["report_output_dir"] = str(args.output_dir.resolve())
        result = run_validation(
            root=ROOT,
            env_file=args.env_file,
            config=config,
            process_environment=os.environ,
            continue_after_failure=args.continue_after_failure,
        )
    except (OSError, ValueError, LiveRuntimeValidationError) as error:
        result = {
            "status": "failed",
            "error": redact_output(str(error), environment=os.environ),
        }
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
