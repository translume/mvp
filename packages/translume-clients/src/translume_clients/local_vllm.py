from __future__ import annotations

import httpx


class LocalVLLMClientError(RuntimeError):
    """Raised when local vLLM cannot produce usable structured output."""


class LocalVLLMTruncationError(LocalVLLMClientError):
    """Raised when vLLM stops structured generation at its token limit.

    Acceptance criteria:
        1. Carries the server-provided finish reason.
        2. Reports only content length, never generated clinical content.
        3. Remains catchable as `LocalVLLMClientError`.
    """

    def __init__(self, *, finish_reason: str, content_chars: int) -> None:
        self.finish_reason = finish_reason
        self.content_chars = content_chars
        super().__init__(
            "vLLM structured output was truncated: "
            f"finish_reason={finish_reason!r}, content_chars={content_chars}"
        )


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
            4. Timeout failures include type, URL, and configured timeout.
            5. Network I/O is isolated here.
        """
        url = f"{self._base_url}/chat/completions"
        try:
            async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                response = await client.post(url, json=request)
        except httpx.TimeoutException as error:
            raise LocalVLLMClientError(
                "Local vLLM request timed out: "
                f"{url}: {type(error).__name__} after "
                f"{self._timeout_seconds:g} seconds"
            ) from error
        if response.status_code >= 400:
            raise LocalVLLMClientError(f"vLLM error {response.status_code}: {response.text}")
        data = response.json()
        try:
            choice = data["choices"][0]
            content = choice["message"]["content"]
            finish_reason = choice.get("finish_reason")
        except (AttributeError, KeyError, IndexError, TypeError) as error:
            raise LocalVLLMClientError("invalid vLLM response shape") from error
        if finish_reason == "length":
            content_chars = len(content) if isinstance(content, str) else 0
            raise LocalVLLMTruncationError(
                finish_reason=finish_reason,
                content_chars=content_chars,
            )
        if isinstance(content, dict):
            return content
        if not isinstance(content, str):
            raise LocalVLLMClientError("invalid vLLM response shape")
        import json
        try:
            parsed = json.loads(_strip_json_fence(content))
        except json.JSONDecodeError as error:
            raise LocalVLLMClientError("vLLM content is not JSON") from error
        if not isinstance(parsed, dict):
            raise LocalVLLMClientError("vLLM structured output is not a JSON object")
        return parsed

    async def count_tokens(self, request: dict[str, object]) -> int:
        """Return a token count from vLLM's model-native tokenizer endpoint."""
        base_root = self._base_url.removesuffix("/v1")
        url = f"{base_root}/tokenize"
        try:
            async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                response = await client.post(url, json=request)
        except httpx.TimeoutException as error:
            raise LocalVLLMClientError(
                f"Local vLLM tokenization timed out: {url}"
            ) from error
        if response.status_code >= 400:
            raise LocalVLLMClientError(
                f"vLLM tokenize error {response.status_code}: {response.text}"
            )
        data = response.json()
        count = data.get("count") if isinstance(data, dict) else None
        if not isinstance(count, int) or count < 0:
            raise LocalVLLMClientError("invalid vLLM tokenize response shape")
        return count


def _strip_json_fence(content: str) -> str:
    stripped = content.strip()
    if stripped.startswith("```json"):
        return stripped.removeprefix("```json").removesuffix("```").strip()
    if stripped.startswith("```"):
        return stripped.removeprefix("```").removesuffix("```").strip()
    return stripped
