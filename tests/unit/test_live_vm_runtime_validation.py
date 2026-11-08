"""Validate the Docker orchestration boundary without claiming a live deployment."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from translume_core.runtime_validation import RuntimeCommandSpec

from scripts import live_vm_runtime_validation as validation


def _spec(*, name: str = "integration_full_stack", required: bool = True):
    return RuntimeCommandSpec(
        name=name,
        argv=(
            "docker",
            "compose",
            "--profile",
            "verification",
            "run",
            "--rm",
            "verify",
        ),
        required=required,
        timeout_seconds=30,
    )


def test_default_plan_runs_only_current_container_checks() -> None:
    config = json.loads(validation.DEFAULT_CONFIG.read_text())
    commands = {command["name"]: command for command in config["commands"]}
    assert all(
        command["argv"][:2] == ["docker", "compose"] for command in commands.values()
    )
    assert commands["docker_compose_config"]["argv"][-1] == "--quiet"
    assert "--profile" not in commands["docker_compose_up"]["argv"]
    assert "--wait" in commands["docker_compose_up"]["argv"]
    assert commands["prime_directives_gate"]["argv"][2:5] == [
        "exec",
        "-T",
        "translume-api",
    ]
    assert (
        commands["prime_directives_gate"]["argv"][-1]
        == "/data/audit/runtime_diagnostics"
    )
    assert commands["preflight"]["argv"][-2:] == [
        "python",
        "scripts/full_stack_preflight.py",
    ]
    assert "verify" in commands["preflight"]["argv"]
    assert commands["integration_full_stack"]["argv"][-1] == "verify"
    assert commands["integration_full_stack"]["timeout_seconds"] > 2 * 21600
    assert commands["docker_compose_logs"]["required"] is False
    text = json.dumps(config).casefold()
    assert "nvidia" not in text
    assert "vllm" not in text
    assert "require-gpu" not in text


def test_dotenv_redaction_handles_quotes_comments_and_process_precedence(tmp_path):
    path = tmp_path / ".env"
    path.write_text(
        '# explanatory comment\nexport OPENAI_API_KEY="secret-from-file" # comment\n'
        "POSTGRES_DSN='postgresql://name:password@database/db'\n"
        "OPENAI_REASONING_MODEL=gpt-6-astra\n"
    )
    values = validation.load_env_file(path)
    assert values["OPENAI_API_KEY"] == "secret-from-file"
    merged = validation.merged_environment(
        values, {"OPENAI_REASONING_MODEL": "gpt-6-astra"}
    )
    assert validation.redact_environment(merged)["OPENAI_API_KEY"] == "<redacted>"
    text = validation.redact_output(
        "secret-from-file postgresql://name:password@database/db Bearer unknown-secret",
        environment=merged,
    )
    assert "secret-from-file" not in text
    assert "password" not in text
    assert "unknown-secret" not in text
    assert values["OPENAI_API_KEY"] == "secret-from-file"


def test_command_redacts_real_boundary_output_and_preserves_nonzero_status(
    tmp_path, monkeypatch
):
    seen = []

    def run(argv, **kwargs):
        seen.append((argv, kwargs))
        return subprocess.CompletedProcess(
            argv, 1, "credential-from-file", "Bearer uncatalogued-secret"
        )

    monkeypatch.setattr(validation.subprocess, "run", run)
    environment = {"PATH": "/unit/bin"}
    result = validation.execute_runtime_command(
        _spec(),
        root=tmp_path,
        env_file=tmp_path / ".env",
        process_environment=environment,
        redaction_environment={"OPENAI_API_KEY": "credential-from-file"},
        secret_names=(),
    )
    assert result.return_code == 1
    assert "credential-from-file" not in result.stdout
    assert "uncatalogued-secret" not in result.stderr
    assert seen[0][0][2:4] == ["--env-file", str(tmp_path / ".env")]
    assert seen[0][1]["env"] == environment
    assert "shell" not in seen[0][1]


@pytest.mark.parametrize("failure", ["timeout", "missing_docker"])
def test_command_failures_are_recorded_without_false_success(
    tmp_path, monkeypatch, failure
):
    def run(argv, **kwargs):
        if failure == "timeout":
            raise subprocess.TimeoutExpired(
                argv, 30, output=b"partial secret-value", stderr=b"timed out"
            )
        raise FileNotFoundError("docker executable is unavailable")

    monkeypatch.setattr(validation.subprocess, "run", run)
    result = validation.execute_runtime_command(
        _spec(),
        root=tmp_path,
        env_file=tmp_path / ".env",
        process_environment={},
        redaction_environment={"OPENAI_API_KEY": "secret-value"},
        secret_names=(),
    )
    assert result.return_code == (124 if failure == "timeout" else 127)
    assert "secret-value" not in result.stdout
    if failure == "timeout":
        assert "partial" in result.stdout
    assert result.stderr


def test_failure_skips_required_work_but_collects_diagnostics(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("OPENAI_API_KEY=unit-secret-from-env\n")
    calls = []

    def run(argv, **kwargs):
        calls.append(argv)
        return subprocess.CompletedProcess(
            argv, 1 if "config" in argv else 0, "unit-secret-from-env", ""
        )

    monkeypatch.setattr(validation.subprocess, "run", run)
    config = {
        "report_output_dir": "reports",
        "commands": [
            {"name": "config", "argv": ["docker", "compose", "config", "--quiet"]},
            {
                "name": "integration_full_stack",
                "argv": ["docker", "compose", "run", "--rm", "verify"],
            },
            {"name": "logs", "argv": ["docker", "compose", "logs"], "required": False},
        ],
    }
    result = validation.run_validation(
        root=tmp_path,
        env_file=env_file,
        config=config,
        process_environment={},
    )
    assert result["status"] == "failed"
    assert result["skipped_commands"] == ["integration_full_stack"]
    assert len(calls) == 2
    assert calls[-1][-1] == "logs"
    report = json.loads(Path(result["json_report"]).read_text())
    assert [command["name"] for command in report["command_results"]] == [
        "config",
        "logs",
    ]
    assert "unit-secret-from-env" not in json.dumps(report)
    assert "integration_full_stack" in Path(result["markdown_report"]).read_text()


def test_empty_plan_cannot_claim_success(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("OPENAI_API_KEY=unit-secret\n")
    with pytest.raises(
        validation.LiveRuntimeValidationError, match="integration_full_stack"
    ):
        validation.run_validation(
            root=tmp_path,
            env_file=env_file,
            config={"commands": []},
            process_environment={},
        )


def test_compose_command_has_no_implicit_profile():
    assert validation.compose_command(("up", "-d")) == ["docker", "compose", "up", "-d"]
    assert validation.compose_command(("run", "--rm", "verify"), ("verification",)) == [
        "docker",
        "compose",
        "--profile",
        "verification",
        "run",
        "--rm",
        "verify",
    ]
