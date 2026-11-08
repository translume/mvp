from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Protocol

from translume_schemas.model_calls import (
    ModelCallRecord,
    ModelInputBudgetError,
    ModelOutputTruncatedError,
    ModelProviderError,
)

__all__ = [
    "ModelCallCapture",
    "ModelInputBudgetError",
    "ModelOutputTruncatedError",
    "ModelProvider",
    "ModelProviderError",
]


class ModelCallCapture(Protocol):
    @property
    def records(self) -> tuple[ModelCallRecord, ...]:
        """Return only attempts belonging to the captured clinical operation."""


class ModelProvider(Protocol):
    def capture_calls(self) -> AbstractContextManager[ModelCallCapture]:
        """Capture task-local attempts without mixing concurrent artifacts."""

    async def structured_completion(
        self,
        *,
        model_name: str,
        system_prompt: str,
        user_prompt: str,
        schema_name: str,
        json_schema: dict[str, object],
        max_tokens: int | None = None,
        input_token_budget: int | None = None,
    ) -> dict[str, object]:
        """Return schema-constrained JSON from a model provider."""

    async def count_tokens(self, *, model_name: str, text: str) -> int:
        """Return the provider's input-token count for a text request."""

    async def count_structured_request(
        self,
        *,
        model_name: str,
        system_prompt: str,
        user_prompt: str,
        schema_name: str,
        json_schema: dict[str, object],
        max_tokens: int | None = None,
    ) -> int:
        """Count the actual wire request, including schema and reasoning."""

    @property
    def call_records(self) -> tuple[ModelCallRecord, ...]:
        """Return immutable metadata for attempts in this request scope."""
