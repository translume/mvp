from __future__ import annotations

import pytest

from medea_service.local_runtime import (
    DEFAULT_LOCAL_OPENAI_API_KEY,
    assert_remote_model_environment_blocked,
    build_local_medea_routing_config,
    validate_local_model_name,
    validate_local_vllm_url,
)
from medea_service.vendor_runtime import VendorRuntimeError


def test_local_vllm_url_accepts_configured_local_host() -> None:
    assert (
        validate_local_vllm_url("http://vllm-clinical:8000/v1/", ("vllm-clinical",))
        == "http://vllm-clinical:8000/v1"
    )


def test_local_vllm_url_rejects_remote_openai_host() -> None:
    with pytest.raises(VendorRuntimeError, match="remote model host"):
        validate_local_vllm_url("https://api.openai.com/v1", ("localhost",))


def test_remote_provider_environment_blocks_real_openai_key() -> None:
    with pytest.raises(VendorRuntimeError, match="OPENAI_API_KEY"):
        assert_remote_model_environment_blocked(
            {
                "OPENAI_API_KEY": "sk-real-remote-key",
                "MEDEA_LOCAL_OPENAI_API_KEY": DEFAULT_LOCAL_OPENAI_API_KEY,
            }
        )


def test_remote_provider_environment_allows_local_openai_sentinel() -> None:
    assert_remote_model_environment_blocked(
        {
            "OPENAI_API_KEY": DEFAULT_LOCAL_OPENAI_API_KEY,
            "MEDEA_LOCAL_OPENAI_API_KEY": DEFAULT_LOCAL_OPENAI_API_KEY,
            "OPENAI_BASE_URL": "http://vllm:8000/v1",
            "MEDEA_ALLOWED_LOCAL_MODEL_HOSTS": "vllm",
        }
    )


def test_local_routing_config_rejects_remote_model_name_by_default() -> None:
    with pytest.raises(VendorRuntimeError, match="hosted remote-provider model"):
        validate_local_model_name("gpt-4o")


def test_build_local_medea_routing_config_from_environment() -> None:
    config = build_local_medea_routing_config(
        {
            "VLLM_BASE_URL": "http://vllm:8000/v1",
            "VLLM_MODEL": "meta-llama/Llama-3.1-8B-Instruct",
            "MEDEA_ALLOWED_LOCAL_MODEL_HOSTS": "vllm",
            "VLLM_TIMEOUT_SECONDS": "33",
        }
    )
    assert config.vllm_base_url == "http://vllm:8000/v1"
    assert config.model_name == "meta-llama/Llama-3.1-8B-Instruct"
    assert config.timeout_seconds == 33
