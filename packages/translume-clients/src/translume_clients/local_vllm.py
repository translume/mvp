from __future__ import annotations

import httpx


class LocalVLLMClientError(RuntimeError):
    """Raised when local vLLM cannot produce usable structured output."""


class LocalVLLMClient:
    def __init__(self, base_url: str, timeout_seconds: float = 120.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds

    async def structured_completion(self, request: dict[str, object]) -> dict[str, object]:
        """Call local vLLM OpenAI-compatible chat completion endpoint.

        Acceptance criteria:
            1. Sends requests only to configured base URL.
            2. Non-2xx responses raise LocalVLLMClientError.
            3. Invalid response shapes raise LocalVLLMClientError.
            4. Network I/O is isolated here.
        """
        url = f"{self._base_url}/chat/completions"
        async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
            response = await client.post(url, json=request)
        if response.status_code >= 400:
            raise LocalVLLMClientError(f"vLLM error {response.status_code}: {response.text}")
        data = response.json()
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as error:
            raise LocalVLLMClientError("invalid vLLM response shape") from error
        if isinstance(content, dict):
            return content
        import json
        try:
            return json.loads(content)
        except json.JSONDecodeError as error:
            raise LocalVLLMClientError("vLLM content is not JSON") from error
