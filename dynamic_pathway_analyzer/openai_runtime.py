"""Remote OpenAI request policy shared by both pathway-analysis commands.

This module performs no local model inference. It records request metadata,
validates Responses completion states, and keeps retries finite. Audit records
contain hashes and provider metadata, never input text or credential values.
"""

from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
import os
import random
import tempfile
import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from openai import APIConnectionError, APIError, APIStatusError, OpenAI
from pydantic import BaseModel, ValidationError

OFFICIAL_BASE_URL = "https://api.openai.com/v1"


@dataclass(frozen=True)
class RemoteSettings:
    """Explicit bounds for one remote pipeline execution."""

    reasoning_mode: str = "pro"
    reasoning_effort: str = "xhigh"
    request_timeout_seconds: float = 900.0
    max_attempts: int = 3
    max_output_tokens: int = 32_000
    max_retry_output_tokens: int = 64_000

    def __post_init__(self) -> None:
        if self.reasoning_mode != "pro":
            raise ValueError("OPENAI_REASONING_MODE must be pro.")
        if self.reasoning_effort not in {"low", "medium", "high", "xhigh", "max"}:
            raise ValueError("Unsupported Astra reasoning effort.")
        if not 1 <= self.max_attempts <= 10:
            raise ValueError("max_attempts must be between 1 and 10.")
        if not 1 <= self.request_timeout_seconds <= 7200:
            raise ValueError("request_timeout_seconds must be in (0, 7200].")
        if not 1 <= self.max_output_tokens <= self.max_retry_output_tokens <= 128_000:
            raise ValueError("Output-token bounds must be positive and ordered.")


class OpenAIRequestFailure(RuntimeError):
    """A terminal provider or response-state failure without clinical content."""


def build_client(api_key: str | None, settings: RemoteSettings) -> OpenAI:
    """Create an official remote client with SDK retries disabled.

    Acceptance criteria:
        1. Missing credentials or a nonofficial base URL fail before network I/O.
        2. The request wrapper is the sole retry owner.
        3. No environment setting can route inference to a local server.
    """
    if not api_key or not api_key.strip():
        raise ValueError("OPENAI_API_KEY is required.")
    configured = os.getenv("OPENAI_BASE_URL", OFFICIAL_BASE_URL).rstrip("/")
    if configured != OFFICIAL_BASE_URL:
        raise ValueError("OPENAI_BASE_URL must be https://api.openai.com/v1.")
    return OpenAI(
        api_key=api_key,
        base_url=OFFICIAL_BASE_URL,
        timeout=settings.request_timeout_seconds,
        max_retries=0,
    )


def strict_schema(schema: Mapping[str, Any]) -> dict[str, Any]:
    """Copy a Pydantic schema into the strict Responses schema dialect.

    Acceptance criteria:
        1. All generated fields are required, preserving existing nullability.
        2. Object schemas are closed; unconstrained output maps fail clearly.
        3. A property named default survives while schema defaults are removed.
        4. Caller-owned schemas and domain models are unchanged.
    """
    result = copy.deepcopy(dict(schema))
    result.pop("default", None)
    for key in ("$defs", "definitions", "properties"):
        children = result.get(key)
        if isinstance(children, dict):
            result[key] = {
                name: strict_schema(child) for name, child in children.items()
            }
    for key in ("items", "contains", "not", "if", "then", "else"):
        child = result.get(key)
        if isinstance(child, dict):
            result[key] = strict_schema(child)
    for key in ("anyOf", "oneOf", "allOf", "prefixItems"):
        children = result.get(key)
        if isinstance(children, list):
            result[key] = [strict_schema(child) for child in children]
    if result.get("type") == "object" or "properties" in result:
        if result.get("additionalProperties") not in (False, None):
            raise ValueError("OpenAI output schema cannot contain an open map.")
        result["required"] = list(result.get("properties", {}))
        result["additionalProperties"] = False
    return result


def text_format(model: type[BaseModel]) -> dict[str, Any]:
    """Return strict text.format while retaining the original domain validator."""
    return {
        "format": {
            "type": "json_schema",
            "name": model.__name__,
            "schema": strict_schema(model.model_json_schema()),
            "strict": True,
        }
    }


def error_code(error: APIError) -> str | None:
    """Read a machine-readable code without returning an API response body."""
    body = getattr(error, "body", None)
    if isinstance(body, Mapping):
        nested = body.get("error", body)
        if isinstance(nested, Mapping):
            code = nested.get("code")
            return str(code) if code else None
    code = getattr(error, "code", None)
    return str(code) if code else None


def retryable_api_error(error: APIError) -> bool:
    """Classify only transient failures as transport-retryable."""
    if isinstance(error, APIConnectionError):
        return True
    if not isinstance(error, APIStatusError):
        return False
    if error_code(error) in {
        "insufficient_quota",
        "billing_hard_limit_reached",
        "billing_not_active",
        "billing_limit_reached",
        "account_deactivated",
        "invalid_api_key",
    }:
        return False
    return error.status_code in {408, 409, 429} or error.status_code >= 500


def _json_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def write_json_atomic(path: Path, payload: Any) -> None:
    """Persist an artifact atomically; a failed write never exposes partial JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def write_text_atomic(path: Path, value: str) -> None:
    """Persist UTF-8 output atomically, preserving existing output on failure."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def response_metadata(response: Any) -> dict[str, Any]:
    """Extract usage and completion state without including response content."""
    payload = response.model_dump(mode="json")
    refusal_present = any(
        content.get("type") == "refusal"
        for item in payload.get("output", [])
        if isinstance(item, Mapping) and item.get("type") == "message"
        for content in item.get("content", [])
        if isinstance(content, Mapping)
    )
    incomplete = payload.get("incomplete_details") or {}
    return {
        "response_id": payload.get("id") or getattr(response, "id", None),
        "request_id": getattr(response, "_request_id", None),
        "model": payload.get("model") or getattr(response, "model", None),
        "status": payload.get("status") or getattr(response, "status", None),
        "incomplete_reason": incomplete.get("reason"),
        "refusal_present": refusal_present,
        "usage": payload.get("usage") or {},
    }


def request_response(
    client: OpenAI,
    *,
    stage: str,
    request: Mapping[str, Any],
    settings: RemoteSettings,
    audit_dir: Path | None = None,
    response_model: type[BaseModel] | None = None,
) -> Any:
    """Run one bounded Responses operation and persist every observed attempt.

    Acceptance criteria:
        1. All attempts explicitly use Pro mode, a token limit, and store=False.
        2. Credential, quota, refusal, filter, and bad-request failures stop.
        3. A token-limit response gets at most one larger bounded request.
        4. Incomplete or failed output is never returned as a completed report.
        5. Audit records retain actual response IDs and usage, including failures.
    """
    call_id = f"call_{uuid.uuid4().hex}"
    parameters = copy.deepcopy(dict(request))
    parameters["reasoning"] = {
        "mode": settings.reasoning_mode,
        "effort": settings.reasoning_effort,
    }
    parameters["store"] = False
    parameters["max_output_tokens"] = settings.max_output_tokens
    expanded_output = False
    for attempt in range(1, settings.max_attempts + 1):
        receipt: dict[str, Any] = {
            "call_id": call_id,
            "stage": stage,
            "attempt": attempt,
            "provider": "openai",
            "requested_model": parameters.get("model"),
            "reasoning_mode": settings.reasoning_mode,
            "reasoning_effort": settings.reasoning_effort,
            "max_output_tokens": parameters["max_output_tokens"],
            "wire_schema_sha256": (
                _json_hash(parameters["text"]["format"]["schema"])
                if "text" in parameters
                else None
            ),
            "request_sha256": _json_hash(parameters),
            "created_at": dt.datetime.now(dt.UTC).isoformat(),
            "outcome": "started",
        }
        audit_path = (
            audit_dir / f"{call_id}_attempt_{attempt}.json"
            if audit_dir is not None
            else None
        )
        if audit_path is not None:
            write_json_atomic(audit_path, receipt)
        try:
            response = client.responses.create(**parameters)
        except APIError as error:
            receipt.update(
                {
                    "outcome": "failed",
                    "error_type": type(error).__name__,
                    "status_code": getattr(error, "status_code", None),
                    "error_code": error_code(error),
                    "request_id": getattr(error, "request_id", None),
                }
            )
            if audit_path is not None:
                write_json_atomic(audit_path, receipt)
            if not retryable_api_error(error) or attempt == settings.max_attempts:
                raise OpenAIRequestFailure(
                    f"OpenAI request failed: stage={stage!r}, "
                    f"error={type(error).__name__}, "
                    f"status={receipt['status_code']!r}, "
                    f"code={receipt['error_code']!r}, "
                    f"request_id={receipt['request_id']!r}"
                ) from error
            time.sleep(min(30.0, 2 ** (attempt - 1) + random.random()))
            continue
        metadata = response_metadata(response)
        complete = metadata["status"] == "completed" and not metadata["refusal_present"]
        receipt.update({**metadata, "outcome": "completed" if complete else "failed"})
        if audit_path is not None:
            write_json_atomic(audit_path, receipt)
        if complete:
            if not all(
                isinstance(metadata[key], str) and metadata[key].strip()
                for key in ("response_id", "model")
            ):
                receipt.update(
                    {
                        "outcome": "failed",
                        "error_type": "InvalidResponseMetadata",
                    }
                )
                if audit_path is not None:
                    write_json_atomic(audit_path, receipt)
                raise OpenAIRequestFailure(
                    f"OpenAI omitted response/model identity: stage={stage!r}."
                )
            try:
                if not response.output_text or not response.output_text.strip():
                    raise OpenAIRequestFailure(
                        f"OpenAI returned empty output: stage={stage!r}."
                    )
                if response_model is not None:
                    structured_output(response, response_model, stage=stage)
            except OpenAIRequestFailure as error:
                receipt.update(
                    {
                        "outcome": "failed",
                        "error_type": type(error).__name__,
                        "domain_validation": "failed",
                    }
                )
                if audit_path is not None:
                    write_json_atomic(audit_path, receipt)
                raise
            if response_model is not None and audit_path is not None:
                write_json_atomic(
                    audit_path,
                    {
                        **receipt,
                        "domain_validation": "passed",
                    },
                )
            return response
        if (
            metadata["status"] == "incomplete"
            and metadata["incomplete_reason"] == "max_output_tokens"
            and not metadata["refusal_present"]
            and not expanded_output
            and attempt < settings.max_attempts
            and settings.max_retry_output_tokens > settings.max_output_tokens
        ):
            expanded_output = True
            parameters["max_output_tokens"] = settings.max_retry_output_tokens
            continue
        raise OpenAIRequestFailure(
            f"OpenAI response did not complete: stage={stage!r}, "
            f"status={metadata['status']!r}, "
            f"reason={metadata['incomplete_reason']!r}, "
            f"refusal_present={metadata['refusal_present']!r}, "
            f"response_id={metadata['response_id']!r}"
        )
    raise OpenAIRequestFailure("OpenAI retry policy exhausted without a response.")


def structured_output[ModelT: BaseModel](
    response: Any,
    model: type[ModelT],
    *,
    stage: str,
) -> ModelT:
    """Validate completed JSON without manufacturing a missing output."""
    text = getattr(response, "output_text", None)
    if not isinstance(text, str) or not text.strip():
        raise OpenAIRequestFailure(
            f"OpenAI returned no structured text: stage={stage!r}."
        )
    try:
        return model.model_validate_json(text)
    except ValidationError as error:
        raise OpenAIRequestFailure(
            f"OpenAI output failed domain validation: stage={stage!r}, "
            f"response_id={getattr(response, 'id', None)!r}, "
            f"invalid_fields={error.error_count()}"
        ) from error
