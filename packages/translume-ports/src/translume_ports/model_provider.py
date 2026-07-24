from __future__ import annotations

from typing import Protocol


class ModelOutputTruncatedError(RuntimeError):
    """Report that a model stopped because its output-token limit was reached."""

    def __init__(
        self,
        *,
        finish_reason: str,
        content_chars: int,
        schema_name: str | None = None,
        max_tokens: int | None = None,
        attempts: int = 1,
    ) -> None:
        self.finish_reason = finish_reason
        self.content_chars = content_chars
        self.schema_name = schema_name
        self.max_tokens = max_tokens
        self.attempts = attempts
        schema_detail = (
            f" for schema {schema_name!r}" if schema_name is not None else ""
        )
        super().__init__(
            f"model structured output was truncated{schema_detail}: "
            f"finish_reason={finish_reason!r}, content_chars={content_chars}, "
            f"max_tokens={max_tokens}, attempts={attempts}"
        )


class ModelProvider(Protocol):
    async def structured_completion(
        self,
        *,
        model_name: str,
        system_prompt: str,
        user_prompt: str,
        schema_name: str,
        json_schema: dict[str, object],
        max_tokens: int | None = None,
    ) -> dict[str, object]:
        """Return schema-constrained JSON from a model provider."""

    async def count_tokens(self, *, model_name: str, text: str) -> int:
        """Return the served model tokenizer's token count for text."""
