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
    build_vllm_structured_output_request,
    get_path,
    health_field_mismatch,
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


def test_health_field_mismatch_accepts_workflows_in_any_order() -> None:
    expected = [
        "literature_validation",
        "pathway_context",
        "target_context",
        "variant_context",
        "trial_context_review",
    ]
    payload = {
        "configured_workflows": [
            "literature_validation",
            "pathway_context",
            "target_context",
            "trial_context_review",
            "variant_context",
        ]
    }
    assert health_field_mismatch("configured_workflows", expected, payload) is None


def test_health_field_mismatch_rejects_missing_workflow() -> None:
    expected = [
        "literature_validation",
        "pathway_context",
        "target_context",
        "variant_context",
        "trial_context_review",
    ]
    payload = {
        "configured_workflows": [
            "literature_validation",
            "pathway_context",
            "target_context",
            "trial_context_review",
        ]
    }
    mismatch = health_field_mismatch("configured_workflows", expected, payload)
    assert mismatch is not None
    assert "variant_context" in mismatch


def test_health_field_mismatch_accepts_omitted_empty_missing_workflows() -> None:
    assert health_field_mismatch("missing_required_workflows", [], {}) is None
    assert (
        health_field_mismatch(
            "missing_required_workflows",
            ["variant_context"],
            {},
        )
        is not None
    )


def test_vllm_preflight_request_uses_single_user_message() -> None:
    schema = {"name": "status_schema", "schema": {"type": "object"}}
    request = build_vllm_structured_output_request(
        model="local-model",
        schema=schema,
    )
    assert request["model"] == "local-model"
    assert request["response_format"] == {
        "type": "json_schema",
        "json_schema": schema,
    }
    assert request["messages"] == [
        {
            "role": "user",
            "content": (
                "Return only schema-valid JSON for this status check. "
                "Return status ready for Translume."
            ),
        }
    ]
    assert schema == {"name": "status_schema", "schema": {"type": "object"}}


@pytest.mark.skipif(
    os.getenv("RUN_FULL_STACK_INTEGRATION") != "true",
    reason="set RUN_FULL_STACK_INTEGRATION=true to run real Docker/GPU/local-vLLM integration",
)
def test_real_full_stack_integration_entrypoint_is_opt_in() -> None:
    # The real integration is executed by scripts/run_full_stack_integration.py
    # after Docker Compose services are running. This test intentionally avoids
    # simulating services because the MVP rule is no mocked product path.
    assert os.getenv("TRANSLUME_E2E_REPORT_PATH")
