"""OpenAI-only inference configuration and bounded Medea completion adapter."""

from __future__ import annotations

import math
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from threading import Event, Lock
from typing import Any

from translume_adapters.model_providers.openai_schema import to_openai_strict_schema
from translume_clients.openai_client import OpenAISyncClient, response_text
from translume_schemas.model_calls import ModelOutputTruncatedError

from medea_service.vendor_runtime import VendorRuntimeError

_OTHER_PROVIDER_KEYS = (
    "OPENROUTER_API_KEY",
    "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "AZURE_OPENAI_API_KEY",
    "AZURE_OPENAI_ENDPOINT",
    "NVIDIA_API_KEY",
)
_EFFORTS = {"low", "medium", "high", "xhigh", "max"}


@dataclass(frozen=True)
class OpenAIMedeaConfig:
    """Immutable routing settings; repr never contains the credential."""

    api_key: str = field(repr=False)
    base_url: str = "https://api.openai.com/v1"
    model_name: str = "gpt-6-astra"
    reasoning_mode: str = "pro"
    reasoning_effort: str = "xhigh"
    timeout_seconds: float = 900.0
    max_output_tokens: int = 32768
    retry_max_output_tokens: int = 65536
    input_token_budget: int = 100000
    max_model_calls: int = 32
    embedding_model: str = "text-embedding-3-large"
    embedding_dimensions: int = 1536

    def __post_init__(self) -> None:
        if not self.api_key.strip() or self.api_key in {"local-vllm", "sk-placeholder"}:
            raise VendorRuntimeError("OPENAI_API_KEY is required for Medea")
        if self.base_url.rstrip("/") != "https://api.openai.com/v1":
            raise VendorRuntimeError("Medea requires https://api.openai.com/v1")
        if not self.model_name.startswith("gpt-6-astra"):
            raise VendorRuntimeError("Medea requires an Astra reasoning model")
        if self.reasoning_mode != "pro" or self.reasoning_effort not in _EFFORTS:
            raise VendorRuntimeError("Medea requires Pro mode and a valid effort")
        if (
            not math.isfinite(self.timeout_seconds)
            or min(
                self.timeout_seconds,
                self.max_output_tokens,
                self.retry_max_output_tokens,
                self.input_token_budget,
                self.max_model_calls,
                self.embedding_dimensions,
            )
            <= 0
        ):
            raise VendorRuntimeError("Medea request limits must be positive")
        if self.retry_max_output_tokens < self.max_output_tokens:
            raise VendorRuntimeError("Medea retry output budget must not shrink")


def build_openai_medea_config(
    environment: Mapping[str, str] | None = None,
) -> OpenAIMedeaConfig:
    """Read and validate the only supported remote inference route.

    Acceptance criteria:
        1. Reject missing OpenAI credentials and alternate/local endpoints.
        2. Reject configured provider fallbacks without exposing their values.
        3. Preserve the caller's environment and the real OpenAI credential.
    """
    env = os.environ if environment is None else environment
    blocked = [key for key in _OTHER_PROVIDER_KEYS if env.get(key, "").strip()]
    if blocked:
        raise VendorRuntimeError(
            "Medea permits only OpenAI model credentials; remove " + ", ".join(blocked)
        )
    if env.get("TRANSLUME_ALLOW_LOCAL_INFERENCE", "false").lower() != "false":
        raise VendorRuntimeError("local inference must remain disabled")
    try:
        return OpenAIMedeaConfig(
            api_key=env.get("OPENAI_API_KEY", "").strip(),
            base_url=env.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip(
                "/"
            ),
            model_name=env.get("OPENAI_REASONING_MODEL", "gpt-6-astra").strip(),
            reasoning_mode=env.get("OPENAI_REASONING_MODE", "pro"),
            reasoning_effort=env.get("OPENAI_REASONING_EFFORT", "xhigh"),
            timeout_seconds=float(env.get("OPENAI_REQUEST_TIMEOUT_SECONDS", "900")),
            max_output_tokens=int(
                env.get(
                    "MEDEA_MAX_OUTPUT_TOKENS",
                    env.get("OPENAI_MAX_OUTPUT_TOKENS", "32768"),
                )
            ),
            retry_max_output_tokens=int(
                env.get(
                    "MEDEA_RETRY_MAX_OUTPUT_TOKENS",
                    env.get("OPENAI_RETRY_MAX_OUTPUT_TOKENS", "65536"),
                )
            ),
            input_token_budget=int(env.get("MEDEA_INPUT_TOKEN_BUDGET", "100000")),
            max_model_calls=int(env.get("MEDEA_MAX_MODEL_CALLS", "32")),
            embedding_model=env.get("OPENAI_EMBEDDING_MODEL", "text-embedding-3-large"),
            embedding_dimensions=int(env.get("OPENAI_EMBEDDING_DIMENSIONS", "1536")),
        )
    except ValueError as error:
        raise VendorRuntimeError(
            "Medea numeric environment settings are invalid"
        ) from error


def build_openai_client(config: OpenAIMedeaConfig) -> OpenAISyncClient:
    """Create the service-owned pooled transport, with one transport retry owner."""
    return OpenAISyncClient(
        api_key=config.api_key,
        base_url=config.base_url,
        timeout_seconds=config.timeout_seconds,
        audit_path=os.environ.get("OPENAI_AUDIT_PATH") or None,
    )


class OpenAICompletion:
    """A request-scoped callable accepted by the actual upstream OpenScholar.

    It holds no local model, does not modify vendor files, and records only real
    response identifiers. Its bounded call counter is shared by worker threads.
    """

    def __init__(
        self,
        client: OpenAISyncClient,
        config: OpenAIMedeaConfig,
        cancel_event: Event | None = None,
    ) -> None:
        self.client = client
        self.config = config
        self._lock = Lock()
        self._calls = 0
        self._response_ids: list[str] = []
        self._cancel_event = cancel_event or Event()

    def checkpoint(self) -> None:
        """Prevent any additional model requests after cancellation or timeout."""
        if self._cancel_event.is_set():
            raise VendorRuntimeError("Medea request was cancelled")

    @property
    def response_ids(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(self._response_ids)

    def send(self, request: dict[str, Any]) -> dict[str, Any]:
        """Retry only a known output-token-limit stop, once with a larger cap.

        Acceptance criteria:
            1. Authentication, quota, refusal and other provider errors propagate.
            2. Truncated output is never parsed as evidence or used as a prompt.
            3. Every attempt passes final-request counting and the call budget.
        """
        initial = request.get("max_output_tokens", self.config.max_output_tokens)
        limits = tuple(
            dict.fromkeys((initial, max(initial, self.config.retry_max_output_tokens)))
        )
        for index, limit in enumerate(limits):
            try:
                return self._send_once({**request, "max_output_tokens": limit})
            except ModelOutputTruncatedError:
                if index == len(limits) - 1:
                    raise
        raise VendorRuntimeError("Medea exhausted its output-token recovery budget")

    def _send_once(self, request: dict[str, Any]) -> dict[str, Any]:
        """Check the final request budget, execute, and retain its actual ID.

        Acceptance criteria:
            1. Every initial and corrective request has its actual tokens counted.
            2. Calls and input tokens are bounded before inference.
            3. Transport, refusal and quota errors propagate unchanged.
        """
        self.checkpoint()
        with self._lock:
            if self._calls >= self.config.max_model_calls:
                raise VendorRuntimeError("Medea exceeded its bounded model-call budget")
            self._calls += 1
        if self.client.count_tokens(request) > self.config.input_token_budget:
            raise VendorRuntimeError("Medea request exceeds its input-token budget")
        self.checkpoint()
        response = self.client.response(request)
        identifier = response.get("id")
        if isinstance(identifier, str) and identifier:
            with self._lock:
                self._response_ids.append(identifier)
        self.checkpoint()
        return response

    def __call__(
        self,
        messages: Any,
        temperature: float = 0.0,
        model: str | None = None,
        mod: str = "query",
        attempts: int = 1,
        seed: int | None = None,
        use_openrouter: bool = False,
        response_format: dict[str, Any] | None = None,
        reasoning_effort: str | None = None,
        **unused: Any,
    ) -> str:
        """Adapt the upstream call signature to the official Responses API.

        Acceptance criteria:
            1. Compatibility arguments never activate another provider or retry loop.
            2. Astra receives no unsupported temperature, seed or logprob fields.
            3. An upstream request for a different model is rejected explicitly.
        """
        if model and model != self.config.model_name:
            raise VendorRuntimeError("Medea attempted an unconfigured model route")
        effort = reasoning_effort or self.config.reasoning_effort
        if effort not in _EFFORTS:
            raise VendorRuntimeError("Medea requested an unsupported reasoning effort")
        request = build_medea_request(self.config, messages, effort=effort)
        if response_format is not None:
            if response_format.get("type") == "json_schema":
                specification = response_format.get("json_schema", {})
                request["text"] = {
                    "format": {
                        "type": "json_schema",
                        "name": specification.get("name", "MedeaOutput"),
                        "schema": to_openai_strict_schema(specification["schema"]),
                        "strict": True,
                    }
                }
            elif response_format.get("type") == "json_object":
                request["text"] = {"format": {"type": "json_object"}}
            else:
                raise VendorRuntimeError("unsupported Medea response format")
        return response_text(self.send(request))


def build_medea_request(
    config: OpenAIMedeaConfig,
    messages: Any,
    *,
    effort: str | None = None,
    schema_name: str | None = None,
    schema: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a real remote request; optional strict schemas are copied, not mutated."""
    if not isinstance(messages, (str, list)):
        raise VendorRuntimeError("Medea input must be text or a message list")
    request: dict[str, Any] = {
        "model": config.model_name,
        "input": messages,
        "reasoning": {
            "mode": config.reasoning_mode,
            "effort": effort or config.reasoning_effort,
        },
        "max_output_tokens": config.max_output_tokens,
        "store": False,
    }
    if schema is not None:
        request["text"] = {
            "format": {
                "type": "json_schema",
                "name": schema_name or "MedeaOutput",
                "schema": to_openai_strict_schema(schema),
                "strict": True,
            }
        }
    return request
