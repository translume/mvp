from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

import precision_oncology_runner


def test_pipeline_command_forwards_configured_request_timeout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Runner timeout configuration must reach the pipeline CLI."""
    monkeypatch.setenv("PRECISION_ONCOLOGY_REQUEST_TIMEOUT_SECONDS", "900")

    command = precision_oncology_runner._pipeline_command(
        tmp_path / "input.json",
        tmp_path / "outputs",
    )

    assert command[0] == sys.executable
    timeout_index = command.index("--request-timeout")
    assert command[timeout_index + 1] == "900"


def test_run_directory_requires_a_child_of_output_root(tmp_path: Path) -> None:
    """Runner should reject command output outside its configured output root."""
    output_root = tmp_path / "outputs"
    output_root.mkdir()
    run_directory = output_root / "run-1"
    run_directory.mkdir()

    resolved = precision_oncology_runner._run_directory_from_stdout(
        f"run_dir={run_directory}\n",
        output_root,
    )

    assert resolved == run_directory.resolve()
    with pytest.raises(HTTPException):
        precision_oncology_runner._run_directory_from_stdout(
            f"run_dir={tmp_path}\n",
            output_root,
        )


def test_failure_diagnostic_prefers_final_pipeline_error(tmp_path: Path) -> None:
    """Verbose Pydantic warnings must not hide the actionable final error."""
    output_root = tmp_path / "outputs"
    run_directory = output_root / "run_test"
    run_directory.mkdir(parents=True)
    for stage in precision_oncology_runner._STAGE_ORDER[:7]:
        (run_directory / f"state_after_{stage}.json").write_text("{}")
    warning = "PydanticSerializationUnexpectedValue " * 300
    result = subprocess.CompletedProcess(
        args=["pipeline"],
        returncode=1,
        stdout="",
        stderr=(
            f"UserWarning: Pydantic serializer warnings: {warning}\n"
            "2026-07-15 ERROR Pipeline failed: synthesis validation failed"
        ),
    )

    diagnostic = precision_oncology_runner._pipeline_failure_diagnostic(
        result,
        output_root,
    )

    assert diagnostic.error.endswith("Pipeline failed: synthesis validation failed")
    assert diagnostic.inferred_stage == "hypothesis_syntheses"
    assert diagnostic.pydantic_warnings_summarized is True
    assert warning.strip() not in diagnostic.error


def test_failure_diagnostic_uses_bounded_redacted_stderr_fallback(
    tmp_path: Path,
) -> None:
    """Fallback diagnostics use the tail and redact credential-shaped text."""
    result = subprocess.CompletedProcess(
        args=["pipeline"],
        returncode=2,
        stdout="unused stdout",
        stderr=f"{'old warning ' * 300} api_key=sk-secretvalue123 final failure",
    )

    diagnostic = precision_oncology_runner._pipeline_failure_diagnostic(
        result,
        tmp_path / "missing",
    )

    assert len(diagnostic.error) <= 2000
    assert diagnostic.error.endswith("api_key [REDACTED] final failure")
    assert "sk-secretvalue123" not in diagnostic.error


def test_failure_diagnostic_falls_back_to_stdout(tmp_path: Path) -> None:
    """Stdout remains useful when the subprocess produces no stderr."""
    result = subprocess.CompletedProcess(
        args=["pipeline"],
        returncode=1,
        stdout="final stdout failure",
        stderr="",
    )

    diagnostic = precision_oncology_runner._pipeline_failure_diagnostic(
        result,
        tmp_path / "missing",
    )

    assert diagnostic.error == "final stdout failure"
    assert diagnostic.inferred_stage is None


def test_persist_failure_diagnostic_is_session_scoped(tmp_path: Path) -> None:
    """Diagnostics are atomically persisted in the latest run directory."""
    session_root = tmp_path / "session_test"
    output_root = session_root / "outputs"
    run_directory = output_root / "run_test"
    run_directory.mkdir(parents=True)
    diagnostic = precision_oncology_runner.PipelineFailureDiagnostic(
        exit_code=1,
        inferred_stage="hypothesis_syntheses",
        error="validation failed",
        pydantic_warnings_summarized=True,
    )

    precision_oncology_runner._persist_failure_diagnostic(
        diagnostic,
        session_root,
        output_root,
    )

    persisted = run_directory / "pipeline_failure.json"
    assert persisted.is_file()
    assert "validation failed" in persisted.read_text()


def test_pipeline_command_propagates_shared_openai_roles(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_REASONING_MODEL", "gpt-6-astra")
    monkeypatch.setenv("OPENAI_REASONING_MODE", "pro")
    monkeypatch.setenv("OPENAI_REASONING_EFFORT", "xhigh")
    monkeypatch.setenv("OPENAI_MODEL", "ignored-legacy-model")
    command = precision_oncology_runner._pipeline_command(
        tmp_path / "input.json",
        tmp_path / "outputs",
    )
    assert command[command.index("--model") + 1] == "gpt-6-astra"
    assert command[command.index("--reasoning-mode") + 1] == "pro"
    assert command[command.index("--reasoning-effort") + 1] == "xhigh"


def test_runner_timeout_persists_failure_and_returns_gateway_timeout(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(precision_oncology_runner, "_ARTIFACT_ROOT", tmp_path)
    monkeypatch.setenv("PRECISION_ONCOLOGY_RUN_TIMEOUT_SECONDS", "5")

    def timeout_run(command, **kwargs):
        assert kwargs["timeout"] == 5
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(precision_oncology_runner.subprocess, "run", timeout_run)
    with pytest.raises(HTTPException) as captured:
        precision_oncology_runner.run_precision_pipeline(
            precision_oncology_runner.PrecisionRunRequest(
                session_id="session_unit",
                review_packet={"unit": True},
            )
        )
    assert captured.value.status_code == 504
    diagnostic = tmp_path / "session_unit" / "pipeline_failure.json"
    assert diagnostic.is_file()
    assert '"exit_code": 124' in diagnostic.read_text()


def test_health_requires_remote_configuration_without_disclosing_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(HTTPException) as captured:
        precision_oncology_runner.health()
    assert captured.value.status_code == 503
    monkeypatch.setenv("OPENAI_API_KEY", "unit-test-only")
    monkeypatch.setenv("OPENAI_REASONING_MODE", "pro")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    response = precision_oncology_runner.health()
    assert response["provider"] == "openai"
    assert "unit-test-only" not in str(response)
