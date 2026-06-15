from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


class RuntimeValidationConfigError(ValueError):
    """Raised when runtime validation configuration is invalid."""


@dataclass(frozen=True)
class RuntimeCommandSpec:
    """Represent one executable runtime command.

    Attributes:
        name: Human-readable command name.
        argv: Command vector to execute.
        required: Whether failure should fail the whole validation.
        timeout_seconds: Command timeout.
    """

    name: str
    argv: tuple[str, ...]
    required: bool
    timeout_seconds: float


@dataclass(frozen=True)
class RuntimeCommandResult:
    """Represent the observed result of one runtime command.

    Attributes:
        name: Human-readable command name.
        argv: Command vector that was executed.
        return_code: Process return code.
        stdout: Captured standard output.
        stderr: Captured standard error.
        required: Whether this command was required.
        elapsed_seconds: Runtime duration in seconds.
    """

    name: str
    argv: tuple[str, ...]
    return_code: int
    stdout: str
    stderr: str
    required: bool
    elapsed_seconds: float


@dataclass(frozen=True)
class RuntimeFailurePattern:
    """Represent one configured failure pattern.

    Attributes:
        category: Failure category label.
        patterns: Case-insensitive substrings that trigger the category.
        explanation: Human-readable failure explanation.
        next_actions: Concrete repair commands or checks for the operator.
    """

    category: str
    patterns: tuple[str, ...]
    explanation: str
    next_actions: tuple[str, ...]


@dataclass(frozen=True)
class RuntimeFailureFinding:
    """Represent one detected runtime failure category.

    Attributes:
        category: Failure category label.
        matched_patterns: Patterns that matched captured output.
        explanation: Human-readable explanation.
        next_actions: Suggested real repair steps.
    """

    category: str
    matched_patterns: tuple[str, ...]
    explanation: str
    next_actions: tuple[str, ...]


@dataclass(frozen=True)
class RuntimeValidationReport:
    """Represent a complete live VM runtime validation report.

    Attributes:
        status: `ok` if every required command succeeded, else `failed`.
        report_id: Stable hash of command results and findings.
        command_results: Observed runtime command results.
        findings: Classified failure findings.
    """

    status: str
    report_id: str
    command_results: tuple[RuntimeCommandResult, ...]
    findings: tuple[RuntimeFailureFinding, ...]


def load_runtime_validation_config(path: Path) -> dict[str, Any]:
    """Load runtime validation configuration from JSON.

    Acceptance criteria:
        1. Determinism: Same file content returns the same dictionary.
        2. Validation: Missing files raise `FileNotFoundError`.
        3. Validation: Non-object JSON raises `RuntimeValidationConfigError`.
        4. No mutation: Returned dictionary is caller-owned.

    Args:
        path: Configuration file path.

    Returns:
        Parsed configuration dictionary.

    Raises:
        FileNotFoundError: If `path` does not exist.
        RuntimeValidationConfigError: If JSON root is not an object.
    """
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeValidationConfigError(
            "runtime validation config must be a JSON object"
        )
    return dict(payload)


def command_specs_from_config(
    config: Mapping[str, Any],
    environment: Mapping[str, str],
) -> tuple[RuntimeCommandSpec, ...]:
    """Return runtime command specs from config.

    Acceptance criteria:
        1. Determinism: Same config and environment return the same specs.
        2. Validation: Missing `commands` config raises `RuntimeValidationConfigError`.
        3. Expansion: Environment variables in argv values are expanded.
        4. No mutation: Config and environment are not mutated.

    Args:
        config: Runtime validation configuration.
        environment: Environment variable mapping used for expansion.

    Returns:
        Tuple of command specs.

    Raises:
        RuntimeValidationConfigError: If command config is malformed.
    """
    raw_commands = config.get("commands")
    if not isinstance(raw_commands, list):
        raise RuntimeValidationConfigError("commands must be a list")
    return tuple(
        _command_spec_from_mapping(raw_command, environment)
        for raw_command in raw_commands
    )


def _command_spec_from_mapping(
    raw_command: Any,
    environment: Mapping[str, str],
) -> RuntimeCommandSpec:
    if not isinstance(raw_command, dict):
        raise RuntimeValidationConfigError("each command must be an object")
    argv = raw_command.get("argv")
    if not isinstance(argv, list) or not argv:
        raise RuntimeValidationConfigError("command argv must be a non-empty list")
    return RuntimeCommandSpec(
        name=str(raw_command.get("name", argv[0])),
        argv=tuple(expand_env_value(str(item), environment) for item in argv),
        required=bool(raw_command.get("required", True)),
        timeout_seconds=float(raw_command.get("timeout_seconds", 120.0)),
    )


def expand_env_value(value: str, environment: Mapping[str, str]) -> str:
    """Expand simple `${NAME}` environment placeholders.

    Acceptance criteria:
        1. Determinism: Same value and environment return same string.
        2. No mutation: Environment mapping is not modified.
        3. Unknown variables expand to an empty string.
        4. Literal strings without placeholders are unchanged.

    Args:
        value: Raw value potentially containing `${NAME}`.
        environment: Environment mapping.

    Returns:
        Expanded string.
    """
    output = value
    for key, env_value in environment.items():
        output = output.replace("${" + key + "}", env_value)
    while "${" in output:
        start = output.find("${")
        end = output.find("}", start)
        if end == -1:
            return output
        output = output[:start] + output[end + 1 :]
    return output


def failure_patterns_from_config(
    config: Mapping[str, Any],
) -> tuple[RuntimeFailurePattern, ...]:
    """Return failure patterns from runtime validation config.

    Acceptance criteria:
        1. Determinism: Same config returns the same patterns.
        2. Validation: Missing patterns default to an empty tuple.
        3. Validation: Malformed pattern entries raise a config error.
        4. No mutation: Config is not modified.

    Args:
        config: Runtime validation config.

    Returns:
        Tuple of failure pattern objects.
    """
    raw_patterns = config.get("failure_patterns", [])
    if not isinstance(raw_patterns, list):
        raise RuntimeValidationConfigError("failure_patterns must be a list")
    patterns: list[RuntimeFailurePattern] = []
    for raw_pattern in raw_patterns:
        if not isinstance(raw_pattern, dict):
            raise RuntimeValidationConfigError("failure pattern must be an object")
        raw_terms = raw_pattern.get("patterns", [])
        raw_actions = raw_pattern.get("next_actions", [])
        if not isinstance(raw_terms, list) or not isinstance(raw_actions, list):
            raise RuntimeValidationConfigError(
                "failure pattern terms and actions must be lists"
            )
        patterns.append(
            RuntimeFailurePattern(
                category=str(raw_pattern["category"]),
                patterns=tuple(str(item) for item in raw_terms),
                explanation=str(raw_pattern.get("explanation", "")),
                next_actions=tuple(str(item) for item in raw_actions),
            )
        )
    return tuple(patterns)


def classify_runtime_failures(
    results: Sequence[RuntimeCommandResult],
    patterns: Sequence[RuntimeFailurePattern],
) -> tuple[RuntimeFailureFinding, ...]:
    """Classify runtime failures from captured command output.

    Acceptance criteria:
        1. Determinism: Same results and patterns return same findings.
        2. Case-insensitive matching: Pattern matching ignores case.
        3. Required failure: Non-zero required command is always surfaced.
        4. No mutation: Inputs are not modified.

    Args:
        results: Runtime command results.
        patterns: Failure patterns loaded from config.

    Returns:
        Tuple of failure findings.
    """
    combined_text = "\n".join(
        f"{result.name}\n{result.stdout}\n{result.stderr}"
        for result in results
    ).casefold()
    findings: list[RuntimeFailureFinding] = []
    for pattern in patterns:
        matched = tuple(
            term for term in pattern.patterns if term.casefold() in combined_text
        )
        if matched:
            findings.append(
                RuntimeFailureFinding(
                    category=pattern.category,
                    matched_patterns=matched,
                    explanation=pattern.explanation,
                    next_actions=pattern.next_actions,
                )
            )
    failed_required = tuple(
        result.name for result in results if result.required and result.return_code != 0
    )
    if failed_required:
        findings.append(
            RuntimeFailureFinding(
                category="required_command_failed",
                matched_patterns=failed_required,
                explanation="One or more required runtime validation commands failed.",
                next_actions=(
                    "Open the generated diagnostics report.",
                    "Run `make live-vm-logs` to inspect service logs.",
                    "Fix the first failing required command before rerunning validation.",
                ),
            )
        )
    return tuple(_dedupe_findings(findings))


def _dedupe_findings(
    findings: Sequence[RuntimeFailureFinding],
) -> list[RuntimeFailureFinding]:
    seen: set[str] = set()
    deduped: list[RuntimeFailureFinding] = []
    for finding in findings:
        if finding.category in seen:
            continue
        seen.add(finding.category)
        deduped.append(finding)
    return deduped


def build_runtime_validation_report(
    results: Sequence[RuntimeCommandResult],
    patterns: Sequence[RuntimeFailurePattern],
) -> RuntimeValidationReport:
    """Build a runtime validation report from observed commands.

    Acceptance criteria:
        1. Status is `ok` only when all required commands return zero.
        2. Failure findings are computed from output and return codes.
        3. Report ID is deterministic for report content.
        4. Function is pure.

    Args:
        results: Runtime command results.
        patterns: Configured failure patterns.

    Returns:
        Runtime validation report.
    """
    findings = classify_runtime_failures(results, patterns)
    required_failures = [
        result for result in results if result.required and result.return_code != 0
    ]
    status = "failed" if required_failures else "ok"
    payload = {
        "status": status,
        "command_results": [asdict(result) for result in results],
        "findings": [asdict(finding) for finding in findings],
    }
    report_id = hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
    return RuntimeValidationReport(
        status=status,
        report_id=report_id,
        command_results=tuple(results),
        findings=findings,
    )


def runtime_report_to_dict(report: RuntimeValidationReport) -> dict[str, Any]:
    """Return a JSON-serializable runtime validation report dictionary.

    Acceptance criteria:
        1. Output is JSON-serializable.
        2. Preserves all command results.
        3. Preserves all failure findings.
        4. Function is pure.
    """
    return {
        "status": report.status,
        "report_id": report.report_id,
        "command_results": [asdict(result) for result in report.command_results],
        "findings": [asdict(finding) for finding in report.findings],
    }


def render_runtime_report_markdown(report: RuntimeValidationReport) -> str:
    """Render runtime validation report as Markdown.

    Acceptance criteria:
        1. Determinism: Same report returns same Markdown.
        2. Includes status and report ID.
        3. Includes failed command names.
        4. Includes next actions for classified failures.
    """
    lines = [
        "# Translume Live VM Runtime Validation Report",
        "",
        f"Status: **{report.status}**",
        f"Report ID: `{report.report_id}`",
        "",
        "## Commands",
    ]
    for result in report.command_results:
        lines.append(
            f"- `{result.name}` returned `{result.return_code}` "
            f"in `{result.elapsed_seconds:.2f}s`"
        )
    lines.extend(["", "## Findings"])
    if not report.findings:
        lines.append("- No classified failures.")
    for finding in report.findings:
        lines.append(f"### {finding.category}")
        lines.append(finding.explanation or "No explanation configured.")
        lines.append("")
        lines.append("Next actions:")
        lines.extend(f"- {action}" for action in finding.next_actions)
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def redact_sensitive_text(
    text: str,
    secret_names: Sequence[str],
    environment: Mapping[str, str],
) -> str:
    """Redact configured secret values from diagnostic output.

    Acceptance criteria:
        1. Determinism: Same text and environment return same redaction.
        2. No mutation: Environment is not modified.
        3. Blank secret values are ignored.
        4. Function is pure.
    """
    redacted = text
    for name in secret_names:
        value = environment.get(name, "")
        if value:
            redacted = redacted.replace(value, "<redacted:" + name + ">")
    return redacted
