"""CPU-only tests using the real SDK and a local HTTP test transport."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import httpx
import openai_runtime as remote
import pytest
import tumor_board_causal_synthesis as synthesis
from openai import OpenAI
from pydantic import BaseModel

import dynamic_pathway_analyzer as analyzer


class Echo(BaseModel):
    value: str
    optional: str | None = None


def sdk_response(
    text: str = '{"value":"unit","optional":null}',
    *,
    status: str = "completed",
    reason: str = "max_output_tokens",
    refusal: bool = False,
    web: bool = False,
    response_id: str = "resp_unit",
) -> dict[str, Any]:
    content = [{"type": "output_text", "text": text, "annotations": []}]
    if refusal:
        content.append({"type": "refusal", "refusal": "Unit refusal."})
    output: list[dict[str, Any]] = [
        {
            "id": "msg_unit",
            "type": "message",
            "role": "assistant",
            "status": "completed",
            "content": content,
        }
    ]
    if web:
        output.insert(
            0,
            {
                "id": "ws_unit",
                "type": "web_search_call",
                "status": "completed",
                "action": {
                    "type": "search",
                    "query": "unit query",
                    "sources": [
                        {
                            "type": "url",
                            "url": "https://pubmed.ncbi.nlm.nih.gov/1/",
                            "title": "Unit-test source metadata",
                        }
                    ],
                },
            },
        )
    return {
        "id": response_id,
        "object": "response",
        "created_at": 0,
        "status": status,
        "model": "gpt-6-astra",
        "output": output,
        "incomplete_details": {"reason": reason} if status == "incomplete" else None,
        "usage": {"input_tokens": 100, "output_tokens": 200, "total_tokens": 300},
    }


def sdk_client(handler: Any) -> OpenAI:
    return OpenAI(
        api_key="unit-test-only",
        base_url=remote.OFFICIAL_BASE_URL,
        max_retries=0,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def invoke(client: OpenAI, tmp_path: Path, **settings):
    return remote.request_response(
        client,
        stage="unit",
        request={
            "model": "gpt-6-astra",
            "input": "unit input",
            "text": remote.text_format(Echo),
        },
        settings=remote.RemoteSettings(**settings),
        audit_dir=tmp_path,
    )


def test_remote_policy_and_audit_use_actual_sdk_metadata(tmp_path: Path):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            200, json=sdk_response(), headers={"x-request-id": "req_unit"}
        )

    with sdk_client(handler) as client:
        response = invoke(client, tmp_path)
        output = remote.structured_output(response, Echo, stage="unit")
    assert output.value == "unit"
    body = json.loads(calls[0].content)
    assert str(calls[0].url) == "https://api.openai.com/v1/responses"
    assert body["reasoning"] == {"mode": "pro", "effort": "xhigh"}
    assert body["store"] is False
    assert body["max_output_tokens"] == 32000
    assert body["text"]["format"]["schema"]["required"] == ["value", "optional"]
    record = json.loads(next(tmp_path.glob("*.json")).read_text())
    assert record["request_id"] == "req_unit"
    assert record["response_id"] == "resp_unit"
    assert record["usage"]["total_tokens"] == 300
    assert record["reasoning_mode"] == "pro"
    assert "unit input" not in json.dumps(record)
    assert "unit-test-only" not in json.dumps(record)


@pytest.mark.parametrize(
    "status,code",
    [
        (401, "invalid_api_key"),
        (403, "permission_denied"),
        (429, "insufficient_quota"),
        (400, "invalid_request_error"),
    ],
)
def test_terminal_failures_do_not_retry(tmp_path, status, code):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            status,
            json={
                "error": {
                    "code": code,
                    "message": "Private request content.",
                }
            },
            headers={"x-request-id": "req_failure"},
        )

    with (
        sdk_client(handler) as client,
        pytest.raises(remote.OpenAIRequestFailure) as captured,
    ):
        invoke(client, tmp_path, max_attempts=5)
    assert len(calls) == 1
    assert "Private" not in str(captured.value)
    assert "req_failure" in str(captured.value)
    record = json.loads(next(tmp_path.glob("*.json")).read_text())
    assert record["outcome"] == "failed"
    assert record["error_code"] == code


@pytest.mark.parametrize(
    "status,reason,refusal",
    [
        ("incomplete", "content_filter", False),
        ("completed", "max_output_tokens", True),
        ("failed", "max_output_tokens", False),
    ],
)
def test_partial_text_and_refusals_never_succeed(tmp_path, status, reason, refusal):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            200, json=sdk_response(status=status, reason=reason, refusal=refusal)
        )

    with sdk_client(handler) as client, pytest.raises(remote.OpenAIRequestFailure):
        invoke(client, tmp_path, max_attempts=5)
    assert len(calls) == 1


def test_truncation_retry_has_one_larger_bound_and_retains_failed_usage(tmp_path):
    calls = []

    def handler(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200, json=sdk_response(status="incomplete"))

    with sdk_client(handler) as client, pytest.raises(remote.OpenAIRequestFailure):
        invoke(client, tmp_path, max_attempts=5)
    assert [call["max_output_tokens"] for call in calls] == [32000, 64000]
    records = [json.loads(path.read_text()) for path in tmp_path.glob("*.json")]
    assert len(records) == 2
    assert all(record["usage"]["total_tokens"] == 300 for record in records)
    assert all(record["outcome"] == "failed" for record in records)


def case_map() -> analyzer.NormalizedCaseMap:
    return analyzer.NormalizedCaseMap(
        case=analyzer.CaseContext(
            disease="unit diagnosis",
            histology="unit histology",
            report_date="PRIVATE_DATE",
            location="PRIVATE_LOCATION",
            specimen_site="PRIVATE_SPECIMEN",
            prior_therapies=["PRIVATE_HISTORY"],
        ),
        findings=[
            analyzer.NormalizedFinding(
                finding_id="finding_unit",
                gene_or_marker="UNIT1",
                display_label="unit finding",
                alteration="unit alteration",
                alteration_type="unit type",
                source_texts=["PRIVATE_SOURCE"],
            )
        ],
        pathway_hypotheses=[
            analyzer.PathwayHypothesis(
                pathway_id="pathway_unit",
                title="unit pathway",
                pathway_type="other",
                involved_findings=["finding_unit"],
                patient_specific_basis="PRIVATE_BASIS",
                simplified_pathway=["unit step"],
                research_queries=["PRIVATE_QUERY"],
                caution="unit caution",
            )
        ],
    )


def report() -> analyzer.FinalReport:
    return analyzer.FinalReport(
        title="Unit pipeline report",
        case_summary="unit summary",
        overall_interpretation="unit interpretation",
        pathways=[],
        cross_pathway_interactions=[],
        missing_information_that_limits_use=[],
        no_assumption_statements=[],
        final_biological_significance="unit biology",
        final_clinical_actionability="unit uncertainty",
        final_required_confirmation="unit confirmation",
        disclaimer="Unit-test fixture.",
    )


def test_public_search_payload_excludes_identifying_fields_without_mutation():
    original = case_map()
    before = original.model_dump(mode="json")
    minimized = analyzer.biomedical_search_payload(original, "unit diagnosis")
    encoded = json.dumps(minimized)
    assert "PRIVATE_" not in encoded
    assert "UNIT1" in encoded
    assert "unit diagnosis" in encoded
    assert original.model_dump(mode="json") == before


def test_full_dynamic_flow_uses_four_real_sdk_requests_and_writes_audit(
    tmp_path, monkeypatch
):
    requests = []

    def handler(request):
        body = json.loads(request.content)
        requests.append(body)
        schema_name = body.get("text", {}).get("format", {}).get("name")
        if schema_name == "NormalizedCaseMap":
            data = sdk_response(
                case_map().model_dump_json(), response_id="resp_normalizer"
            )
        elif schema_name == "FinalReport":
            data = sdk_response(
                report().model_dump_json(), response_id="resp_finalizer"
            )
        else:
            data = sdk_response(
                "Unit research memo with a recorded source.",
                web=True,
                response_id=f"resp_research_{len(requests)}",
            )
        return httpx.Response(200, json=data)

    monkeypatch.setattr(analyzer, "OPENAI_API_KEY", "unit-test-only")
    monkeypatch.setattr(
        remote, "build_client", lambda key, settings: sdk_client(handler)
    )
    input_path = tmp_path / "case.json"
    input_path.write_text('{"diagnosis":"unit diagnosis"}')
    output_dir = tmp_path / "output"
    json_path, md_path = analyzer.analyze_file(
        input_path,
        output_dir,
        "gpt-6-astra",
        "gpt-6-astra",
        "unit diagnosis",
    )
    assert len(requests) == 4
    assert all(
        body["reasoning"] == {"mode": "pro", "effort": "xhigh"} for body in requests
    )
    assert all(body["store"] is False for body in requests)
    assert all(body["max_output_tokens"] == 32000 for body in requests)
    assert "PRIVATE_" not in requests[1]["input"][1]["content"]
    assert "PRIVATE_" not in requests[2]["input"][1]["content"]
    assert "PRIVATE_DATE" in requests[3]["input"][1]["content"]
    assert json.loads(json_path.read_text())["title"] == "Unit pipeline report"
    assert md_path.read_text().startswith("# Unit pipeline report")
    assert len(list((output_dir / "openai_calls").glob("*.json"))) == 4
    manifest = json.loads((output_dir / "case.openai_manifest.json").read_text())
    assert manifest["reasoning_mode"] == "pro"


def test_tumor_board_request_uses_pro_without_web(tmp_path):
    calls = []

    def handler(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200, json=sdk_response("# Unit synthesis"))

    with sdk_client(handler) as client:
        response = synthesis.call_with_retries(
            client,
            model="gpt-6-astra",
            system_prompt="unit instructions",
            user_message="unit evidence",
            attempts=2,
            reasoning_effort="xhigh",
            audit_dir=tmp_path,
        )
    assert response.output_text == "# Unit synthesis"
    assert calls[0]["reasoning"] == {"mode": "pro", "effort": "xhigh"}
    assert "tools" not in calls[0]
    assert calls[0]["store"] is False


def test_wire_schemas_preserve_properties_and_nullable_values():
    schema = {
        "type": "object",
        "properties": {"default": {"type": "string", "default": "unit"}},
    }
    before = copy.deepcopy(schema)
    converted = remote.strict_schema(schema)
    assert schema == before
    assert converted["properties"]["default"] == {"type": "string"}
    for model in (analyzer.NormalizedCaseMap, analyzer.FinalReport):
        wire = remote.text_format(model)["format"]["schema"]
        assert wire["additionalProperties"] is False
        assert set(wire["required"]) == set(wire["properties"])


def test_bad_json_does_not_echo_model_content(tmp_path):
    def handler(request):
        return httpx.Response(200, json=sdk_response("PRIVATE_INVALID_JSON"))

    with sdk_client(handler) as client:
        response = invoke(client, tmp_path)
        with pytest.raises(remote.OpenAIRequestFailure) as captured:
            remote.structured_output(response, Echo, stage="unit")
    assert "PRIVATE_INVALID_JSON" not in str(captured.value)


def test_nonofficial_endpoint_and_standard_mode_are_rejected(monkeypatch):
    with pytest.raises(ValueError, match="must be pro"):
        remote.RemoteSettings(reasoning_mode="standard")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://localhost:8000/v1")
    with pytest.raises(ValueError, match="OPENAI_BASE_URL"):
        remote.build_client("unit-test-only", remote.RemoteSettings())


def test_invalid_completed_output_is_recorded_as_failed_with_usage(tmp_path):
    def handler(request):
        return httpx.Response(200, json=sdk_response('{"wrong":"PRIVATE"}'))

    with (
        sdk_client(handler) as client,
        pytest.raises(remote.OpenAIRequestFailure),
    ):
        remote.request_response(
            client,
            stage="unit",
            request={"model": "gpt-6-astra", "input": "unit"},
            settings=remote.RemoteSettings(),
            audit_dir=tmp_path,
            response_model=Echo,
        )
    receipt = json.loads(next(tmp_path.glob("*.json")).read_text())
    assert receipt["outcome"] == "failed"
    assert receipt["domain_validation"] == "failed"
    assert receipt["usage"]["total_tokens"] == 300
    assert "PRIVATE" not in json.dumps(receipt)
