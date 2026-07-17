from __future__ import annotations

from datetime import datetime, timezone

import pytest

from translume_core.compiler.structured_model_artifacts import (
    _BoundedConfirmatoryTestingOutput,
    _canonicalize_provenance_schema,
    _require_prompt_within_token_budget,
    StructuredArtifactGenerationError,
)
from translume_core.provenance.hashing import stable_json_hash
from translume_schemas.confirmatory import ConfirmatoryTestingOutput
from translume_schemas.provenance import ArtifactProvenance


class _CountingProvider:
    """Return a configured token count without model generation."""

    def __init__(self, count: int) -> None:
        self.count = count

    async def count_tokens(self, *, model_name: str, text: str) -> int:
        del model_name, text
        return self.count


@pytest.mark.asyncio
async def test_confirmatory_prompt_preflight_rejects_oversized_input() -> None:
    """Reject a request before vLLM when measured input exceeds its budget."""
    with pytest.raises(
        StructuredArtifactGenerationError,
        match="exceeds input token budget: 4001 > 4000",
    ):
        await _require_prompt_within_token_budget(
            model_provider=_CountingProvider(4001),
            model_name="local-model",
            system_prompt="system",
            user_prompt="user",
            input_token_budget=4000,
            schema_name="ConfirmatoryTestingOutput",
        )


def test_confirmatory_leaf_schema_bounds_output_cardinality() -> None:
    """Prevent unbounded test rows and strings during structured decoding."""
    schema = _BoundedConfirmatoryTestingOutput.model_json_schema()

    assert schema["properties"]["tests"]["maxItems"] == 12
    assert schema["properties"]["must_not_assume"]["maxItems"] == 12


def test_confirmatory_provenance_uses_public_schema() -> None:
    """Internal generation constraints must not leak into provenance."""
    provenance = ArtifactProvenance(
        artifact_id="artifact_confirmatory",
        artifact_type="_BoundedConfirmatoryTestingOutput",
        schema_name="_BoundedConfirmatoryTestingOutput",
        model_name="local-model",
        prompt_hash="prompt-hash",
        schema_hash="bounded-schema-hash",
        source_artifact_ids=["artifact_report"],
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    canonical = _canonicalize_provenance_schema(
        provenance,
        ConfirmatoryTestingOutput,
    )

    assert canonical.artifact_type == "ConfirmatoryTestingOutput"
    assert canonical.schema_name == "ConfirmatoryTestingOutput"
    assert canonical.schema_hash == stable_json_hash(
        ConfirmatoryTestingOutput.model_json_schema()
    )
    assert canonical.prompt_hash == "prompt-hash"
    assert provenance.schema_name == "_BoundedConfirmatoryTestingOutput"
