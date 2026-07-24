from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, Field, model_validator


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
    tool_workflows: tuple[str, ...] = (
        "literature_validation",
        "pathway_context",
        "target_context",
        "variant_context",
        "trial_context_review",
        "therapy_context",
        "resistance_mechanism_context",
        "biomarker_retesting_context",
        "guideline_context",
        "clinical_trial_context",
        "lineage_transformation_context",
        "recent_therapy_agent_backfill_context",
    )
    max_chunk_chars: int = 2400
    opensearch_url: str = "http://opensearch:9200"
    opensearch_timeout_seconds: float = 30.0
    opensearch_required: bool = True
    retrieval_mode: str = "lexical"
    vector_dimension: int | None = None
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
    vllm_structured_output_max_tokens: int = Field(default=3000, ge=1)
    vllm_structured_output_retry_max_tokens: int = Field(default=6000, ge=1)
    vllm_model_context_tokens: int = Field(default=8192, ge=1)
    report_extraction_max_tokens: int = Field(default=2500, ge=1)
    report_extraction_retry_max_tokens: int = Field(default=5000, ge=1)
    report_extraction_input_token_budget: int = Field(default=2200, ge=1)
    report_extraction_context_safety_tokens: int = Field(default=512, ge=1)
    report_extraction_max_split_depth: int = Field(default=6, ge=0)
    report_extraction_min_segment_chars: int = Field(default=400, ge=1)
    confirmatory_testing_input_token_budget: int = Field(default=8000, ge=1)
    tumor_behavior_input_token_budget: int = Field(default=24000, ge=1)
    tumor_behavior_max_tokens: int = Field(default=6000, ge=1)
    report_extraction_batch_max_chunks: int = Field(default=5, ge=1)
    prompts_root: Path = Path("configs/prompts")
    require_local_vllm: bool = True
    enable_provider_cache: bool = True
    graph_cache_ttl_seconds: float | None = 3600.0
    tool_cache_ttl_seconds: float | None = 1800.0
    medea_cache_ttl_seconds: float | None = 1800.0
    async_stage_latency_budget_seconds: float | None = None
    decision_brief_stage_latency_budget_seconds: float | None = None
    stage_latency_budgets_seconds: dict[str, float] = Field(default_factory=dict)
    precision_oncology_service_url: str = "http://precision-oncology-pipeline:8094"
    dynamic_pathway_service_url: str = "http://dynamic-pathway-analyzer:8095"
    downstream_timeout_seconds: float = 7200.0

    @model_validator(mode="after")
    def validate_report_extraction_budget(self) -> Settings:
        """Validate that the largest extraction request fits model context."""
        if (
            self.vllm_structured_output_retry_max_tokens
            <= self.vllm_structured_output_max_tokens
        ):
            raise ValueError(
                "structured output retry max tokens must exceed initial max tokens"
            )
        if self.report_extraction_max_tokens > self.report_extraction_retry_max_tokens:
            raise ValueError(
                "report extraction initial max tokens must not exceed retry max tokens"
            )
        required = (
            self.report_extraction_input_token_budget
            + self.report_extraction_retry_max_tokens
            + self.report_extraction_context_safety_tokens
        )
        if required > self.vllm_model_context_tokens:
            raise ValueError(
                "report extraction token budgets exceed vLLM model context: "
                f"required={required}, context={self.vllm_model_context_tokens}"
            )
        return self


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
        require_mims=os.getenv("TRANSLUME_REQUIRE_MIMS", "true").casefold()
        == "true",
        optimuskg_service_url=os.getenv(
            "OPTIMUSKG_SERVICE_URL",
            "http://optimuskg-service:8091",
        ),
        tooluniverse_service_url=os.getenv(
            "TOOLUNIVERSE_SERVICE_URL",
            "http://tooluniverse-service:8092",
        ),
        medea_service_url=os.getenv(
            "MEDEA_SERVICE_URL",
            "http://medea-service:8093",
        ),
        mims_timeout_seconds=float(os.getenv("MIMS_TIMEOUT_SECONDS", "240")),
        tool_workflows=_parse_csv_tuple(
            os.getenv(
                "TRANSLUME_TOOL_WORKFLOWS",
                _default_tool_workflows_csv(),
            )
        ),
        max_chunk_chars=int(os.getenv("TRANSLUME_MAX_CHUNK_CHARS", "2400")),
        opensearch_url=os.getenv("OPENSEARCH_URL", "http://opensearch:9200"),
        opensearch_timeout_seconds=float(
            os.getenv("OPENSEARCH_TIMEOUT_SECONDS", "30")
        ),
        opensearch_required=os.getenv(
            "TRANSLUME_REQUIRE_OPENSEARCH",
            "true",
        ).casefold()
        == "true",
        retrieval_mode=os.getenv("TRANSLUME_RETRIEVAL_MODE", "lexical"),
        vector_dimension=_optional_int(os.getenv("TRANSLUME_VECTOR_DIMENSION", "")),
        postgres_dsn=os.getenv(
            "POSTGRES_DSN",
            "postgresql://translume:translume@postgres:5432/translume",
        ),
        postgres_connect_timeout_seconds=float(
            os.getenv("POSTGRES_CONNECT_TIMEOUT_SECONDS", "10")
        ),
        postgres_required=os.getenv("TRANSLUME_REQUIRE_POSTGRES", "true").casefold()
        == "true",
        docling_service_url=os.getenv(
            "DOCLING_SERVICE_URL",
            "http://docling-service:8090",
        ),
        docling_timeout_seconds=float(os.getenv("DOCLING_TIMEOUT_SECONDS", "240")),
        docling_required=os.getenv("TRANSLUME_REQUIRE_DOCLING", "true").casefold()
        == "true",
        docling_extraction_method=os.getenv("DOCLING_EXTRACTION_METHOD", "docling"),
        vllm_base_url=os.getenv("VLLM_BASE_URL", "http://vllm:8000/v1"),
        vllm_model=os.getenv("VLLM_MODEL", ""),
        vllm_timeout_seconds=float(os.getenv("VLLM_TIMEOUT_SECONDS", "240")),
        vllm_structured_output_max_tokens=int(
            os.getenv("VLLM_STRUCTURED_OUTPUT_MAX_TOKENS", "3000")
        ),
        vllm_structured_output_retry_max_tokens=int(
            os.getenv("VLLM_STRUCTURED_OUTPUT_RETRY_MAX_TOKENS", "6000")
        ),
        vllm_model_context_tokens=int(
            os.getenv("VLLM_MODEL_CONTEXT_TOKENS", "8192")
        ),
        report_extraction_max_tokens=int(
            os.getenv(
                "REPORT_EXTRACTION_INITIAL_MAX_TOKENS",
                os.getenv("REPORT_EXTRACTION_MAX_TOKENS", "2500"),
            )
        ),
        report_extraction_retry_max_tokens=int(
            os.getenv("REPORT_EXTRACTION_RETRY_MAX_TOKENS", "5000")
        ),
        report_extraction_input_token_budget=int(
            os.getenv("REPORT_EXTRACTION_INPUT_TOKEN_BUDGET", "2200")
        ),
        report_extraction_context_safety_tokens=int(
            os.getenv("REPORT_EXTRACTION_CONTEXT_SAFETY_TOKENS", "512")
        ),
        report_extraction_max_split_depth=int(
            os.getenv("REPORT_EXTRACTION_MAX_SPLIT_DEPTH", "6")
        ),
        report_extraction_min_segment_chars=int(
            os.getenv("REPORT_EXTRACTION_MIN_SEGMENT_CHARS", "400")
        ),
        confirmatory_testing_input_token_budget=int(
            os.getenv("CONFIRMATORY_TESTING_INPUT_TOKEN_BUDGET", "8000")
        ),
        tumor_behavior_input_token_budget=int(
            os.getenv("TUMOR_BEHAVIOR_INPUT_TOKEN_BUDGET", "24000")
        ),
        tumor_behavior_max_tokens=int(
            os.getenv("VLLM_TUMOR_BEHAVIOR_MAX_TOKENS", "6000")
        ),
        report_extraction_batch_max_chunks=int(
            os.getenv("REPORT_EXTRACTION_BATCH_MAX_CHUNKS", "5")
        ),
        prompts_root=Path(os.getenv("TRANSLUME_PROMPTS_ROOT", "configs/prompts")),
        require_local_vllm=os.getenv(
            "TRANSLUME_REQUIRE_LOCAL_VLLM",
            "true",
        ).casefold()
        == "true",
        enable_provider_cache=os.getenv(
            "TRANSLUME_ENABLE_PROVIDER_CACHE",
            "true",
        ).casefold()
        == "true",
        graph_cache_ttl_seconds=_optional_float(
            os.getenv("TRANSLUME_GRAPH_CACHE_TTL_SECONDS", "3600")
        ),
        tool_cache_ttl_seconds=_optional_float(
            os.getenv("TRANSLUME_TOOL_CACHE_TTL_SECONDS", "1800")
        ),
        medea_cache_ttl_seconds=_optional_float(
            os.getenv("TRANSLUME_MEDEA_CACHE_TTL_SECONDS", "1800")
        ),
        async_stage_latency_budget_seconds=_optional_float(
            os.getenv("TRANSLUME_ASYNC_STAGE_LATENCY_BUDGET_SECONDS", "")
        ),
        decision_brief_stage_latency_budget_seconds=_optional_float(
            os.getenv("TRANSLUME_DECISION_BRIEF_STAGE_LATENCY_BUDGET_SECONDS", "")
        ),
        stage_latency_budgets_seconds=_parse_latency_budget_map(
            os.getenv("TRANSLUME_STAGE_LATENCY_BUDGETS_SECONDS", "")
        ),
        precision_oncology_service_url=os.getenv(
            "PRECISION_ONCOLOGY_SERVICE_URL",
            "http://precision-oncology-pipeline:8094",
        ),
        dynamic_pathway_service_url=os.getenv(
            "DYNAMIC_PATHWAY_SERVICE_URL",
            "http://dynamic-pathway-analyzer:8095",
        ),
        downstream_timeout_seconds=float(
            os.getenv("TRANSLUME_DOWNSTREAM_TIMEOUT_SECONDS", "7200")
        ),
    )


def _default_tool_workflows_csv() -> str:
    return ",".join(Settings().tool_workflows)

def _parse_csv_tuple(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _optional_int(value: str) -> int | None:
    stripped = value.strip()
    return int(stripped) if stripped else None


def _optional_float(value: str) -> float | None:
    stripped = value.strip()
    return float(stripped) if stripped else None


def _parse_latency_budget_map(value: str) -> dict[str, float]:
    budgets: dict[str, float] = {}
    for item in value.split(","):
        if not item.strip():
            continue
        if "=" not in item:
            raise ValueError(
                "TRANSLUME_STAGE_LATENCY_BUDGETS_SECONDS entries must be stage=seconds"
            )
        stage, seconds = item.split("=", 1)
        stage = stage.strip()
        if not stage:
            raise ValueError(
                "TRANSLUME_STAGE_LATENCY_BUDGETS_SECONDS contains an empty stage name"
            )
        budgets[stage] = float(seconds.strip())
    return budgets
