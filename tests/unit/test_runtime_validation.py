from __future__ import annotations

from translume_core.runtime_validation import (
    RuntimeCommandResult,
    RuntimeFailurePattern,
    build_runtime_validation_report,
    command_specs_from_config,
    expand_env_value,
    failure_patterns_from_config,
    redact_sensitive_text,
    render_runtime_report_markdown,
    runtime_report_to_dict,
)


def test_expand_env_value_replaces_known_and_unknown_variables() -> None:
    assert expand_env_value("${A}/path/${B}", {"A": "root"}) == "root/path/"
    assert expand_env_value("literal", {"A": "root"}) == "literal"


def test_command_specs_from_config_expands_environment() -> None:
    config = {
        "commands": [
            {
                "name": "example",
                "argv": ["echo", "${VALUE}"],
                "required": True,
                "timeout_seconds": 3,
            }
        ]
    }
    specs = command_specs_from_config(config, {"VALUE": "ok"})
    assert specs[0].argv == ("echo", "ok")
    assert specs[0].required is True


def test_failure_patterns_from_config_and_classification() -> None:
    config = {
        "failure_patterns": [
            {
                "category": "gpu_unavailable",
                "patterns": ["nvidia-smi"],
                "explanation": "GPU failure.",
                "next_actions": ["Check GPU."],
            }
        ]
    }
    patterns = failure_patterns_from_config(config)
    report = build_runtime_validation_report(
        [
            RuntimeCommandResult(
                name="gpu_state",
                argv=("nvidia-smi",),
                return_code=1,
                stdout="",
                stderr="nvidia-smi failed",
                required=True,
                elapsed_seconds=0.1,
            )
        ],
        patterns,
    )
    assert report.status == "failed"
    categories = {finding.category for finding in report.findings}
    assert "gpu_unavailable" in categories
    assert "required_command_failed" in categories


def test_runtime_report_serialization_and_markdown() -> None:
    report = build_runtime_validation_report(
        [
            RuntimeCommandResult(
                name="preflight",
                argv=("python", "scripts/full_stack_preflight.py"),
                return_code=0,
                stdout="ok",
                stderr="",
                required=True,
                elapsed_seconds=1.2,
            )
        ],
        [],
    )
    payload = runtime_report_to_dict(report)
    markdown = render_runtime_report_markdown(report)
    assert payload["status"] == "ok"
    assert "preflight" in markdown
    assert report.report_id in markdown


def test_redact_sensitive_text_uses_configured_secret_names() -> None:
    text = "postgresql://user:pass@host/db and public"
    redacted = redact_sensitive_text(
        text,
        ["POSTGRES_DSN"],
        {"POSTGRES_DSN": "postgresql://user:pass@host/db"},
    )
    assert "pass" not in redacted
    assert "<redacted:POSTGRES_DSN>" in redacted
