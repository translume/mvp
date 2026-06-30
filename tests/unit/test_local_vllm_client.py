from __future__ import annotations

import httpx
import pytest

from translume_clients.local_vllm import LocalVLLMClient, LocalVLLMClientError


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
