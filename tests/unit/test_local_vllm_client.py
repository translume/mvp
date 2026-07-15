from __future__ import annotations

import httpx
import pytest

from translume_clients.local_vllm import (
    LocalVLLMClient,
    LocalVLLMClientError,
    LocalVLLMTruncationError,
)


class _TimeoutClient:
    def __init__(self, *, timeout: float) -> None:
        self.timeout = timeout

    async def __aenter__(self) -> "_TimeoutClient":
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def post(self, url: str, json: dict[str, object]) -> httpx.Response:
        request = httpx.Request("POST", url)
        raise httpx.ReadTimeout("", request=request)


class _ResponseClient:
    response_payload: dict[str, object] = {}

    def __init__(self, *, timeout: float) -> None:
        self.timeout = timeout

    async def __aenter__(self) -> "_ResponseClient":
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def post(self, url: str, json: dict[str, object]) -> httpx.Response:
        request = httpx.Request("POST", url)
        return httpx.Response(200, request=request, json=self.response_payload)


@pytest.mark.asyncio
async def test_local_vllm_timeout_error_includes_type_url_and_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(httpx, "AsyncClient", _TimeoutClient)
    client = LocalVLLMClient(
        base_url="http://vllm-clinical:8000/v1",
        timeout_seconds=17,
    )

    with pytest.raises(LocalVLLMClientError) as error:
        await client.structured_completion({"messages": []})

    message = str(error.value)
    assert "Local vLLM request timed out" in message
    assert "http://vllm-clinical:8000/v1/chat/completions" in message
    assert "ReadTimeout" in message
    assert "17 seconds" in message


@pytest.mark.asyncio
async def test_local_vllm_reports_length_finish_as_truncation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Detect token exhaustion before attempting to decode partial JSON."""
    _ResponseClient.response_payload = {
        "choices": [
            {
                "finish_reason": "length",
                "message": {"content": '{"partial":'},
            }
        ]
    }
    monkeypatch.setattr(httpx, "AsyncClient", _ResponseClient)

    with pytest.raises(LocalVLLMTruncationError) as error:
        await LocalVLLMClient("http://vllm/v1").structured_completion({})

    assert error.value.finish_reason == "length"
    assert error.value.content_chars == 11
    assert "partial" not in str(error.value)


@pytest.mark.asyncio
async def test_local_vllm_keeps_non_truncated_invalid_json_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Do not misclassify malformed completed content as truncation."""
    _ResponseClient.response_payload = {
        "choices": [
            {
                "finish_reason": "stop",
                "message": {"content": "not-json"},
            }
        ]
    }
    monkeypatch.setattr(httpx, "AsyncClient", _ResponseClient)

    with pytest.raises(LocalVLLMClientError, match="content is not JSON"):
        await LocalVLLMClient("http://vllm/v1").structured_completion({})
