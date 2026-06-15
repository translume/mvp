from __future__ import annotations

from typing import Protocol


class ModelProvider(Protocol):
    async def structured_completion(
        self,
        *,
        model_name: str,
        system_prompt: str,
        user_prompt: str,
        schema_name: str,
        json_schema: dict[str, object],
    ) -> dict[str, object]:
        """Return schema-constrained JSON from a model provider."""
