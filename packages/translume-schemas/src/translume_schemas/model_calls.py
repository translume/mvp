"""Shared, content-free records and errors for remote model boundaries."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from translume_schemas.base import TranslumeBaseModel


class ModelCallRecord(TranslumeBaseModel):
    """Describe one actual HTTP attempt without prompts or credentials.

    Acceptance criteria:
        1. One unique call ID identifies one attempt, including failed attempts.
        2. Request and response IDs are copied only from the provider.
        3. Token counts are provider-reported, never estimated usage.
        4. No generated content, source text, or credential is retained here.
    """

    call_id: str
    operation_id: str
    correlation_id: str | None = None
    trace_ids: tuple[str, ...] = ()
    provider: Literal["openai"] = "openai"
    endpoint: str
    requested_model: str
    actual_model: str | None = None
    reasoning_mode: str | None = None
    reasoning_effort: str | None = None
    request_id: str | None = None
    response_id: str | None = None
    request_hash: str
    wire_schema_hash: str | None = None
    status: str
    response_status: str | None = None
    http_status: int | None = None
    error_code: str | None = None
    attempt: int = Field(ge=1)
    created_at: datetime
    elapsed_ms: int = Field(ge=0)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    cached_input_tokens: int | None = Field(default=None, ge=0)
    reasoning_tokens: int | None = Field(default=None, ge=0)


class ModelProviderError(RuntimeError):
    """A provider failure that must not become a clinical repair prompt."""

    def __init__(
        self,
        message: str,
        *,
        error_code: str | None = None,
        request_id: str | None = None,
        http_status: int | None = None,
    ) -> None:
        self.error_code = error_code
        self.request_id = request_id
        self.http_status = http_status
        details = []
        if http_status is not None:
            details.append(f"HTTP {http_status}")
        if error_code:
            details.append(f"code={error_code}")
        if request_id:
            details.append(f"request_id={request_id}")
        suffix = f" ({', '.join(details)})" if details else ""
        super().__init__(message + suffix)


class ModelAuthenticationError(ModelProviderError):
    """The API key, project permissions, or model access was rejected."""


class ModelQuotaError(ModelProviderError):
    """The provider reports exhausted credits or quota; retries cannot fix it."""


class ModelRateLimitError(ModelProviderError):
    """The provider's rate limit persisted through the bounded retry policy."""


class ModelTimeoutError(ModelProviderError):
    """The remote request exceeded its configured network timeout."""


class ModelConnectionError(ModelProviderError):
    """The remote connection could not be completed."""


class ModelInvalidRequestError(ModelProviderError):
    """The model or request configuration was rejected by the API."""


class ModelResponseError(ModelProviderError):
    """The provider returned an invalid or failed response envelope."""


class ModelRefusalError(ModelProviderError):
    """The model refused the request; refusal text is not clinical evidence."""


class ModelIncompleteError(ModelProviderError):
    """The response is incomplete for a reason other than its output limit."""


class ModelAuditError(ModelProviderError):
    """An actual model attempt could not be durably recorded."""


class ModelInputBudgetError(ModelProviderError):
    """The final request cannot fit the configured input/context allowance."""

    def __init__(
        self,
        *,
        schema_name: str,
        input_tokens: int,
        input_token_budget: int,
    ) -> None:
        self.schema_name = schema_name
        self.input_tokens = input_tokens
        self.input_token_budget = input_token_budget
        super().__init__(
            f"{schema_name} final request exceeds input token budget: "
            f"{input_tokens} > {input_token_budget}",
            error_code="input_token_budget_exceeded",
        )


class ModelOutputTruncatedError(ModelProviderError):
    """The API explicitly stopped at the configured output-token limit."""

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
            f"max_tokens={max_tokens}, attempts={attempts}",
            error_code="max_output_tokens",
        )
