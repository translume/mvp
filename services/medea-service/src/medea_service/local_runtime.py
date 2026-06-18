from __future__ import annotations

import importlib
import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx

from medea_service.vendor_runtime import VendorRuntimeError

REMOTE_MODEL_ENV_KEYS: tuple[str, ...] = (
    "OPENROUTER_API_KEY",
    "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "AZURE_OPENAI_API_KEY",
    "AZURE_OPENAI_ENDPOINT",
    "NVIDIA_API_KEY",
    "OPENROUTER_SITE_URL",
    "OPENROUTER_SITE_NAME",
)

REMOTE_MODEL_NAME_TOKENS: tuple[str, ...] = (
    "gpt-4",
    "gpt-5",
    "claude",
    "gemini",
    "openai/",
    "anthropic/",
    "google/",
    "openrouter/",
)

DEFAULT_ALLOWED_LOCAL_HOSTS: tuple[str, ...] = (
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "host.docker.internal",
    "vllm",
    "vllm-clinical",
)

DEFAULT_LOCAL_OPENAI_API_KEY = "local-vllm"


@dataclass(frozen=True)
class LocalMedeaRoutingConfig:
    """Validated local-vLLM routing configuration for Medea.

    Acceptance criteria:
        1. Contains only local OpenAI-compatible vLLM routing values.
        2. Does not store or expose remote provider credentials.
        3. Is created only after remote-provider checks pass.
    """

    vllm_base_url: str
    model_name: str
    timeout_seconds: float
    local_openai_api_key: str
    provider_name: str = "OpenAI"


def parse_allowed_hosts(value: str | None) -> tuple[str, ...]:
    """Return configured local model hosts.

    Acceptance criteria:
        1. Blank input falls back to the safe local host allow-list.
        2. Returned hosts are normalized to lowercase.
        3. Function is deterministic and pure.
    """
    if not value or not value.strip():
        return DEFAULT_ALLOWED_LOCAL_HOSTS
    hosts = tuple(item.strip().casefold() for item in value.split(",") if item.strip())
    return hosts or DEFAULT_ALLOWED_LOCAL_HOSTS


def validate_local_vllm_url(base_url: str, allowed_hosts: tuple[str, ...]) -> str:
    """Validate that a model URL points at an allowed local vLLM host.

    Acceptance criteria:
        1. Requires http or https URL.
        2. Requires host in the configured local-host allow-list.
        3. Rejects known hosted provider domains.
        4. Returns a stripped URL without trailing slash.
    """
    stripped = base_url.strip().rstrip("/")
    if not stripped:
        raise VendorRuntimeError("VLLM_BASE_URL is required for Medea local routing")
    parsed = urlparse(stripped)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise VendorRuntimeError(f"VLLM_BASE_URL must be an HTTP(S) URL: {base_url!r}")
    host = (parsed.hostname or "").casefold()
    blocked_hosts = (
        "api.openai.com",
        "openrouter.ai",
        "api.anthropic.com",
        "generativelanguage.googleapis.com",
        "integrate.api.nvidia.com",
    )
    if host in blocked_hosts or any(host.endswith("." + blocked) for blocked in blocked_hosts):
        raise VendorRuntimeError(f"remote model host is not allowed for Medea: {host}")
    if host not in set(allowed_hosts):
        raise VendorRuntimeError(
            "VLLM_BASE_URL host is not in MEDEA_ALLOWED_LOCAL_MODEL_HOSTS: "
            f"{host}; allowed={', '.join(allowed_hosts)}"
        )
    return stripped


def validate_local_model_name(model_name: str) -> str:
    """Reject remote-provider-style model names for Medea local routing.

    Acceptance criteria:
        1. Blank model names are rejected.
        2. Known hosted-provider model names are rejected by default.
        3. Local/Hugging Face model identifiers are returned unchanged except stripping.
    """
    stripped = model_name.strip()
    if not stripped:
        raise VendorRuntimeError("VLLM_MODEL is required for Medea local routing")
    if os.getenv("MEDEA_ALLOW_REMOTE_STYLE_MODEL_NAMES", "false").casefold() != "true":
        lowered = stripped.casefold()
        if any(token in lowered for token in REMOTE_MODEL_NAME_TOKENS):
            raise VendorRuntimeError(
                "VLLM_MODEL looks like a hosted remote-provider model name. "
                "Set a real local/Hugging Face model id, or explicitly set "
                "MEDEA_ALLOW_REMOTE_STYLE_MODEL_NAMES=true only if vLLM serves that alias."
            )
    return stripped


def assert_remote_model_environment_blocked(environment: Mapping[str, str] | None = None) -> None:
    """Reject remote model-provider credentials and endpoints for Medea.

    Acceptance criteria:
        1. Blocks OpenRouter, Anthropic, Gemini, Google, Azure, and NVIDIA credentials.
        2. Blocks OPENAI_API_KEY unless it is the configured local sentinel value.
        3. Blocks OPENAI_BASE_URL / OPENAI_API_BASE when they point outside local vLLM.
        4. Does not mutate environment.
    """
    env = environment or os.environ
    blocked = [key for key in REMOTE_MODEL_ENV_KEYS if env.get(key, "").strip()]
    local_key = env.get("MEDEA_LOCAL_OPENAI_API_KEY", DEFAULT_LOCAL_OPENAI_API_KEY).strip()
    openai_key = env.get("OPENAI_API_KEY", "").strip()
    if openai_key and openai_key != local_key:
        blocked.append("OPENAI_API_KEY")
    allowed_hosts = parse_allowed_hosts(env.get("MEDEA_ALLOWED_LOCAL_MODEL_HOSTS"))
    for key in ("OPENAI_BASE_URL", "OPENAI_API_BASE"):
        value = env.get(key, "").strip()
        if value:
            try:
                validate_local_vllm_url(value, allowed_hosts)
            except VendorRuntimeError:
                blocked.append(key)
    if blocked:
        raise VendorRuntimeError(
            "remote model-provider configuration is not allowed for Medea local routing: "
            + ", ".join(sorted(set(blocked)))
        )


def build_local_medea_routing_config(environment: Mapping[str, str] | None = None) -> LocalMedeaRoutingConfig:
    """Build validated local routing config for Medea.

    Acceptance criteria:
        1. Requires VLLM_BASE_URL and VLLM_MODEL.
        2. Rejects remote provider credentials before returning.
        3. Rejects non-local model URLs.
        4. Returns a config that can be applied to Medea environment and patches.
    """
    env = environment or os.environ
    assert_remote_model_environment_blocked(env)
    allowed_hosts = parse_allowed_hosts(env.get("MEDEA_ALLOWED_LOCAL_MODEL_HOSTS"))
    base_url = validate_local_vllm_url(env.get("VLLM_BASE_URL", ""), allowed_hosts)
    model_name = validate_local_model_name(env.get("VLLM_MODEL", ""))
    timeout = float(env.get("MEDEA_VLLM_TIMEOUT_SECONDS", env.get("VLLM_TIMEOUT_SECONDS", "240")))
    local_key = env.get("MEDEA_LOCAL_OPENAI_API_KEY", DEFAULT_LOCAL_OPENAI_API_KEY).strip() or DEFAULT_LOCAL_OPENAI_API_KEY
    return LocalMedeaRoutingConfig(
        vllm_base_url=base_url,
        model_name=model_name,
        timeout_seconds=timeout,
        local_openai_api_key=local_key,
    )


def apply_local_medea_environment(config: LocalMedeaRoutingConfig) -> None:
    """Apply local-only Medea model environment variables.

    Acceptance criteria:
        1. Forces Medea provider routing to OpenAI-compatible local vLLM.
        2. Overwrites OPENAI_API_KEY with a local sentinel, not a real remote key.
        3. Sets OpenAI-compatible base URLs to VLLM_BASE_URL.
        4. Does not set any remote-provider credentials.
    """
    os.environ["LLM_PROVIDER_NAME"] = config.provider_name
    os.environ["BACKBONE_LLM"] = config.model_name
    os.environ["UTILITY_LLM"] = config.model_name
    os.environ["OPENAI_BASE_URL"] = config.vllm_base_url
    os.environ["OPENAI_API_BASE"] = config.vllm_base_url
    os.environ["OPENAI_API_KEY"] = config.local_openai_api_key
    os.environ["LLM_REQUEST_TIMEOUT"] = str(int(config.timeout_seconds))


def build_local_vllm_chat_completion(config: LocalMedeaRoutingConfig):
    """Build a synchronous chat-completion function that calls local vLLM.

    Acceptance criteria:
        1. Calls only the configured local vLLM chat-completions URL.
        2. Accepts Medea's chat_completion signature shape.
        3. Does not call any remote provider SDK.
        4. Raises when local vLLM returns non-2xx or invalid response shape.
    """

    def local_chat_completion(
        messages: Any,
        temperature: float = 0.0,
        model: str | None = None,
        mod: str = "query",
        attempts: int = 1,
        seed: int | None = None,
        use_openrouter: bool = False,
        response_format: dict[str, Any] | None = None,
        reasoning_effort: str | None = None,
        **_: Any,
    ) -> str:
        if mod == "query" and isinstance(messages, str):
            formatted_messages = [{"role": "user", "content": messages}]
        else:
            formatted_messages = messages
        if not isinstance(formatted_messages, list):
            raise VendorRuntimeError("Medea local vLLM messages must be a list or query string")
        request: dict[str, Any] = {
            "model": model or config.model_name,
            "messages": formatted_messages,
            "temperature": temperature,
        }
        if seed is not None:
            request["seed"] = seed
        if response_format is not None:
            request["response_format"] = response_format
        if reasoning_effort is not None:
            request["extra_body"] = {"reasoning_effort": reasoning_effort}
        url = f"{config.vllm_base_url}/chat/completions"
        last_error = "not attempted"
        for _attempt in range(max(1, attempts)):
            try:
                with httpx.Client(timeout=config.timeout_seconds) as client:
                    response = client.post(url, json=request)
                if response.status_code >= 400:
                    last_error = f"{response.status_code} {response.text[:500]}"
                    continue
                payload = response.json()
                content = payload["choices"][0]["message"]["content"]
                if not isinstance(content, str):
                    return str(content)
                return content
            except Exception as error:  # pragma: no cover - exercised by integration failures
                last_error = str(error)
        raise VendorRuntimeError(f"local vLLM chat completion failed: {last_error}")

    return local_chat_completion


def patch_medea_chat_completion_to_local_vllm(
    medea_module: Any,
    config: LocalMedeaRoutingConfig,
) -> tuple[str, ...]:
    """Patch Medea's LLM call sites to use local vLLM.

    Acceptance criteria:
        1. Patches real imported Medea modules from outside the vendored repo.
        2. Does not edit files inside the Medea repository.
        3. Fails if no known Medea LLM call site can be patched.
        4. Returns the patched module names for runtime validation.
    """
    local_completion = build_local_vllm_chat_completion(config)
    candidate_modules = (
        "medea.tool_space.gpt_utils",
        "medea.modules.agent_llms",
    )
    patched: list[str] = []
    for module_name in candidate_modules:
        try:
            module = importlib.import_module(module_name)
        except ImportError:
            continue
        if hasattr(module, "chat_completion"):
            setattr(module, "chat_completion", local_completion)
            patched.append(module_name)
    if not patched and hasattr(medea_module, "chat_completion"):
        setattr(medea_module, "chat_completion", local_completion)
        patched.append(getattr(medea_module, "__name__", "medea"))
    if not patched:
        raise VendorRuntimeError(
            "no Medea chat_completion call site could be patched for local vLLM"
        )
    return tuple(patched)


def configure_and_patch_medea_for_local_vllm(medea_module: Any) -> tuple[LocalMedeaRoutingConfig, tuple[str, ...]]:
    """Validate local model routing, apply environment, and patch Medea call sites."""
    config = build_local_medea_routing_config(os.environ)
    apply_local_medea_environment(config)
    patched_modules = patch_medea_chat_completion_to_local_vllm(medea_module, config)
    return config, patched_modules
