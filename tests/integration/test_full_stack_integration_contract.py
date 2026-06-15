from __future__ import annotations

import os
from pathlib import Path

import pytest

from scripts.full_stack_preflight import (
    PreflightError,
    load_requirements,
    validate_model_identifier,
    validate_report_path,
    validate_required_environment,
)
from scripts.run_full_stack_integration import (
    assert_absent_phrases,
    assert_non_empty_paths,
    get_path,
    is_non_empty,
)


ROOT = Path(__file__).resolve().parents[2]


def test_full_stack_requirements_are_loadable() -> None:
    requirements = load_requirements(
        ROOT / "configs" / "integration" / "full_stack_requirements.json"
    )
    assert "review_packet_required_non_empty_paths" in requirements
    assert "vllm" in requirements


def test_required_environment_reports_all_missing_values() -> None:
    with pytest.raises(PreflightError) as exc_info:
        validate_required_environment(("A", "B"), {"A": ""})
    message = str(exc_info.value)
    assert "A" in message
    assert "B" in message


def test_validate_model_identifier_rejects_configured_placeholder_values() -> None:
    with pytest.raises(PreflightError):
        validate_model_identifier("local-clinical-model", ["local-clinical-model"])
    assert validate_model_identifier("hf-org/model-name", ["local-clinical-model"]) == "hf-org/model-name"


def test_validate_report_path_requires_real_pdf(tmp_path: Path) -> None:
    report = tmp_path / "report.pdf"
    report.write_bytes(b"%PDF-1.4\n% real enough for path validation\n")
    assert validate_report_path(str(report)) == report.resolve()
    with pytest.raises(PreflightError):
        validate_report_path(str(tmp_path / "missing.pdf"))


def test_nested_path_extraction_and_non_empty_validation() -> None:
    payload = {"bundle": {"claims": [{"claim_id": "claim1"}]}}
    assert get_path(payload, "bundle.claims.0.claim_id") == "claim1"
    assert is_non_empty(" value ") is True
    assert is_non_empty("") is False
    assert assert_non_empty_paths(payload, ["bundle.claims.0.claim_id"])
    with pytest.raises(Exception):
        assert_non_empty_paths(payload, ["bundle.claims.1.claim_id"])


def test_absent_phrase_check_blocks_unsafe_output() -> None:
    assert_absent_phrases({"text": "molecular fit for expert review"}, ["recommended treatment"])
    with pytest.raises(Exception):
        assert_absent_phrases({"text": "recommended treatment"}, ["recommended treatment"])


@pytest.mark.skipif(
    os.getenv("RUN_FULL_STACK_INTEGRATION") != "true",
    reason="set RUN_FULL_STACK_INTEGRATION=true to run real Docker/GPU/local-vLLM integration",
)
def test_real_full_stack_integration_entrypoint_is_opt_in() -> None:
    # The real integration is executed by scripts/run_full_stack_integration.py
    # after Docker Compose services are running. This test intentionally avoids
    # simulating services because the MVP rule is no mocked product path.
    assert os.getenv("TRANSLUME_E2E_REPORT_PATH")
