from __future__ import annotations

from translume_clients.local_vllm import (
    LocalVLLMClient,
    LocalVLLMTruncationError,
)
from translume_ports.model_provider import ModelOutputTruncatedError


_TIGHT_OUTPUT_SCHEMAS = {
    "ActionableBiologyOutput",
    "BiomarkerWatchListOutput",
    "ClaimEvidenceListOutput",
    "ConfirmatoryTestingOutput",
    "_BoundedConfirmatoryTestingOutput",
    "NextTestRecommendationsOutput",
    "RankedTreatmentOptionsOutput",
    "ResistanceForecastOutput",
    "RetestingTriggersOutput",
    "TranslationalAssessmentOutput",
    "TreatmentPressureMapOutput",
}


class LocalVLLMProvider:
    """Route bounded structured outputs to local vLLM.

    Acceptance criteria:
        1. Every structured request includes a positive output-token bound.
        2. Report extraction uses its dedicated positive output-token bound.
        3. Request construction does not mutate caller-owned values.
    """

    def __init__(
        self,
        client: LocalVLLMClient,
        *,
        structured_output_max_tokens: int = 3000,
        structured_output_retry_max_tokens: int = 6000,
        report_extraction_max_tokens: int = 2500,
        tumor_behavior_max_tokens: int = 6000,
    ) -> None:
        if structured_output_max_tokens <= 0:
            raise ValueError("structured_output_max_tokens must be positive")
        if report_extraction_max_tokens <= 0:
            raise ValueError("report_extraction_max_tokens must be positive")
        if structured_output_retry_max_tokens <= structured_output_max_tokens:
            raise ValueError(
                "structured_output_retry_max_tokens must exceed "
                "structured_output_max_tokens"
            )
        if tumor_behavior_max_tokens <= structured_output_max_tokens:
            raise ValueError(
                "tumor_behavior_max_tokens must exceed "
                "structured_output_max_tokens"
            )
        self._client = client
        self._structured_output_max_tokens = structured_output_max_tokens
        self._structured_output_retry_max_tokens = (
            structured_output_retry_max_tokens
        )
        self._report_extraction_max_tokens = report_extraction_max_tokens
        self._tumor_behavior_max_tokens = tumor_behavior_max_tokens

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
        request = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0,
            "max_tokens": (
                self._max_tokens_for_schema(schema_name)
                if max_tokens is None
                else max_tokens
            ),
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "schema": _bounded_generation_schema(
                        json_schema,
                        schema_name=schema_name,
                    ),
                    "strict": True,
                },
            },
        }
        try:
            return await self._client.structured_completion(request)
        except LocalVLLMTruncationError as error:
            if max_tokens is not None:
                raise ModelOutputTruncatedError(
                    finish_reason=error.finish_reason,
                    content_chars=error.content_chars,
                    schema_name=schema_name,
                    max_tokens=max_tokens,
                ) from error
            retry_max_tokens = (
                self._tumor_behavior_max_tokens
                if schema_name == "TumorBehaviorModelOutput"
                else self._structured_output_retry_max_tokens
            )
            retry_request = {
                **request,
                "max_tokens": retry_max_tokens,
            }
            try:
                return await self._client.structured_completion(retry_request)
            except LocalVLLMTruncationError as retry_error:
                raise ModelOutputTruncatedError(
                    finish_reason=retry_error.finish_reason,
                    content_chars=retry_error.content_chars,
                    schema_name=schema_name,
                    max_tokens=retry_max_tokens,
                    attempts=2,
                ) from retry_error

    async def count_tokens(self, *, model_name: str, text: str) -> int:
        """Count text with the tokenizer hosted by the configured vLLM model."""
        return await self._client.count_tokens(
            {"model": model_name, "prompt": text}
        )

    def _max_tokens_for_schema(self, schema_name: str) -> int:
        if schema_name == "ReportExtractionOutput":
            return self._report_extraction_max_tokens
        return self._structured_output_max_tokens


def _bounded_generation_schema(
    json_schema: dict[str, object],
    *,
    schema_name: str,
) -> dict[str, object]:
    """Return generation-only string and array bounds for structured decoding.

    Acceptance criteria:
        1. The caller-owned schema is never mutated.
        2. Existing stricter bounds remain unchanged.
        3. Narrative Markdown retains a larger bounded text allowance.
        4. List-heavy clinical stages receive tighter default constraints.
    """
    max_items = 12 if schema_name in _TIGHT_OUTPUT_SCHEMAS else 20
    max_string_chars = 700 if schema_name in _TIGHT_OUTPUT_SCHEMAS else 1200
    return _bound_schema_node(
        json_schema,
        max_items=max_items,
        max_string_chars=max_string_chars,
        property_name=None,
    )


def _bound_schema_node(
    value: object,
    *,
    max_items: int,
    max_string_chars: int,
    property_name: str | None,
) -> object:
    if isinstance(value, list):
        return [
            _bound_schema_node(
                item,
                max_items=max_items,
                max_string_chars=max_string_chars,
                property_name=property_name,
            )
            for item in value
        ]
    if not isinstance(value, dict):
        return value
    bounded = {
        key: _bound_schema_node(
            item,
            max_items=max_items,
            max_string_chars=max_string_chars,
            property_name=key if key not in {"properties", "$defs"} else property_name,
        )
        for key, item in value.items()
    }
    node_type = bounded.get("type")
    if node_type == "array":
        existing = bounded.get("maxItems")
        bounded["maxItems"] = (
            min(existing, max_items) if isinstance(existing, int) else max_items
        )
    if node_type == "string":
        field_limit = 12000 if property_name == "markdown" else max_string_chars
        existing = bounded.get("maxLength")
        bounded["maxLength"] = (
            min(existing, field_limit)
            if isinstance(existing, int)
            else field_limit
        )
    return bounded
