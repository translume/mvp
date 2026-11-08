"""OpenAI Responses implementation of the clinical model-provider port."""

from __future__ import annotations

import hashlib
import json
from contextlib import AbstractContextManager

from translume_adapters.model_providers.openai_schema import bounded_generation_schema
from translume_clients.openai_client import (
    OpenAICallCapture,
    OpenAIClient,
    normalize_count_request,
)
from translume_ports.model_provider import (
    ModelInputBudgetError,
    ModelOutputTruncatedError,
)
from translume_schemas.model_calls import ModelCallRecord


class OpenAIModelProvider:
    """Generate strict clinical objects with actual-request token preflights.

    Acceptance criteria:
        1. Every request uses the configured OpenAI reasoning mode and effort.
        2. Strict schemas and repaired prompts are counted before generation.
        3. Context space reserves output/reasoning tokens and a safety margin.
        4. Only explicit output-limit truncation receives a larger output retry.
        5. API errors/refusals propagate without a clinical repair request.
    """

    def __init__(
        self,
        client: OpenAIClient,
        *,
        reasoning_mode: str = "pro",
        reasoning_effort: str = "xhigh",
        structured_output_max_tokens: int = 32768,
        structured_output_retry_max_tokens: int = 65536,
        report_extraction_max_tokens: int = 16384,
        tumor_behavior_max_tokens: int = 65536,
        context_window_tokens: int = 200000,
        input_token_budget: int = 100000,
        safety_margin_tokens: int = 2048,
    ) -> None:
        if reasoning_mode != "pro":
            raise ValueError("This deployment requires OPENAI_REASONING_MODE=pro")
        if reasoning_effort not in {"low", "medium", "high", "xhigh", "max"}:
            raise ValueError("Unsupported OpenAI reasoning effort")
        limits = {
            "structured_output_max_tokens": structured_output_max_tokens,
            "structured_output_retry_max_tokens": structured_output_retry_max_tokens,
            "report_extraction_max_tokens": report_extraction_max_tokens,
            "tumor_behavior_max_tokens": tumor_behavior_max_tokens,
            "context_window_tokens": context_window_tokens,
            "input_token_budget": input_token_budget,
            "safety_margin_tokens": safety_margin_tokens,
        }
        for name, value in limits.items():
            if type(value) is not int or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        if structured_output_retry_max_tokens <= structured_output_max_tokens:
            raise ValueError(
                "structured_output_retry_max_tokens must exceed the initial limit"
            )
        if (
            max(
                structured_output_retry_max_tokens,
                tumor_behavior_max_tokens,
                report_extraction_max_tokens,
            )
            + safety_margin_tokens
            >= context_window_tokens
        ):
            raise ValueError(
                "Output/reasoning reservation must fit the configured context window"
            )
        self._client = client
        self._reasoning_mode = reasoning_mode
        self._reasoning_effort = reasoning_effort
        self._structured_output_max_tokens = structured_output_max_tokens
        self._structured_output_retry_max_tokens = structured_output_retry_max_tokens
        self._report_extraction_max_tokens = report_extraction_max_tokens
        self._tumor_behavior_max_tokens = tumor_behavior_max_tokens
        self._context_window_tokens = context_window_tokens
        self._input_token_budget = input_token_budget
        self._safety_margin_tokens = safety_margin_tokens
        # Counts are cached only within this workflow's provider instance.
        self._token_counts: dict[str, int] = {}

    @property
    def call_records(self) -> tuple[ModelCallRecord, ...]:
        return self._client.call_records

    def bind_correlation_id(self, correlation_id: str) -> None:
        self._client.bind_correlation_id(correlation_id)

    def capture_calls(self) -> AbstractContextManager[OpenAICallCapture]:
        """Return a task-local trace for one clinical artifact generation."""
        return self._client.capture_calls()

    def wire_schema(
        self, json_schema: dict[str, object], *, schema_name: str
    ) -> dict[str, object]:
        return bounded_generation_schema(json_schema, schema_name=schema_name)

    def build_request(
        self,
        *,
        model_name: str,
        system_prompt: str,
        user_prompt: str,
        schema_name: str,
        json_schema: dict[str, object],
        max_tokens: int | None = None,
    ) -> dict[str, object]:
        """Build exactly the request that is counted and sent to Responses."""
        output_limit = (
            max_tokens
            if max_tokens is not None
            else self._max_tokens_for_schema(schema_name)
        )
        if type(output_limit) is not int or output_limit <= 0:
            raise ValueError("max_tokens must be a positive integer")
        if not model_name.strip():
            raise ValueError("An OpenAI model name is required")
        return {
            "model": model_name,
            "instructions": system_prompt,
            "input": user_prompt,
            "reasoning": {
                "mode": self._reasoning_mode,
                "effort": self._reasoning_effort,
            },
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": schema_name,
                    "schema": self.wire_schema(json_schema, schema_name=schema_name),
                    "strict": True,
                }
            },
            "max_output_tokens": output_limit,
            "store": False,
        }

    async def count_structured_request(self, **kwargs: object) -> int:
        return await self._count_request(self.build_request(**kwargs))

    async def count_tokens(self, *, model_name: str, text: str) -> int:
        return await self._count_request({"model": model_name, "input": text})

    async def _count_request(self, request: dict[str, object]) -> int:
        count_request = normalize_count_request(request)
        key = hashlib.sha256(
            json.dumps(count_request, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        if key not in self._token_counts:
            count = await self._client.count_tokens(count_request)
            if len(self._token_counts) >= 512:
                self._token_counts.clear()
            self._token_counts[key] = count
        return self._token_counts[key]

    async def _require_budget(
        self,
        request: dict[str, object],
        *,
        schema_name: str,
        input_token_budget: int | None,
    ) -> None:
        configured_limit = (
            self._input_token_budget
            if input_token_budget is None
            else min(self._input_token_budget, input_token_budget)
        )
        if type(configured_limit) is not int or configured_limit <= 0:
            raise ValueError("input_token_budget must be positive")
        context_allowance = (
            self._context_window_tokens
            - int(request["max_output_tokens"])
            - self._safety_margin_tokens
        )
        effective_limit = min(configured_limit, context_allowance)
        count = await self._count_request(request)
        if count > effective_limit:
            raise ModelInputBudgetError(
                schema_name=schema_name,
                input_tokens=count,
                input_token_budget=effective_limit,
            )

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
        request = self.build_request(
            model_name=model_name,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            schema_name=schema_name,
            json_schema=json_schema,
            max_tokens=max_tokens,
        )
        await self._require_budget(
            request, schema_name=schema_name, input_token_budget=input_token_budget
        )
        try:
            return await self._client.structured_completion(request)
        except ModelOutputTruncatedError as error:
            if max_tokens is not None:
                raise
            retry_limit = (
                self._tumor_behavior_max_tokens
                if schema_name == "TumorBehaviorModelOutput"
                else self._structured_output_retry_max_tokens
            )
            retry_request = {**request, "max_output_tokens": retry_limit}
            await self._require_budget(
                retry_request,
                schema_name=schema_name,
                input_token_budget=input_token_budget,
            )
            try:
                return await self._client.structured_completion(retry_request)
            except ModelOutputTruncatedError as retry_error:
                raise ModelOutputTruncatedError(
                    finish_reason=retry_error.finish_reason,
                    content_chars=retry_error.content_chars,
                    schema_name=schema_name,
                    max_tokens=retry_limit,
                    attempts=2,
                ) from error

    def _max_tokens_for_schema(self, schema_name: str) -> int:
        if schema_name in {"ReportExtractionOutput", "_BoundedReportExtractionOutput"}:
            return self._report_extraction_max_tokens
        return self._structured_output_max_tokens
