"""Authenticated OpenAI REST boundaries with bounded retries and audit records.

The asynchronous and synchronous clients share response validation and error
classification. They never fall back to another provider or a local model.
Create one client per report/service request and close it at that boundary.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import re
import threading
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Self
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
from translume_schemas.model_calls import (
    ModelAuditError,
    ModelAuthenticationError,
    ModelCallRecord,
    ModelConnectionError,
    ModelIncompleteError,
    ModelInvalidRequestError,
    ModelOutputTruncatedError,
    ModelProviderError,
    ModelQuotaError,
    ModelRateLimitError,
    ModelRefusalError,
    ModelResponseError,
    ModelTimeoutError,
)

OPENAI_BASE_URL = "https://api.openai.com/v1"
_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9_.:/-]{1,256}$")
_RETRYABLE_HTTP_STATUS = frozenset({408, 409, 429, 500, 502, 503, 504})
_QUOTA_CODES = frozenset(
    {"insufficient_quota", "billing_hard_limit_reached", "usage_limit_reached"}
)
_COUNT_REQUEST_FIELDS = frozenset(
    {
        "model",
        "instructions",
        "input",
        "text",
        "reasoning",
        "tools",
        "tool_choice",
        "previous_response_id",
        "conversation",
        "parallel_tool_calls",
        "truncation",
    }
)

# Retained as a convenient public catch point for service wrappers.
OpenAIClientError = ModelProviderError


def validate_openai_base_url(base_url: str) -> str:
    """Return the only allowed model-provider origin.

    Acceptance criteria:
        1. Only HTTPS api.openai.com/v1 is accepted.
        2. Credentials, query strings, fragments, and alternate ports fail.
        3. Normalization never changes the endpoint to a local fallback.
    """
    parsed = urlsplit(base_url.strip())
    try:
        port = parsed.port
    except ValueError as error:
        raise ValueError("OPENAI_BASE_URL has an invalid port") from error
    if (
        parsed.scheme != "https"
        or parsed.hostname != "api.openai.com"
        or port not in {None, 443}
        or parsed.path.rstrip("/") != "/v1"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(
            "OPENAI_BASE_URL must be https://api.openai.com/v1; "
            "local models and alternate providers are disabled"
        )
    return OPENAI_BASE_URL


def normalize_count_request(request: Mapping[str, object]) -> dict[str, object]:
    """Copy the generation fields supported by Responses input-token counting.

    Acceptance criteria:
        1. Includes the exact input, schema, instructions, tools, and reasoning.
        2. Excludes generation-only fields such as store/max_output_tokens.
        3. Never mutates or returns nested references into the caller's data.
    """
    return deepcopy(
        {key: value for key, value in request.items() if key in _COUNT_REQUEST_FIELDS}
    )


def response_text(response: Mapping[str, object]) -> str:
    """Read text only from typed Responses output messages.

    Acceptance criteria:
        1. Ignores reasoning/tool items and never treats them as final output.
        2. Joins output_text blocks in their original order.
        3. Rejects an absent or non-text final answer without inventing one.
    """
    texts = []
    output = response.get("output")
    if not isinstance(output, list):
        raise ModelResponseError("OpenAI response has no typed output list")
    for item in output:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "output_text" and isinstance(
                block.get("text"), str
            ):
                texts.append(block["text"])
    text = "".join(texts)
    if not text.strip():
        raise ModelResponseError("OpenAI completed response contains no answer text")
    return text


def _structured_object(response: Mapping[str, object]) -> dict[str, object]:
    try:
        result = json.loads(response_text(response))
    except json.JSONDecodeError as error:
        raise ModelResponseError(
            "OpenAI completed structured response is not valid JSON"
        ) from error
    if not isinstance(result, dict):
        raise ModelResponseError("OpenAI structured response is not a JSON object")
    return result


def _safe_identifier(value: object) -> str | None:
    if isinstance(value, str) and _SAFE_IDENTIFIER.fullmatch(value):
        return value
    return None


def _nonnegative_integer(value: object) -> int | None:
    return value if type(value) is int and value >= 0 else None


def _json_hash(value: object) -> str:
    serialized = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _wire_schema(request: Mapping[str, object]) -> object | None:
    text = request.get("text")
    if not isinstance(text, dict):
        return None
    text_format = text.get("format")
    if not isinstance(text_format, dict):
        return None
    return text_format.get("schema")


def _error_code(data: Mapping[str, object]) -> str | None:
    error = data.get("error")
    if not isinstance(error, dict):
        return None
    return _safe_identifier(error.get("code")) or _safe_identifier(error.get("type"))


def _response_error(
    data: Mapping[str, object], request: Mapping[str, object]
) -> ModelProviderError | None:
    output = data.get("output", [])
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content", [])
            if isinstance(content, list) and any(
                isinstance(block, dict) and block.get("type") == "refusal"
                for block in content
            ):
                return ModelRefusalError(
                    "OpenAI refused the request", error_code="model_refusal"
                )
    status = data.get("status")
    if status == "completed":
        return None
    if status == "incomplete":
        details = data.get("incomplete_details")
        reason = (
            _safe_identifier(details.get("reason"))
            if isinstance(details, dict)
            else None
        )
        if reason == "max_output_tokens":
            text = request.get("text", {})
            text_format = text.get("format", {}) if isinstance(text, dict) else {}
            name = text_format.get("name") if isinstance(text_format, dict) else None
            try:
                content_chars = len(response_text(data))
            except ModelResponseError:
                content_chars = 0
            return ModelOutputTruncatedError(
                finish_reason=reason,
                content_chars=content_chars,
                schema_name=name if isinstance(name, str) else None,
                max_tokens=_nonnegative_integer(request.get("max_output_tokens")),
            )
        return ModelIncompleteError(
            "OpenAI returned an incomplete response", error_code=reason
        )
    return ModelResponseError(
        "OpenAI did not complete the response",
        error_code=_error_code(data)
        or _safe_identifier(status)
        or "invalid_response_status",
    )


def _http_error(
    response: httpx.Response, data: Mapping[str, object]
) -> ModelProviderError:
    status = response.status_code
    code = _error_code(data)
    kwargs = {
        "error_code": code,
        "request_id": _safe_identifier(response.headers.get("x-request-id")),
        "http_status": status,
    }
    if status in {401, 403}:
        return ModelAuthenticationError(
            "OpenAI rejected the API key, project permissions, or model access",
            **kwargs,
        )
    if code in _QUOTA_CODES:
        return ModelQuotaError("OpenAI API credits or quota are exhausted", **kwargs)
    if status == 429:
        return ModelRateLimitError("OpenAI API rate limit exceeded", **kwargs)
    if status in {400, 404, 405, 413, 415, 422}:
        return ModelInvalidRequestError(
            "OpenAI rejected the request or configured model", **kwargs
        )
    return ModelResponseError("OpenAI API request failed", **kwargs)


def _retry_delay(response: httpx.Response | None, attempt: int, base: float) -> float:
    if response is not None:
        raw = response.headers.get("retry-after")
        if raw:
            try:
                delay = float(raw)
            except ValueError:
                try:
                    when = parsedate_to_datetime(raw)
                    delay = (when - datetime.now(UTC)).total_seconds()
                except (TypeError, ValueError, OverflowError):
                    delay = 0.0
            if math.isfinite(delay) and delay > 0:
                return min(delay, 60.0)
    return min(base * 2 ** (attempt - 1), 30.0)


def _json_object(response: httpx.Response) -> dict[str, object]:
    try:
        data = response.json()
    except ValueError as error:
        if response.is_error:
            return {}
        raise ModelResponseError("OpenAI returned an invalid JSON envelope") from error
    if not isinstance(data, dict):
        if response.is_error:
            return {}
        raise ModelResponseError("OpenAI returned a non-object JSON envelope")
    return data


def _usage_fields(data: Mapping[str, object]) -> dict[str, int | None]:
    usage = data.get("usage")
    if not isinstance(usage, dict):
        return {}
    input_details = usage.get("input_tokens_details", {})
    output_details = usage.get("output_tokens_details", {})
    return {
        "input_tokens": _nonnegative_integer(
            usage.get("input_tokens", usage.get("prompt_tokens"))
        ),
        "output_tokens": _nonnegative_integer(usage.get("output_tokens")),
        "total_tokens": _nonnegative_integer(usage.get("total_tokens")),
        "cached_input_tokens": _nonnegative_integer(input_details.get("cached_tokens"))
        if isinstance(input_details, dict)
        else None,
        "reasoning_tokens": _nonnegative_integer(output_details.get("reasoning_tokens"))
        if isinstance(output_details, dict)
        else None,
    }


def _append_journal(path: Path, record: ModelCallRecord) -> None:
    """Persist one complete JSONL record, including attempts without artifacts."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    payload = (record.model_dump_json() + "\n").encode("utf-8")
    descriptor = os.open(path, os.O_APPEND | os.O_WRONLY | os.O_CREAT, 0o600)
    try:
        # Docker runs Linux. flock also protects a shared journal across workers.
        import fcntl

        fcntl.flock(descriptor, fcntl.LOCK_EX)
        remaining = memoryview(payload)
        while remaining:
            written = os.write(descriptor, remaining)
            if written <= 0:
                raise OSError("model audit write made no progress")
            remaining = remaining[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


class _OpenAIClientBase:
    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = OPENAI_BASE_URL,
        timeout_seconds: float = 600.0,
        max_retries: int = 2,
        retry_base_seconds: float = 0.5,
        audit_path: str | Path | None = None,
        correlation_id: str | None = None,
    ) -> None:
        self._base_url = validate_openai_base_url(base_url)
        if not api_key.strip() or "\n" in api_key or "\r" in api_key:
            raise ValueError("OPENAI_API_KEY must contain a valid backend credential")
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("OpenAI timeout_seconds must be positive and finite")
        if type(max_retries) is not int or not 0 <= max_retries <= 5:
            raise ValueError("OpenAI max_retries must be between 0 and 5")
        if not math.isfinite(retry_base_seconds) or retry_base_seconds < 0:
            raise ValueError("OpenAI retry_base_seconds must be finite and nonnegative")
        self._api_key = api_key.strip()
        if correlation_id is not None and _safe_identifier(correlation_id) is None:
            raise ValueError(
                "OpenAI correlation_id must be a generated safe identifier"
            )
        self._correlation_id = correlation_id
        self._timeout = httpx.Timeout(
            timeout_seconds, connect=min(30.0, timeout_seconds)
        )
        self._max_retries = max_retries
        self._retry_base_seconds = retry_base_seconds
        self._audit_path = Path(audit_path) if audit_path is not None else None
        self._records: list[ModelCallRecord] = []
        self._records_lock = threading.Lock()
        self._request_started = False
        self._trace_ids: ContextVar[tuple[str, ...]] = ContextVar(
            f"openai_capture_{uuid4().hex}", default=()
        )

    @contextmanager
    def capture_calls(self) -> Iterator[OpenAICallCapture]:
        """Capture only the current async task's model attempts.

        Acceptance criteria:
            1. Concurrent clinical stages never claim each other's attempts.
            2. Child tasks inherit their current trace, including cancellations.
            3. Nested captures preserve both parent and child trace identities.
            4. Context is restored on both success and failure.
        """
        trace_id = f"trace_{uuid4().hex}"
        token = self._trace_ids.set((*self._trace_ids.get(), trace_id))
        try:
            yield OpenAICallCapture(self, trace_id)
        finally:
            self._trace_ids.reset(token)

    def bind_correlation_id(self, correlation_id: str) -> None:
        """Bind a generated session ID before the first request starts.

        Acceptance criteria:
            1. A client cannot be relabeled after any network operation starts.
            2. An already configured correlation ID cannot be changed.
            3. Invalid identifiers fail before any request is sent.
        """
        if _safe_identifier(correlation_id) is None:
            raise ValueError(
                "OpenAI correlation_id must be a generated safe identifier"
            )
        with self._records_lock:
            if self._request_started:
                raise ValueError(
                    "Cannot bind correlation_id after an OpenAI request starts"
                )
            if self._correlation_id not in {None, correlation_id}:
                raise ValueError("Cannot change an OpenAI client's correlation_id")
            self._correlation_id = correlation_id

    def _begin_operation(self) -> str:
        with self._records_lock:
            self._request_started = True
        return str(uuid4())

    @property
    def call_records(self) -> tuple[ModelCallRecord, ...]:
        """Return immutable snapshots; clients are scoped to one workflow run."""
        with self._records_lock:
            return tuple(self._records)

    def _headers(self, operation_id: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "X-Client-Request-Id": operation_id,
        }

    def _record(
        self,
        *,
        endpoint: str,
        request: Mapping[str, object],
        operation_id: str,
        attempt: int,
        started: float,
        created_at: datetime,
        response: httpx.Response | None = None,
        data: Mapping[str, object] | None = None,
        error: ModelProviderError | None = None,
    ) -> None:
        data = data or {}
        reasoning = request.get("reasoning")
        reasoning = reasoning if isinstance(reasoning, dict) else {}
        schema = _wire_schema(request)
        response_status = _safe_identifier(data.get("status"))
        if isinstance(error, ModelRefusalError):
            status = "refused"
        elif response_status in {"incomplete", "failed", "cancelled"}:
            status = response_status
        else:
            status = "error" if error else response_status or "completed"
        record = ModelCallRecord(
            call_id=f"call_{uuid4().hex}",
            operation_id=operation_id,
            correlation_id=self._correlation_id,
            trace_ids=self._trace_ids.get(),
            endpoint=endpoint,
            requested_model=str(request.get("model", "")),
            actual_model=_safe_identifier(data.get("model")),
            reasoning_mode=_safe_identifier(reasoning.get("mode")),
            reasoning_effort=_safe_identifier(reasoning.get("effort")),
            request_id=_safe_identifier(response.headers.get("x-request-id"))
            if response is not None
            else None,
            response_id=_safe_identifier(data.get("id")),
            request_hash=_json_hash(request),
            wire_schema_hash=_json_hash(schema) if schema is not None else None,
            status=status,
            response_status=response_status,
            http_status=response.status_code if response is not None else None,
            error_code=error.error_code if error is not None else None,
            attempt=attempt,
            created_at=created_at,
            elapsed_ms=max(0, round((time.monotonic() - started) * 1000)),
            **_usage_fields(data),
        )
        with self._records_lock:
            if self._audit_path is not None:
                try:
                    _append_journal(self._audit_path, record)
                except OSError as write_error:
                    raise ModelAuditError(
                        "OpenAI attempt could not be written to the audit journal"
                    ) from write_error
            self._records.append(record)

    def _process_http_response(
        self, response: httpx.Response, endpoint: str, request: Mapping[str, object]
    ) -> tuple[dict[str, object], ModelProviderError | None, bool]:
        try:
            data = _json_object(response)
        except ModelProviderError as error:
            return {}, error, False
        if response.status_code >= 300:
            error = _http_error(response, data)
            retryable = (
                response.status_code in _RETRYABLE_HTTP_STATUS
                and not isinstance(error, (ModelQuotaError, ModelAuthenticationError))
            )
            return data, error, retryable
        error = _response_error(data, request) if endpoint == "/responses" else None
        return data, error, False

    @staticmethod
    def _response_request(request: Mapping[str, object]) -> dict[str, object]:
        payload = deepcopy(dict(request))
        payload["store"] = False
        if payload.get("background") or payload.get("stream"):
            raise ValueError("This client requires foreground, non-streaming responses")
        return payload


@dataclass(frozen=True)
class OpenAICallCapture:
    """Immutable handle to a single task-local, optionally nested trace."""

    client: _OpenAIClientBase
    trace_id: str

    @property
    def records(self) -> tuple[ModelCallRecord, ...]:
        return tuple(
            record
            for record in self.client.call_records
            if self.trace_id in record.trace_ids
        )


class OpenAIClient(_OpenAIClientBase):
    """Pool asynchronous OpenAI connections for one report request.

    Acceptance criteria:
        1. Every attempt is authenticated and audited without content leakage.
        2. Only transient, classified transport failures are retried.
        3. Read timeouts fail directly to avoid repeating uncertain generation.
        4. Closing the client releases its owned connection pool.
    """

    def __init__(
        self,
        api_key: str,
        *,
        http_client: httpx.AsyncClient | None = None,
        **kwargs: object,
    ) -> None:
        super().__init__(api_key, **kwargs)
        self._owns_http_client = http_client is None
        self._http = http_client or httpx.AsyncClient(
            timeout=self._timeout, follow_redirects=False
        )

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_http_client:
            await self._http.aclose()

    async def response(self, request: Mapping[str, object]) -> dict[str, object]:
        return await self._post("/responses", self._response_request(request))

    async def structured_completion(
        self, request: Mapping[str, object]
    ) -> dict[str, object]:
        return _structured_object(await self.response(request))

    async def count_tokens(self, request: Mapping[str, object]) -> int:
        data = await self._post(
            "/responses/input_tokens", normalize_count_request(request)
        )
        count = _nonnegative_integer(data.get("input_tokens"))
        if count is None:
            raise ModelResponseError("OpenAI input-token response has no valid count")
        return count

    async def embeddings(self, request: Mapping[str, object]) -> dict[str, object]:
        return await self._post("/embeddings", deepcopy(dict(request)))

    async def _post(
        self, endpoint: str, request: dict[str, object]
    ) -> dict[str, object]:
        operation_id = self._begin_operation()
        for attempt in range(1, self._max_retries + 2):
            started = time.monotonic()
            created_at = datetime.now(UTC)
            response = None
            data: dict[str, object] = {}
            try:
                response = await self._http.post(
                    self._base_url + endpoint,
                    json=request,
                    headers=self._headers(operation_id),
                    timeout=self._timeout,
                    follow_redirects=False,
                )
            except asyncio.CancelledError:
                self._record(
                    endpoint=endpoint,
                    request=request,
                    operation_id=operation_id,
                    attempt=attempt,
                    started=started,
                    created_at=created_at,
                    error=ModelTimeoutError(
                        "OpenAI request was cancelled before a response was received",
                        error_code="client_cancelled",
                    ),
                )
                raise
            except httpx.TimeoutException as cause:
                error = ModelTimeoutError(
                    "OpenAI request timed out", error_code=type(cause).__name__
                )
                retryable = isinstance(cause, (httpx.ConnectTimeout, httpx.PoolTimeout))
            except httpx.RequestError as cause:
                error = ModelConnectionError(
                    "OpenAI connection failed", error_code=type(cause).__name__
                )
                retryable = isinstance(cause, httpx.ConnectError)
            else:
                data, error, retryable = self._process_http_response(
                    response, endpoint, request
                )
            self._record(
                endpoint=endpoint,
                request=request,
                operation_id=operation_id,
                attempt=attempt,
                started=started,
                created_at=created_at,
                response=response,
                data=data,
                error=error,
            )
            if error is None:
                return data
            if not retryable or attempt > self._max_retries:
                raise error
            await asyncio.sleep(
                _retry_delay(response, attempt, self._retry_base_seconds)
            )
        raise ModelResponseError("OpenAI request retry policy was exhausted")


class OpenAISyncClient(_OpenAIClientBase):
    """Synchronous transport for CPU document and literature service wrappers."""

    def __init__(
        self, api_key: str, *, http_client: httpx.Client | None = None, **kwargs: object
    ) -> None:
        super().__init__(api_key, **kwargs)
        self._owns_http_client = http_client is None
        self._http = http_client or httpx.Client(
            timeout=self._timeout, follow_redirects=False
        )

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def close(self) -> None:
        if self._owns_http_client:
            self._http.close()

    def response(self, request: Mapping[str, object]) -> dict[str, object]:
        return self._post("/responses", self._response_request(request))

    def structured_completion(self, request: Mapping[str, object]) -> dict[str, object]:
        return _structured_object(self.response(request))

    def count_tokens(self, request: Mapping[str, object]) -> int:
        data = self._post("/responses/input_tokens", normalize_count_request(request))
        count = _nonnegative_integer(data.get("input_tokens"))
        if count is None:
            raise ModelResponseError("OpenAI input-token response has no valid count")
        return count

    def embeddings(self, request: Mapping[str, object]) -> dict[str, object]:
        return self._post("/embeddings", deepcopy(dict(request)))

    def _post(self, endpoint: str, request: dict[str, object]) -> dict[str, object]:
        operation_id = self._begin_operation()
        for attempt in range(1, self._max_retries + 2):
            started = time.monotonic()
            created_at = datetime.now(UTC)
            response = None
            data: dict[str, object] = {}
            try:
                response = self._http.post(
                    self._base_url + endpoint,
                    json=request,
                    headers=self._headers(operation_id),
                    timeout=self._timeout,
                    follow_redirects=False,
                )
            except httpx.TimeoutException as cause:
                error = ModelTimeoutError(
                    "OpenAI request timed out", error_code=type(cause).__name__
                )
                retryable = isinstance(cause, (httpx.ConnectTimeout, httpx.PoolTimeout))
            except httpx.RequestError as cause:
                error = ModelConnectionError(
                    "OpenAI connection failed", error_code=type(cause).__name__
                )
                retryable = isinstance(cause, httpx.ConnectError)
            else:
                data, error, retryable = self._process_http_response(
                    response, endpoint, request
                )
            self._record(
                endpoint=endpoint,
                request=request,
                operation_id=operation_id,
                attempt=attempt,
                started=started,
                created_at=created_at,
                response=response,
                data=data,
                error=error,
            )
            if error is None:
                return data
            if not retryable or attempt > self._max_retries:
                raise error
            time.sleep(_retry_delay(response, attempt, self._retry_base_seconds))
        raise ModelResponseError("OpenAI request retry policy was exhausted")
