from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from translume_clients.openai_client import (
    OpenAIClient,
    OpenAISyncClient,
    normalize_count_request,
    validate_openai_base_url,
)
from translume_schemas.model_calls import (
    ModelAuthenticationError,
    ModelIncompleteError,
    ModelOutputTruncatedError,
    ModelQuotaError,
    ModelRefusalError,
    ModelResponseError,
    ModelTimeoutError,
)


def _completed(text: str = '{"value":1}') -> dict[str, object]:
    return {
        "id": "resp_observed",
        "model": "gpt-6-astra",
        "status": "completed",
        "output": [
            {"type": "reasoning", "summary": []},
            {"type": "message", "content": [{"type": "output_text", "text": text}]},
        ],
        "usage": {
            "input_tokens": 125,
            "output_tokens": 210,
            "total_tokens": 335,
            "input_tokens_details": {"cached_tokens": 10},
            "output_tokens_details": {"reasoning_tokens": 200},
        },
    }


@pytest.mark.asyncio
async def test_remote_request_is_authenticated_and_audit_contains_only_metadata(
    tmp_path,
):
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(
            200, json=_completed(), headers={"x-request-id": "req_observed"}
        )

    journal = tmp_path / "calls.jsonl"
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        client = OpenAIClient("test-secret", http_client=http, audit_path=journal)
        client.bind_correlation_id("session_123")
        result = await client.structured_completion(
            {
                "model": "gpt-6-astra",
                "input": "private clinical source text",
                "reasoning": {"mode": "pro", "effort": "xhigh"},
                "store": True,
            }
        )
        with pytest.raises(ValueError, match="after an OpenAI request"):
            client.bind_correlation_id("session_other")
    assert result == {"value": 1}
    assert str(requests[0].url) == "https://api.openai.com/v1/responses"
    assert requests[0].headers["Authorization"] == "Bearer test-secret"
    assert json.loads(requests[0].content)["store"] is False
    record = client.call_records[0]
    assert record.request_id == "req_observed"
    assert record.response_id == "resp_observed"
    assert record.correlation_id == "session_123"
    assert record.reasoning_mode == "pro"
    assert record.reasoning_tokens == 200
    assert record.input_tokens == 125
    raw = journal.read_text()
    assert "test-secret" not in raw
    assert "private clinical source text" not in raw
    assert json.loads(raw)["call_id"] == record.call_id


@pytest.mark.parametrize(
    "base_url",
    [
        "http://api.openai.com/v1",
        "http://localhost:8000/v1",
        "https://api.openai.com.attacker.invalid/v1",
        "https://user@api.openai.com/v1",
        "https://api.openai.com/v1?key=x",
        "https://api.openai.com:8443/v1",
        "https://api.openai.com/v1/../other",
    ],
)
def test_only_official_openai_endpoint_is_accepted(base_url):
    with pytest.raises(ValueError):
        validate_openai_base_url(base_url)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "code", "expected"),
    [
        (401, "invalid_api_key", ModelAuthenticationError),
        (403, "permission_denied", ModelAuthenticationError),
        (429, "insufficient_quota", ModelQuotaError),
    ],
)
async def test_auth_and_quota_failures_never_retry_or_return_error_body(
    status, code, expected
):
    attempts = []

    def handle(request):
        attempts.append(request)
        return httpx.Response(
            status,
            json={
                "error": {
                    "code": code,
                    "message": "private prompt and secret must not be returned",
                }
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        client = OpenAIClient("test-key", http_client=http, retry_base_seconds=0)
        with pytest.raises(expected) as raised:
            await client.response({"model": "gpt-6-astra", "input": "x"})
    assert len(attempts) == 1
    assert "private prompt" not in str(raised.value)
    assert client.call_records[0].status == "error"


@pytest.mark.asyncio
async def test_transient_retry_has_distinct_attempt_records_and_one_operation():
    attempts = []

    def handle(request):
        attempts.append(request)
        if len(attempts) < 3:
            return httpx.Response(503, json={"error": {"code": "server_error"}})
        return httpx.Response(200, json=_completed())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        client = OpenAIClient("test-key", http_client=http, retry_base_seconds=0)
        await client.response({"model": "gpt-6-astra", "input": "x"})
    assert len(attempts) == 3
    assert [item.attempt for item in client.call_records] == [1, 2, 3]
    assert len({item.operation_id for item in client.call_records}) == 1
    assert len({item.call_id for item in client.call_records}) == 3
    assert [item.status for item in client.call_records] == [
        "error",
        "error",
        "completed",
    ]


@pytest.mark.asyncio
async def test_read_timeout_is_not_repeated_after_uncertain_remote_generation():
    attempts = []

    def handle(request):
        attempts.append(request)
        raise httpx.ReadTimeout("sensitive transport detail", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        client = OpenAIClient("test-key", http_client=http)
        with pytest.raises(ModelTimeoutError) as raised:
            await client.response({"model": "gpt-6-astra", "input": "x"})
    assert len(attempts) == 1
    assert "sensitive" not in str(raised.value)
    assert client.call_records[0].error_code == "ReadTimeout"


@pytest.mark.parametrize(
    ("payload", "error_type"),
    [
        (
            {
                **_completed(),
                "status": "incomplete",
                "incomplete_details": {"reason": "max_output_tokens"},
            },
            ModelOutputTruncatedError,
        ),
        (
            {
                **_completed(),
                "status": "incomplete",
                "incomplete_details": {"reason": "content_filter"},
            },
            ModelIncompleteError,
        ),
        (
            {
                **_completed(),
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {"type": "refusal", "refusal": "private refusal text"}
                        ],
                    }
                ],
            },
            ModelRefusalError,
        ),
        (
            {**_completed(), "status": "failed", "error": {"code": "server_error"}},
            ModelResponseError,
        ),
    ],
)
def test_sync_transport_distinguishes_refusal_truncation_and_failure(
    payload, error_type
):
    with httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    ) as http:
        client = OpenAISyncClient("test-key", http_client=http)
        with pytest.raises(error_type) as raised:
            client.structured_completion(
                {"model": "gpt-6-astra", "input": "x", "max_output_tokens": 100}
            )
    assert "private refusal" not in str(raised.value)
    assert len(client.call_records) == 1
    assert client.call_records[0].response_status == payload["status"]


def test_count_payload_keeps_schema_tools_reasoning_and_does_not_mutate():
    payload = {
        "model": "gpt-6-astra",
        "input": "x",
        "instructions": "y",
        "text": {"format": {"type": "json_schema", "schema": {"type": "object"}}},
        "reasoning": {"mode": "pro", "effort": "xhigh"},
        "tools": [{"type": "web_search"}],
        "store": False,
        "max_output_tokens": 4000,
    }
    counted = normalize_count_request(payload)
    assert "store" not in counted and "max_output_tokens" not in counted
    assert counted["tools"] == payload["tools"]
    counted["text"]["format"]["type"] = "text"
    assert payload["text"]["format"]["type"] == "json_schema"


@pytest.mark.asyncio
async def test_stage_cancellation_preserves_an_uncertain_attempt_in_the_journal(
    tmp_path,
):
    started = asyncio.Event()
    pending = asyncio.Event()

    async def handle(request):
        started.set()
        await pending.wait()
        return httpx.Response(200, json=_completed())

    journal = tmp_path / "calls.jsonl"
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        client = OpenAIClient("test-key", http_client=http, audit_path=journal)
        task = asyncio.create_task(
            client.response({"model": "gpt-6-astra", "input": "x"})
        )
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    record = json.loads(journal.read_text())
    assert record["error_code"] == "client_cancelled"
    assert record["response_id"] is None
    assert record["input_tokens"] is None
