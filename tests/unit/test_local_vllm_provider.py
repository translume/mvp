from __future__ import annotations

import asyncio

import pytest

from translume_adapters.model_providers.local_vllm_provider import (
    LocalVLLMProvider,
)
from translume_clients.local_vllm import LocalVLLMTruncationError
from translume_ports.model_provider import ModelOutputTruncatedError


class RecordingClient:
    """Test boundary that records the structured vLLM request."""

    def __init__(self) -> None:
        self.request: dict[str, object] | None = None

    async def structured_completion(
        self,
        request: dict[str, object],
    ) -> dict[str, object]:
        self.request = request
        return {"artifact_id": "artifact_test"}


class TruncatingClient:
    """Return configured responses while recording immutable requests."""

    def __init__(self, *, truncate_attempts: int) -> None:
        self.truncate_attempts = truncate_attempts
        self.requests: list[dict[str, object]] = []

    async def structured_completion(
        self,
        request: dict[str, object],
    ) -> dict[str, object]:
        self.requests.append(dict(request))
        if len(self.requests) <= self.truncate_attempts:
            raise LocalVLLMTruncationError(
                finish_reason="length",
                content_chars=12000,
            )
        return {"artifact_id": "artifact_test"}


def test_provider_uses_dedicated_report_extraction_token_cap() -> None:
    """Report extraction should use its configured bounded output budget.

    Acceptance criteria:
        1. The request contains a positive max_tokens value.
        2. Report extraction uses the dedicated cap.
        3. The provider preserves the schema-constrained request contract.
    """
    client = RecordingClient()
    provider = LocalVLLMProvider(
        client,
        structured_output_max_tokens=3000,
        report_extraction_max_tokens=2500,
    )

    asyncio.run(
        provider.structured_completion(
            model_name="local-model",
            system_prompt="system",
            user_prompt="user",
            schema_name="ReportExtractionOutput",
            json_schema={"type": "object"},
        )
    )

    assert client.request is not None
    assert client.request["max_tokens"] == 2500


def test_provider_uses_default_token_cap_for_other_schemas() -> None:
    """Non-extraction structured outputs should remain output bounded.

    Acceptance criteria:
        1. The request contains a positive max_tokens value.
        2. Other schemas use the general cap.
        3. Request construction is deterministic.
    """
    client = RecordingClient()
    provider = LocalVLLMProvider(client, structured_output_max_tokens=3000)

    asyncio.run(
        provider.structured_completion(
            model_name="local-model",
            system_prompt="system",
            user_prompt="user",
            schema_name="MolecularPhenotypeOutput",
            json_schema={"type": "object"},
        )
    )

    assert client.request is not None
    assert client.request["max_tokens"] == 3000


def test_provider_retries_truncated_tumor_behavior_with_larger_cap() -> None:
    """Retry tumor behavior once using its dedicated bounded budget."""
    client = TruncatingClient(truncate_attempts=1)
    provider = LocalVLLMProvider(
        client,
        structured_output_max_tokens=3000,
        tumor_behavior_max_tokens=6000,
    )

    result = asyncio.run(
        provider.structured_completion(
            model_name="local-model",
            system_prompt="system",
            user_prompt="user",
            schema_name="TumorBehaviorModelOutput",
            json_schema={"type": "object"},
        )
    )

    assert result == {"artifact_id": "artifact_test"}
    assert [request["max_tokens"] for request in client.requests] == [3000, 6000]


def test_provider_retries_other_truncated_schemas_once() -> None:
    """Apply the shared larger retry to every non-report structured stage."""
    client = TruncatingClient(truncate_attempts=1)
    provider = LocalVLLMProvider(
        client,
        structured_output_max_tokens=3000,
        structured_output_retry_max_tokens=6000,
    )

    result = asyncio.run(
        provider.structured_completion(
            model_name="local-model",
            system_prompt="system",
            user_prompt="user",
            schema_name="ResistanceForecastOutput",
            json_schema={"type": "object"},
        )
    )

    assert result == {"artifact_id": "artifact_test"}
    assert [request["max_tokens"] for request in client.requests] == [3000, 6000]


def test_provider_stops_after_second_tumor_behavior_truncation() -> None:
    """Keep truncation recovery bounded to one additional request."""
    client = TruncatingClient(truncate_attempts=2)
    provider = LocalVLLMProvider(client, tumor_behavior_max_tokens=6000)

    with pytest.raises(
        ModelOutputTruncatedError,
        match="TumorBehaviorModelOutput",
    ):
        asyncio.run(
            provider.structured_completion(
                model_name="local-model",
                system_prompt="system",
                user_prompt="user",
                schema_name="TumorBehaviorModelOutput",
                json_schema={"type": "object"},
            )
        )

    assert len(client.requests) == 2


def test_provider_bounds_generation_schema_without_mutating_input() -> None:
    """Apply bounded decoding while preserving the public schema mapping."""
    client = RecordingClient()
    provider = LocalVLLMProvider(client)
    schema = {
        "type": "object",
        "properties": {
            "rows": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"description": {"type": "string"}},
                },
            }
        },
    }

    asyncio.run(
        provider.structured_completion(
            model_name="local-model",
            system_prompt="system",
            user_prompt="user",
            schema_name="ResistanceForecastOutput",
            json_schema=schema,
        )
    )

    assert client.request is not None
    bounded = client.request["response_format"]["json_schema"]["schema"]
    assert bounded["properties"]["rows"]["maxItems"] == 12
    description = bounded["properties"]["rows"]["items"]["properties"][
        "description"
    ]
    assert description["maxLength"] == 700
    assert "maxItems" not in schema["properties"]["rows"]
