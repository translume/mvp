"""Network-isolated tests of the real OpenAI SDK production boundary."""

from __future__ import annotations

import asyncio
import copy
import dataclasses
import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from openai import OpenAI

import precision_oncology_pipeline as pipeline


class Echo(pipeline.StrictModel):
    value: str
    optional: str | None = None


def response_payload(
    *,
    status: str = "completed",
    refusal: bool = False,
    response_id: str = "resp_unit",
    reason: str = "max_output_tokens",
) -> dict[str, Any]:
    content: list[dict[str, Any]] = [
        {
            "type": "output_text",
            "text": '{"value":"unit","optional":null}',
            "annotations": [],
        }
    ]
    if refusal:
        content.append({"type": "refusal", "refusal": "Unit-test refusal."})
    return {
        "id": response_id,
        "object": "response",
        "created_at": 0,
        "status": status,
        "model": "gpt-6-astra",
        "incomplete_details": {"reason": reason} if status == "incomplete" else None,
        "output": [
            {
                "id": "msg_unit",
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": content,
            }
        ],
        "usage": {"input_tokens": 20, "output_tokens": 15, "total_tokens": 35},
    }


def gateway_with_transport(tmp_path: Path, handler: Any, **overrides: Any):
    config = pipeline.PipelineConfig(
        api_key="unit-test-credential",
        model="gpt-6-astra",
        reasoning_effort="xhigh",
        output_dir=tmp_path,
        **overrides,
    )
    gateway = pipeline.OpenAIResponsesGateway(
        config,
        pipeline.ArtifactStore(tmp_path, "run_unit"),
    )
    gateway._client = OpenAI(
        api_key=config.api_key,
        base_url=pipeline.OPENAI_BASE_URL,
        max_retries=0,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    return gateway


def invoke(gateway: pipeline.OpenAIResponsesGateway) -> pipeline.ModelResult[Echo]:
    prompt = pipeline.PromptSpec(
        name="unit",
        version="1",
        system="Return test data.",
        user_label="INPUT",
        max_output_tokens=1000,
    )
    return gateway._call_with_retry(
        "unit",
        prompt,
        {"unit": "input"},
        Echo,
        False,
        (),
        False,
    )


def test_sdk_request_is_remote_pro_and_strict(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200, json=response_payload(), headers={"x-request-id": "req_unit"}
        )

    with gateway_with_transport(tmp_path, handler) as gateway:
        result = invoke(gateway)
    request = requests[0]
    body = json.loads(request.content)
    assert str(request.url) == "https://api.openai.com/v1/responses"
    assert request.headers["authorization"] == "Bearer unit-test-credential"
    assert body["reasoning"] == {"mode": "pro", "effort": "xhigh"}
    assert body["store"] is False
    assert body["max_output_tokens"] == 32000
    assert "temperature" not in body
    schema = body["text"]["format"]["schema"]
    assert schema["required"] == ["value", "optional"]
    assert schema["additionalProperties"] is False
    assert "default" not in schema["properties"]["optional"]
    assert result.request_id == "req_unit"
    assert result.reasoning_mode == "pro"
    assert result.reasoning_effort == "xhigh"
    receipt = json.loads(
        next((tmp_path / "run_unit" / "calls").glob("*_attempt_1.json")).read_text()
    )
    assert receipt["usage"]["total_tokens"] == 35
    assert receipt["response_id"] == "resp_unit"
    assert "unit-test-credential" not in json.dumps(receipt)
    assert "Return test data" not in json.dumps(receipt)


@pytest.mark.parametrize(
    "status,code",
    [
        (401, "invalid_api_key"),
        (403, "permission_denied"),
        (429, "insufficient_quota"),
        (400, "invalid_request_error"),
    ],
)
def test_terminal_api_failures_make_one_attempt(
    tmp_path: Path,
    status: int,
    code: str,
) -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            status,
            json={
                "error": {
                    "message": "Sensitive request text must not reach logs.",
                    "type": "api_error",
                    "code": code,
                }
            },
            headers={"x-request-id": "req_failed"},
        )

    with (
        gateway_with_transport(tmp_path, handler, max_attempts=4) as gateway,
        pytest.raises(RuntimeError) as captured,
    ):
        invoke(gateway)
    assert len(calls) == 1
    assert "Sensitive" not in str(captured.value)
    assert "req_failed" in str(captured.value)
    receipt = json.loads(
        next((tmp_path / "run_unit" / "calls").glob("*_attempt_1.json")).read_text()
    )
    assert receipt["outcome"] == "failed"
    assert receipt["status_code"] == status
    assert receipt["error_code"] == code
    assert receipt["requested_model"] == "gpt-6-astra"
    assert receipt["model"] is None


def test_server_retry_retains_failed_and_successful_receipts(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(pipeline.time, "sleep", lambda _: None)

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(503, json={"error": {"code": "server_error"}})
        return httpx.Response(200, json=response_payload())

    with gateway_with_transport(tmp_path, handler, max_attempts=3) as gateway:
        result = invoke(gateway)
    assert result.attempts == 2
    assert len(calls) == 2
    records = [
        json.loads(path.read_text())
        for path in (tmp_path / "run_unit" / "calls").glob("*_attempt_*.json")
    ]
    assert {record["outcome"] for record in records} == {"failed", "succeeded"}


@pytest.mark.parametrize(
    "status,refusal,reason",
    [
        ("completed", True, "max_output_tokens"),
        ("incomplete", False, "content_filter"),
        ("failed", False, "max_output_tokens"),
    ],
)
def test_partial_valid_json_and_refusals_are_never_success(
    tmp_path,
    status,
    refusal,
    reason,
):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            200, json=response_payload(status=status, refusal=refusal, reason=reason)
        )

    with (
        gateway_with_transport(tmp_path, handler, max_attempts=5) as gateway,
        pytest.raises(pipeline.OpenAIParsedOutputError),
    ):
        invoke(gateway)
    assert len(calls) == 1


def test_output_limit_gets_one_larger_attempt_with_truthful_provenance(
    tmp_path, monkeypatch
):
    calls = []
    monkeypatch.setattr(pipeline.time, "sleep", lambda _: None)

    def handler(request):
        calls.append(json.loads(request.content))
        status = "incomplete" if len(calls) == 1 else "completed"
        return httpx.Response(200, json=response_payload(status=status))

    with gateway_with_transport(tmp_path, handler, max_attempts=5) as gateway:
        result = invoke(gateway)
    assert [call["max_output_tokens"] for call in calls] == [32000, 64000]
    assert calls[1]["reasoning"] == {"mode": "pro", "effort": "low"}
    assert result.reasoning_effort == "low"
    assert result.attempts == 2
    assert result.cacheable is False


def test_cache_identity_includes_mode_effort_and_schema(tmp_path):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=response_payload())

    prompt = pipeline.PromptSpec("unit", "1", "Return data.", "INPUT", 1000)

    async def run(gateway):
        return await gateway.structured_call(
            stage="unit",
            artifact_id="artifact_unit",
            prompt=prompt,
            payload={"unit": True},
            response_model=Echo,
        )

    with gateway_with_transport(tmp_path, handler) as gateway:
        first = asyncio.run(run(gateway))
        cached = asyncio.run(run(gateway))
        assert first.cache_hit is False
        assert cached.cache_hit is True
        assert cached.reasoning_mode == "pro"
        assert len(requests) == 1
        gateway.config = dataclasses.replace(gateway.config, reasoning_effort="medium")
        changed = asyncio.run(run(gateway))
        assert changed.cache_hit is False
        assert len(requests) == 2
    caches = [
        json.loads(path.read_text()) for path in (tmp_path / "_cache").glob("*.json")
    ]
    assert {cache["reasoning_effort"] for cache in caches} == {"xhigh", "medium"}


def test_schema_conversion_preserves_field_named_default():
    schema = {
        "type": "object",
        "properties": {
            "default": {"type": "string", "default": "value"},
            "nullable": {
                "anyOf": [{"type": "string"}, {"type": "null"}],
                "default": None,
            },
        },
    }
    before = copy.deepcopy(schema)
    wire = pipeline.openai_wire_schema(schema)
    assert schema == before
    assert wire["properties"]["default"] == {"type": "string"}
    assert wire["required"] == ["default", "nullable"]


@pytest.mark.parametrize("web_status", [None, "failed"])
def test_mandatory_web_search_requires_a_completed_tool_call(tmp_path, web_status):
    requests = []

    def handler(request):
        requests.append(request)
        payload = response_payload()
        if web_status is not None:
            payload["output"].insert(
                0,
                {
                    "id": "search_unit",
                    "type": "web_search_call",
                    "status": web_status,
                    "action": {"type": "search", "query": "unit"},
                },
            )
        return httpx.Response(200, json=payload)

    with (
        gateway_with_transport(tmp_path, handler, max_attempts=5) as gateway,
        pytest.raises(RuntimeError, match="domain validation"),
    ):
        gateway._call_with_retry(
            "source_discovery",
            pipeline.PROMPTS["source_discovery"],
            {"biomedical_topic": "unit"},
            Echo,
            True,
            ("clinicaltrials.gov",),
            True,
        )
    assert len(requests) == 1
    receipt = json.loads(
        next((tmp_path / "run_unit" / "calls").glob("*_attempt_1.json")).read_text()
    )
    assert receipt["completed_web_searches"] == 0
    assert receipt["outcome"] == "failed"
    assert receipt["usage"]["total_tokens"] == 35


def test_all_actual_generation_schemas_are_compatible():
    models = (
        pipeline.HypothesisBuilderOutput,
        pipeline.ResearchPlanOutput,
        pipeline.SourceDiscoveryOutput,
        pipeline.SourceExtraction,
        pipeline.SourceFitAssessment,
        pipeline.TrialPrescreen,
        pipeline.HypothesisSynthesis,
        pipeline.ReportDraft,
        pipeline.CrossSourceSynthesis,
        pipeline.ValidationOutput,
    )
    for model in models:
        schema = pipeline.openai_wire_schema(model.model_json_schema())
        assert schema["additionalProperties"] is False
        assert set(schema["required"]) == set(schema["properties"])


def test_nonofficial_base_url_is_rejected_before_network(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "http://localhost:8000/v1")
    with pytest.raises(ValueError, match="OPENAI_BASE_URL"):
        pipeline.OpenAIResponsesGateway(
            pipeline.PipelineConfig(
                api_key="unit-test",
                model="gpt-6-astra",
                reasoning_effort="xhigh",
                output_dir=tmp_path,
            ),
            pipeline.ArtifactStore(tmp_path, "run_rejected"),
        )
