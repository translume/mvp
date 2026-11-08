from __future__ import annotations

from pathlib import Path

import dynamic_pathway_runner
import pytest
from fastapi import HTTPException


def test_require_markdown_rejects_missing_and_empty_artifacts(tmp_path: Path) -> None:
    """Runner should return only existing non-empty Markdown artifacts."""
    missing = tmp_path / "missing.md"
    with pytest.raises(HTTPException):
        dynamic_pathway_runner._require_markdown(missing, "Missing")

    empty = tmp_path / "empty.md"
    empty.write_text("\n", encoding="utf-8")
    with pytest.raises(HTTPException):
        dynamic_pathway_runner._require_markdown(empty, "Empty")

    completed = tmp_path / "completed.md"
    completed.write_text("# Completed\n", encoding="utf-8")
    assert (
        dynamic_pathway_runner._require_markdown(completed, "Completed")
        == "# Completed"
    )


def test_runner_propagates_shared_models_mode_effort_and_deadline(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(dynamic_pathway_runner, "_ARTIFACT_ROOT", tmp_path)
    monkeypatch.setenv("OPENAI_REASONING_MODEL", "gpt-6-astra")
    monkeypatch.setenv("OPENAI_NORMALIZER_MODEL", "gpt-6-astra")
    monkeypatch.setenv("OPENAI_REASONING_MODE", "pro")
    monkeypatch.setenv("OPENAI_REASONING_EFFORT", "xhigh")
    monkeypatch.setenv("DYNAMIC_PATHWAY_RUN_TIMEOUT_SECONDS", "7200")
    input_path = (
        tmp_path
        / "session_unit"
        / "precision_oncology_outputs"
        / "run_unit"
        / "state_after_trial_prescreens.json"
    )
    input_path.parent.mkdir(parents=True)
    input_path.write_text('{"unit":true}')
    calls = []

    def record_command(label, command, *, timeout_seconds):
        calls.append((command, timeout_seconds))
        output = Path(command[command.index("--output-dir") + 1])
        output.mkdir(parents=True)
        if len(calls) == 1:
            (output / "state_after_trial_prescreens.pathway_analysis.md").write_text(
                "# Unit pathway"
            )
            (output / "state_after_trial_prescreens.research_memo.md").write_text(
                "# Unit research"
            )
        else:
            (output / "onco_board_summary.md").write_text("# Unit summary")

    monkeypatch.setattr(dynamic_pathway_runner, "_run_command", record_command)
    response = dynamic_pathway_runner.run_dynamic_pathway_analysis(
        dynamic_pathway_runner.DynamicRunRequest(
            session_id="session_unit",
            precision_run_id="run_unit",
            diagnosis="unit diagnosis",
        )
    )
    assert response.tumor_board_summary_markdown == "# Unit summary"
    assert len(calls) == 2
    for command, timeout in calls:
        assert command[command.index("--model") + 1] == "gpt-6-astra"
        assert command[command.index("--reasoning-mode") + 1] == "pro"
        assert command[command.index("--reasoning-effort") + 1] == "xhigh"
        assert 0 < timeout <= 7200
    assert calls[1][1] <= calls[0][1]


def test_command_timeout_is_explicit(monkeypatch):
    import subprocess

    def timeout_run(command, **kwargs):
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(dynamic_pathway_runner.subprocess, "run", timeout_run)
    with pytest.raises(HTTPException) as captured:
        dynamic_pathway_runner._run_command("unit", ["unit"], timeout_seconds=4)
    assert captured.value.status_code == 504
    assert "4 seconds" in captured.value.detail


def test_runner_redacts_failure_credentials(monkeypatch):
    import subprocess

    monkeypatch.setattr(
        dynamic_pathway_runner.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            ["unit"],
            1,
            stdout="",
            stderr="api_key=sk-unitsecret123 Bearer token-value failure",
        ),
    )
    with pytest.raises(HTTPException) as captured:
        dynamic_pathway_runner._run_command("unit", ["unit"])
    assert "sk-unitsecret123" not in captured.value.detail
    assert "token-value" not in captured.value.detail
    assert "failure" in captured.value.detail


def test_elapsed_deadline_blocks_the_next_subprocess(monkeypatch):
    monkeypatch.setattr(dynamic_pathway_runner.time, "monotonic", lambda: 10.0)
    with pytest.raises(HTTPException) as captured:
        dynamic_pathway_runner._remaining_seconds(9.0)
    assert captured.value.status_code == 504
