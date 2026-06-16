from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

from translume_core.vendor.repositories import (
    VendorRepositoryError,
    load_vendor_repo_specs,
    require_updateable_vendor_repos,
)


class PrimeDirectiveViolation(RuntimeError):
    """Raised when production/demo runtime violates Translume PRIME_DIRECTIVES."""


@dataclass(frozen=True)
class PrimeDirectiveFinding:
    """Represent one production-gate violation or warning.

    Attributes:
        rule_id: Stable rule identifier.
        severity: `error` or `warning`.
        message: Human-readable problem description.
        next_actions: Real repair steps. No cosmetic bypasses.
    """

    rule_id: str
    severity: str
    message: str
    next_actions: tuple[str, ...]


@dataclass(frozen=True)
class PrimeDirectiveGateReport:
    """Represent the result of a PRIME_DIRECTIVES production gate check.

    Attributes:
        ok: True only when no error findings exist.
        active: Whether the gate was enforced for this run.
        mode: Observed Translume environment mode.
        findings: Gate findings.
    """

    ok: bool
    active: bool
    mode: str
    findings: tuple[PrimeDirectiveFinding, ...]


REQUIRED_TRUE_FLAGS: tuple[str, ...] = (
    "TRANSLUME_REQUIRE_MIMS",
    "TRANSLUME_REQUIRE_DOCLING",
    "TRANSLUME_REQUIRE_OPENSEARCH",
    "TRANSLUME_REQUIRE_POSTGRES",
    "BLOCK_REMOTE_MODEL_PROVIDERS",
)

REQUIRED_NONEMPTY_ENV: tuple[str, ...] = (
    "VLLM_BASE_URL",
    "VLLM_MODEL",
    "DOCLING_SERVICE_URL",
    "OPTIMUSKG_SERVICE_URL",
    "TOOLUNIVERSE_SERVICE_URL",
    "MEDEA_SERVICE_URL",
    "OPENSEARCH_URL",
    "POSTGRES_DSN",
)

REMOTE_PROVIDER_SECRET_ENV: tuple[str, ...] = (
    "OPENAI_API_KEY",
    "OPENROUTER_API_KEY",
    "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "AZURE_OPENAI_API_KEY",
    "AZURE_OPENAI_ENDPOINT",
    "NVIDIA_API_KEY",
    "NVIDIA_API_BASE",
)

DISALLOWED_MODEL_IDS: tuple[str, ...] = (
    "",
    "local-clinical-model",
    "placeholder",
    "mock",
    "dummy",
    "test",
)

REMOTE_PROVIDER_INACTIVE_VALUES: tuple[str, ...] = (
    "",
    "none",
    "null",
    "disabled",
    "not-used",
    "local-not-used",
    "local_only",
    "local-only",
)

PRODUCTION_MODES: tuple[str, ...] = ("production", "prod", "demo", "live")


def should_enforce_prime_directives(environment: Mapping[str, str]) -> bool:
    """Return whether the production gate should be active.

    Acceptance criteria:
        1. Production/demo/live modes activate the gate.
        2. TRANSLUME_ENFORCE_PRIME_DIRECTIVES=true activates the gate.
        3. Local mode without explicit enforcement remains inactive.
        4. Function is pure and does not mutate environment.
    """
    mode = env_value("TRANSLUME_ENV", environment).casefold()
    explicit = truthy(env_value("TRANSLUME_ENFORCE_PRIME_DIRECTIVES", environment))
    return explicit or mode in PRODUCTION_MODES


def validate_prime_directives(
    *,
    environment: Mapping[str, str],
    root: Path,
    force: bool = False,
) -> PrimeDirectiveGateReport:
    """Validate that production/demo runtime cannot start with fake paths.

    Acceptance criteria:
        1. Inactive local mode returns an inactive OK report.
        2. Forced/production/demo mode validates required runtime flags.
        3. MIMS upstream repositories must be real updateable Git clones.
        4. Remote model provider credentials must not be active.
        5. UI Docker entrypoint must run real Gradio, not Uvicorn ASGI shim.
        6. Report does not mutate filesystem, environment, or vendor repos.
    """
    mode = env_value("TRANSLUME_ENV", environment) or "local"
    active = force or should_enforce_prime_directives(environment)
    if not active:
        return PrimeDirectiveGateReport(ok=True, active=False, mode=mode, findings=())

    findings: list[PrimeDirectiveFinding] = []
    findings.extend(validate_required_true_flags(environment))
    findings.extend(validate_required_nonempty_environment(environment))
    findings.extend(validate_vllm_model(environment))
    findings.extend(validate_remote_provider_environment(environment))
    findings.extend(validate_vendor_repositories(root))
    findings.extend(validate_ui_docker_entrypoint(root))
    findings.extend(validate_required_tool_workflows(environment))
    ok = all(finding.severity != "error" for finding in findings)
    return PrimeDirectiveGateReport(
        ok=ok,
        active=True,
        mode=mode,
        findings=tuple(findings),
    )


def assert_prime_directives(
    *,
    environment: Mapping[str, str],
    root: Path,
    force: bool = False,
) -> PrimeDirectiveGateReport:
    """Return gate report or raise on PRIME_DIRECTIVES violations."""
    report = validate_prime_directives(environment=environment, root=root, force=force)
    if report.ok:
        return report
    raise PrimeDirectiveViolation(render_prime_directives_report(report))


def validate_required_true_flags(
    environment: Mapping[str, str],
) -> tuple[PrimeDirectiveFinding, ...]:
    """Validate production-required booleans are explicitly true."""
    findings: list[PrimeDirectiveFinding] = []
    for name in REQUIRED_TRUE_FLAGS:
        if not truthy(env_value(name, environment)):
            findings.append(
                PrimeDirectiveFinding(
                    rule_id=f"required_true:{name}",
                    severity="error",
                    message=(
                        f"{name} must be true in production/demo mode. "
                        "The MVP may not silently bypass required services or "
                        "remote-provider blocking."
                    ),
                    next_actions=(
                        f"Set {name}=true in .env or deployment configuration.",
                        "Rerun `make validate-prime-directives`.",
                    ),
                )
            )
    return tuple(findings)


def validate_required_nonempty_environment(
    environment: Mapping[str, str],
) -> tuple[PrimeDirectiveFinding, ...]:
    """Validate required service/model endpoints are configured."""
    findings: list[PrimeDirectiveFinding] = []
    for name in REQUIRED_NONEMPTY_ENV:
        if not env_value(name, environment):
            findings.append(
                PrimeDirectiveFinding(
                    rule_id=f"required_env:{name}",
                    severity="error",
                    message=f"{name} is required for production/demo runtime.",
                    next_actions=(
                        f"Set {name} to the real service value in .env.",
                        "Do not use blank values to bypass missing dependencies.",
                    ),
                )
            )
    return tuple(findings)


def validate_vllm_model(environment: Mapping[str, str]) -> tuple[PrimeDirectiveFinding, ...]:
    """Validate local vLLM clinical model identifier is real, not placeholder."""
    model = env_value("VLLM_MODEL", environment)
    if model.casefold() in {value.casefold() for value in DISALLOWED_MODEL_IDS}:
        return (
            PrimeDirectiveFinding(
                rule_id="vllm_model:not_placeholder",
                severity="error",
                message=(
                    "VLLM_MODEL must be a real local/Hugging Face model id. "
                    f"Observed disallowed value: {model!r}."
                ),
                next_actions=(
                    "Set VLLM_MODEL to the real clinical structured-output model id.",
                    "Rerun `make validate-prime-directives` and the live VM validator.",
                ),
            ),
        )
    return ()


def validate_remote_provider_environment(
    environment: Mapping[str, str],
) -> tuple[PrimeDirectiveFinding, ...]:
    """Validate remote model provider credentials are not active."""
    findings: list[PrimeDirectiveFinding] = []
    for name in REMOTE_PROVIDER_SECRET_ENV:
        value = env_value(name, environment)
        if value and value.casefold() not in REMOTE_PROVIDER_INACTIVE_VALUES:
            findings.append(
                PrimeDirectiveFinding(
                    rule_id=f"remote_provider_blocked:{name}",
                    severity="error",
                    message=(
                        f"{name} is active. Production/demo mode must route model "
                        "calls to local vLLM and must not expose remote provider "
                        "credentials."
                    ),
                    next_actions=(
                        f"Unset {name} for the Translume runtime.",
                        "If a third-party package requires this key syntactically, set it to local-not-used and route the provider to VLLM_BASE_URL.",
                    ),
                )
            )
    return tuple(findings)


def validate_vendor_repositories(root: Path) -> tuple[PrimeDirectiveFinding, ...]:
    """Validate required MIMS upstream repos are updateable Git clones."""
    config_path = root / "third_party" / "vendor_repos.json"
    try:
        specs = load_vendor_repo_specs(config_path, root)
        require_updateable_vendor_repos(specs)
    except (FileNotFoundError, VendorRepositoryError) as error:
        return (
            PrimeDirectiveFinding(
                rule_id="mims_vendors:updateable_git_clones",
                severity="error",
                message=(
                    "MIMS upstream repositories must be real updateable Git clones. "
                    f"Details: {error}"
                ),
                next_actions=(
                    "Run `make vendor-repos` on a networked VM.",
                    "Run `make vendor-status` and confirm every repository is OK.",
                    "Do not use zip-extracted vendor directories for production/demo validation.",
                ),
            ),
        )
    return ()


def validate_ui_docker_entrypoint(root: Path) -> tuple[PrimeDirectiveFinding, ...]:
    """Validate UI container runs Gradio directly, not a fake ASGI shim."""
    dockerfile = root / "docker" / "ui.Dockerfile"
    if not dockerfile.exists():
        return (
            PrimeDirectiveFinding(
                rule_id="ui_dockerfile:exists",
                severity="error",
                message=f"UI Dockerfile is missing: {dockerfile}",
                next_actions=("Restore docker/ui.Dockerfile.",),
            ),
        )
    content = dockerfile.read_text(encoding="utf-8")
    findings: list[PrimeDirectiveFinding] = []
    if "uvicorn translume_ui.app:app" in content:
        findings.append(
            PrimeDirectiveFinding(
                rule_id="ui_dockerfile:no_uvicorn_asgi_shim",
                severity="error",
                message=(
                    "UI Dockerfile still attempts to run Gradio as "
                    "uvicorn translume_ui.app:app."
                ),
                next_actions=(
                    "Change the UI command to `python -m translume_ui.app`.",
                    "Rerun `make check-ui-health` after starting the stack.",
                ),
            )
        )
    if "python" not in content or "-m" not in content or "translume_ui.app" not in content:
        findings.append(
            PrimeDirectiveFinding(
                rule_id="ui_dockerfile:gradio_module_entrypoint",
                severity="error",
                message=(
                    "UI Dockerfile must launch the real Gradio module entrypoint "
                    "with python -m translume_ui.app."
                ),
                next_actions=(
                    "Set docker/ui.Dockerfile CMD to run `python -m translume_ui.app`.",
                ),
            )
        )
    return tuple(findings)


def validate_required_tool_workflows(
    environment: Mapping[str, str],
) -> tuple[PrimeDirectiveFinding, ...]:
    """Validate at least one governed ToolUniverse workflow is configured.

    Full workflow coverage is repaired in Tutorial 9. This gate only prevents a
    blank ToolUniverse product path in production/demo mode.
    """
    workflows = [
        item.strip()
        for item in env_value("TRANSLUME_TOOL_WORKFLOWS", environment).split(",")
        if item.strip()
    ]
    if not workflows:
        return (
            PrimeDirectiveFinding(
                rule_id="tooluniverse:workflows_nonempty",
                severity="error",
                message=(
                    "TRANSLUME_TOOL_WORKFLOWS must name real governed workflows. "
                    "A blank ToolUniverse path would hide missing evidence enrichment."
                ),
                next_actions=(
                    "Set TRANSLUME_TOOL_WORKFLOWS to configured workflow names.",
                    "Tutorial 9 must map every required workflow to a real ToolUniverse tool.",
                ),
            ),
        )
    return ()


def env_value(name: str, environment: Mapping[str, str]) -> str:
    return environment.get(name, "").strip()


def truthy(value: str) -> bool:
    return value.casefold() in {"1", "true", "yes", "y", "on"}


def load_env_file(path: Path) -> dict[str, str]:
    """Load simple KEY=VALUE lines from an env file.

    Acceptance criteria:
        1. Missing files return an empty mapping.
        2. Comments and blank lines are ignored.
        3. Quoted values are unwrapped.
        4. No shell evaluation or command interpolation is performed.
    """
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def merge_environment_file(
    *,
    env_file: Path,
    process_environment: Mapping[str, str],
) -> dict[str, str]:
    """Return env file values overridden by process environment."""
    merged = load_env_file(env_file)
    merged.update(dict(process_environment))
    return merged


def find_project_root(start: Path) -> Path:
    """Return nearest ancestor containing docker-compose.yml and pyproject.toml."""
    candidate = start.resolve()
    if candidate.is_file():
        candidate = candidate.parent
    for path in (candidate, *candidate.parents):
        if (path / "docker-compose.yml").exists() and (path / "pyproject.toml").exists():
            return path
    raise PrimeDirectiveViolation(
        f"could not find Translume project root from {start}"
    )


def prime_directives_report_to_dict(report: PrimeDirectiveGateReport) -> dict[str, object]:
    """Return a JSON-serializable production gate report."""
    return {
        "ok": report.ok,
        "active": report.active,
        "mode": report.mode,
        "findings": [asdict(finding) for finding in report.findings],
    }


def render_prime_directives_report(report: PrimeDirectiveGateReport) -> str:
    """Render a human-readable PRIME_DIRECTIVES gate report."""
    header = (
        f"PRIME_DIRECTIVES gate: {'OK' if report.ok else 'FAILED'} "
        f"(active={report.active}, mode={report.mode})"
    )
    if not report.findings:
        return header
    lines = [header]
    for finding in report.findings:
        lines.append(f"- [{finding.severity}] {finding.rule_id}: {finding.message}")
        for action in finding.next_actions:
            lines.append(f"  next: {action}")
    return "\n".join(lines)


def write_prime_directives_reports(
    *,
    report: PrimeDirectiveGateReport,
    output_dir: Path,
) -> tuple[Path, Path]:
    """Write JSON and Markdown reports for operator diagnostics."""
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "prime_directives_gate.json"
    md_path = output_dir / "prime_directives_gate.md"
    json_path.write_text(
        json.dumps(prime_directives_report_to_dict(report), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    md_path.write_text(render_prime_directives_report(report) + "\n", encoding="utf-8")
    return json_path, md_path
