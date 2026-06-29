from __future__ import annotations

import httpx
import pytest

from translume_clients.mims import (
    MimsServiceClientConfig,
    MimsServiceClientError,
    _post_json,
)


class _StatusClient:
    def __init__(self, *, timeout: float) -> None:
        self.timeout = timeout

    async def __aenter__(self) -> "_StatusClient":
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def post(self, url: str, json: dict[str, object]) -> httpx.Response:
        request = httpx.Request("POST", url)
        return httpx.Response(
            422,
            json={"detail": "missing first_disease"},
            request=request,
        )


@pytest.mark.asyncio
async def test_post_json_status_error_includes_response_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(httpx, "AsyncClient", _StatusClient)

    with pytest.raises(MimsServiceClientError) as error:
        await _post_json(
            MimsServiceClientConfig(base_url="http://tooluniverse-service:8092"),
            "/workflows",
            {"workflows": []},
        )

    message = str(error.value)
    assert "422" in message
    assert "missing first_disease" in message
