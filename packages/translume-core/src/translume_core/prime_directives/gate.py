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

REQUIRED_TOOLUNIVERSE_WORKFLOWS: tuple[str, ...] = (
    "literature_validation",
    "pathway_context",
    "target_context",
    "variant_context",
    "trial_context_review",
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
    findings.extend(validate_required_tool_workflows(environment, root))
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
    root: Path,
) -> tuple[PrimeDirectiveFinding, ...]:
    """Validate all required governed ToolUniverse workflows are configured.

    Acceptance criteria:
        1. TRANSLUME_TOOL_WORKFLOWS must include every MVP-required workflow.
        2. The ToolUniverse workflow config file must exist.
        3. The config must define each required workflow with executable steps.
        4. Missing workflows are production-gate errors, not warnings.
    """
    findings: list[PrimeDirectiveFinding] = []
    requested = {
        item.strip()
        for item in env_value("TRANSLUME_TOOL_WORKFLOWS", environment).split(",")
        if item.strip()
    }
    missing_requested = sorted(set(REQUIRED_TOOLUNIVERSE_WORKFLOWS) - requested)
    if missing_requested:
        findings.append(
            PrimeDirectiveFinding(
                rule_id="tooluniverse:required_workflows_requested",
                severity="error",
                message=(
                    "TRANSLUME_TOOL_WORKFLOWS must include every MVP-required "
                    "governed workflow. Missing: " + ", ".join(missing_requested)
                ),
                next_actions=(
                    "Set TRANSLUME_TOOL_WORKFLOWS=literature_validation,pathway_context,target_context,variant_context,trial_context_review.",
                    "Rerun `make validate-prime-directives`.",
                ),
            )
        )
    config_path = Path(
        env_value("TOOLUNIVERSE_WORKFLOW_CONFIG", environment)
        or "configs/local/tooluniverse_workflows.json"
    )
    if not config_path.is_absolute():
        config_path = root / config_path
    if not config_path.exists():
        findings.append(
            PrimeDirectiveFinding(
                rule_id="tooluniverse:workflow_config_exists",
                severity="error",
                message=f"ToolUniverse workflow config is missing: {config_path}",
                next_actions=(
                    "Restore configs/local/tooluniverse_workflows.json or set TOOLUNIVERSE_WORKFLOW_CONFIG.",
                    "Do not bypass ToolUniverse evidence enrichment in production/demo mode.",
                ),
            )
        )
        return tuple(findings)
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        findings.append(
            PrimeDirectiveFinding(
                rule_id="tooluniverse:workflow_config_valid_json",
                severity="error",
                message=f"ToolUniverse workflow config is invalid JSON: {error}",
                next_actions=("Fix the JSON syntax and rerun the production gate.",),
            )
        )
        return tuple(findings)
    workflows = payload.get("workflows") if isinstance(payload, dict) else None
    if not isinstance(workflows, dict):
        findings.append(
            PrimeDirectiveFinding(
                rule_id="tooluniverse:workflow_config_object",
                severity="error",
                message="ToolUniverse workflow config must contain a workflows object.",
                next_actions=("Define a workflows object keyed by workflow name.",),
            )
        )
        return tuple(findings)
    missing_configured = sorted(set(REQUIRED_TOOLUNIVERSE_WORKFLOWS) - set(workflows.keys()))
    if missing_configured:
        findings.append(
            PrimeDirectiveFinding(
                rule_id="tooluniverse:required_workflows_configured",
                severity="error",
                message=(
                    "ToolUniverse workflow config must define every MVP-required workflow. Missing: "
                    + ", ".join(missing_configured)
                ),
                next_actions=(
                    "Configure literature_validation, pathway_context, target_context, variant_context, and trial_context_review.",
                    "Each workflow must map to real ToolUniverse tools and executable steps.",
                ),
            )
        )
    for workflow_name in REQUIRED_TOOLUNIVERSE_WORKFLOWS:
        spec = workflows.get(workflow_name)
        if not isinstance(spec, dict):
            continue
        steps = spec.get("steps")
        if not isinstance(steps, list) or not steps:
            findings.append(
                PrimeDirectiveFinding(
                    rule_id=f"tooluniverse:workflow_steps:{workflow_name}",
                    severity="error",
                    message=f"ToolUniverse workflow has no executable steps: {workflow_name}",
                    next_actions=("Add at least one step with a real ToolUniverse tool_name.",),
                )
            )
            continue
        for index, step in enumerate(steps):
            if not isinstance(step, dict) or not str(step.get("tool_name", "")).strip():
                findings.append(
                    PrimeDirectiveFinding(
                        rule_id=f"tooluniverse:workflow_tool_name:{workflow_name}:{index}",
                        severity="error",
                        message=f"ToolUniverse workflow step missing tool_name: {workflow_name}[{index}]",
                        next_actions=("Set tool_name to an actual ToolUniverse registry tool.",),
                    )
                )
    return tuple(findings)


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
