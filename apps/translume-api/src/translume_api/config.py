from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel


class Settings(BaseModel):
    """Runtime settings for the Translume API."""

    app_name: str = "translume-api"
    block_remote_model_providers: bool = True
    storage_root: Path = Path("data/uploads")
    require_mims: bool = True
    optimuskg_service_url: str = "http://optimuskg-service:8091"
    tooluniverse_service_url: str = "http://tooluniverse-service:8092"
    medea_service_url: str = "http://medea-service:8093"
    mims_timeout_seconds: float = 240.0
    tool_workflows: tuple[str, ...] = ("target_context",)
    max_chunk_chars: int = 2400
    opensearch_url: str = "http://opensearch:9200"
    opensearch_timeout_seconds: float = 30.0
    opensearch_required: bool = True
    vector_dimension: int = 384
    postgres_dsn: str = "postgresql://translume:translume@postgres:5432/translume"
    postgres_connect_timeout_seconds: float = 10.0
    postgres_required: bool = True
    docling_service_url: str = "http://docling-service:8090"
    docling_timeout_seconds: float = 240.0
    docling_required: bool = True
    docling_extraction_method: str = "docling"
    vllm_base_url: str = "http://vllm:8000/v1"
    vllm_model: str = ""
    vllm_timeout_seconds: float = 240.0
    prompts_root: Path = Path("configs/prompts")
    require_local_vllm: bool = True


def get_settings() -> Settings:
    """Return API settings from environment variables.

    Acceptance criteria:
        1. Returns a `Settings` object.
        2. Does not mutate process state.
        3. Provides strict MIMS-required default behavior unless explicitly
           disabled by `TRANSLUME_REQUIRE_MIMS=false`.
    """
    return Settings(
        storage_root=Path(os.getenv("TRANSLUME_STORAGE_ROOT", "data/uploads")),
        require_mims=os.getenv("TRANSLUME_REQUIRE_MIMS", "true").casefold() == "true",
        optimuskg_service_url=os.getenv("OPTIMUSKG_SERVICE_URL", "http://optimuskg-service:8091"),
        tooluniverse_service_url=os.getenv("TOOLUNIVERSE_SERVICE_URL", "http://tooluniverse-service:8092"),
        medea_service_url=os.getenv("MEDEA_SERVICE_URL", "http://medea-service:8093"),
        mims_timeout_seconds=float(os.getenv("MIMS_TIMEOUT_SECONDS", "240")),
        tool_workflows=_parse_csv_tuple(os.getenv("TRANSLUME_TOOL_WORKFLOWS", "target_context")),
        max_chunk_chars=int(os.getenv("TRANSLUME_MAX_CHUNK_CHARS", "2400")),
        opensearch_url=os.getenv("OPENSEARCH_URL", "http://opensearch:9200"),
        opensearch_timeout_seconds=float(os.getenv("OPENSEARCH_TIMEOUT_SECONDS", "30")),
        opensearch_required=os.getenv("TRANSLUME_REQUIRE_OPENSEARCH", "true").casefold() == "true",
        vector_dimension=int(os.getenv("TRANSLUME_VECTOR_DIMENSION", "384")),
        postgres_dsn=os.getenv("POSTGRES_DSN", "postgresql://translume:translume@postgres:5432/translume"),
        postgres_connect_timeout_seconds=float(os.getenv("POSTGRES_CONNECT_TIMEOUT_SECONDS", "10")),
        postgres_required=os.getenv("TRANSLUME_REQUIRE_POSTGRES", "true").casefold() == "true",
        docling_service_url=os.getenv("DOCLING_SERVICE_URL", "http://docling-service:8090"),
        docling_timeout_seconds=float(os.getenv("DOCLING_TIMEOUT_SECONDS", "240")),
        docling_required=os.getenv("TRANSLUME_REQUIRE_DOCLING", "true").casefold() == "true",
        docling_extraction_method=os.getenv("DOCLING_EXTRACTION_METHOD", "docling"),
        vllm_base_url=os.getenv("VLLM_BASE_URL", "http://vllm:8000/v1"),
        vllm_model=os.getenv("VLLM_MODEL", ""),
        vllm_timeout_seconds=float(os.getenv("VLLM_TIMEOUT_SECONDS", "240")),
        prompts_root=Path(os.getenv("TRANSLUME_PROMPTS_ROOT", "configs/prompts")),
        require_local_vllm=os.getenv("TRANSLUME_REQUIRE_LOCAL_VLLM", "true").casefold() == "true",
    )


def _parse_csv_tuple(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())
