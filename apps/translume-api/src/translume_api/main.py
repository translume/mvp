from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
import os

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from translume_api.config import Settings, get_settings
from translume_clients.docling import DoclingClientConfig, DoclingServiceClient
from translume_clients.downstream import (
    DownstreamRunnerConfig,
    DynamicPathwayRunnerClient,
    PrecisionOncologyRunnerClient,
)
from translume_adapters.model_providers.local_vllm_provider import LocalVLLMProvider
from translume_clients.local_vllm import LocalVLLMClient
from translume_clients.mims import (
    MedeaServiceClient,
    MimsServiceClientConfig,
    OptimusKGServiceClient,
    ToolUniverseServiceClient,
)
from translume_clients.opensearch import OpenSearchClientConfig, OpenSearchVectorStore
from translume_clients.postgres import PostgresClientConfig, PostgresLedgerStore
from translume_core.indexing.persistence import persist_review_packet_to_opensearch
from translume_core.validation.review import (
    apply_validation_decision_to_packet,
    build_validation_decision,
    validation_cards_from_packet,
)
from translume_core.prime_directives import (
    PrimeDirectiveViolation,
    assert_prime_directives,
    find_project_root,
)
from translume_core.workflow import (
    TranslumeWorkflowConfig,
    TranslumeWorkflowProviders,
    process_report_pdf,
)
from translume_schemas.downstream import (
    DownstreamAnalysisRequest,
    DownstreamAnalysisResult,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Run production/demo PRIME_DIRECTIVES gate at API startup.

    Acceptance criteria:
        1. Local development mode can start without production dependencies.
        2. Production/demo/enforced mode fails before accepting requests if
           required real services, vendor Git clones, or local-model routing are
           missing.
        3. The gate does not fabricate readiness or silently downgrade missing
           dependencies.
    """
    root = find_project_root(Path(__file__))
    try:
        assert_prime_directives(environment=os.environ, root=root, force=False)
    except PrimeDirectiveViolation as error:
        raise RuntimeError(str(error)) from error
    yield


app = FastAPI(title="Translume API", lifespan=lifespan)


class ValidationDecisionRequest(BaseModel):
    """Request body for claim validation."""

    status: Literal["validated", "rejected", "needs_review"]
    reviewer_id: str | None = None
    reviewer_note: str | None = None


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "translume-api"}


@app.post("/api/v1/reports/process")
async def process_report(
    file: UploadFile = File(...),
    report_type: str = Form("NGS"),
) -> dict[str, object]:
    """Process one oncology PDF into a review packet.

    Acceptance criteria:
        1. Accepts one PDF upload.
        2. Runs the production workflow.
        3. Returns a JSON-serializable review packet.
        4. Provider failures return explicit HTTP errors.
        5. No mock data is inserted by the API layer.
    """
    settings = get_settings()
    content = await file.read()
    try:
        packet = await process_report_pdf(
            filename=file.filename or "uploaded.pdf",
            content=content,
            report_type=report_type,
            config=_workflow_config(settings),
            providers=_workflow_providers(settings),
        )
    except Exception as error:
        raise HTTPException(status_code=422, detail=_http_error_detail(error)) from error
    return packet.model_dump(mode="json")


@app.get("/api/v1/review-packets/{session_id}/validation-cards")
async def get_validation_cards(session_id: str) -> dict[str, object]:
    """Return claim cards that require human validation.

    Acceptance criteria:
        1. Loads the persisted review packet from Postgres.
        2. Returns only real claim cards from the stored packet.
        3. Does not fabricate validation cards.
        4. Provider failures return explicit HTTP errors.
    """
    store = _postgres_store(get_settings())
    try:
        packet = await store.fetch_review_packet_by_session_id(session_id)
    except Exception as error:
        raise HTTPException(status_code=404, detail=_http_error_detail(error)) from error
    cards = validation_cards_from_packet(packet)
    return {
        "case_id": packet.case_id,
        "session_id": packet.session_id,
        "claims": [card.model_dump(mode="json") for card in cards],
    }


@app.get("/api/v1/review-packets/{session_id}/export")
async def get_review_packet_export(session_id: str) -> dict[str, object]:
    """Return the persisted review packet export for a session.

    Acceptance criteria:
        1. Loads the review packet from Postgres.
        2. Returns the exact stored packet payload.
        3. Does not reconstruct or fabricate a packet from partial data.
    """
    store = _postgres_store(get_settings())
    try:
        packet = await store.fetch_review_packet_by_session_id(session_id)
    except Exception as error:
        raise HTTPException(status_code=404, detail=_http_error_detail(error)) from error
    return packet.model_dump(mode="json")


@app.post(
    "/api/v1/review-packets/{session_id}/downstream-analysis",
    response_model=DownstreamAnalysisResult,
)
async def run_downstream_analysis(
    session_id: str,
    request: DownstreamAnalysisRequest,
) -> DownstreamAnalysisResult:
    """Run verified downstream analysis for one persisted review packet.

    Acceptance criteria:
        1. Persistence: Loads the exact review packet from Postgres.
        2. Sequencing: Runs precision oncology before pathway analysis.
        3. Validation: Returns schema-valid, verified Markdown artifacts only.
        4. Isolation: Delegates filesystem and subprocess work to runner services.
    """
    diagnosis = request.diagnosis.strip()
    if not diagnosis:
        raise HTTPException(status_code=422, detail="Diagnosis is required.")
    settings = get_settings()
    try:
        packet = await _postgres_store(settings).fetch_review_packet_by_session_id(
            session_id
        )
        config = DownstreamRunnerConfig(
            base_url=settings.precision_oncology_service_url,
            timeout_seconds=settings.downstream_timeout_seconds,
        )
        precision_run = await PrecisionOncologyRunnerClient(config).run(
            session_id=packet.session_id,
            review_packet=packet.model_dump(mode="json"),
        )
        dynamic_config = DownstreamRunnerConfig(
            base_url=settings.dynamic_pathway_service_url,
            timeout_seconds=settings.downstream_timeout_seconds,
        )
        return await DynamicPathwayRunnerClient(dynamic_config).run(
            session_id=packet.session_id,
            precision_run=precision_run,
            diagnosis=diagnosis,
        )
    except Exception as error:
        raise HTTPException(status_code=422, detail=_http_error_detail(error)) from error




@app.get("/api/v1/review-packets/{session_id}/decision-brief")
async def get_oncologist_decision_brief(session_id: str) -> dict[str, object]:
    """Return only the persisted oncologist decision brief for a session.

    Acceptance criteria:
        1. Loads the exact persisted review packet from Postgres.
        2. Returns the stored decision_brief artifact only.
        3. Does not reconstruct or fabricate decision-brief content.
        4. Fails explicitly when the persisted packet has no decision brief.
    """
    store = _postgres_store(get_settings())
    try:
        packet = await store.fetch_review_packet_by_session_id(session_id)
    except Exception as error:
        raise HTTPException(status_code=404, detail=_http_error_detail(error)) from error
    if packet.bundle.decision_brief is None:
        raise HTTPException(
            status_code=404,
            detail="Persisted packet does not contain an oncologist decision brief",
        )
    return packet.bundle.decision_brief.model_dump(mode="json")


@app.post("/api/v1/review-packets/{session_id}/claims/{claim_id}/validation")
async def validate_claim(
    session_id: str,
    claim_id: str,
    request: ValidationDecisionRequest,
) -> dict[str, object]:
    """Persist a human validation decision for one claim.

    Acceptance criteria:
        1. Loads the real persisted review packet from Postgres.
        2. Requires the target claim to exist.
        3. Applies the decision to the claim status.
        4. Persists the updated packet to Postgres.
        5. Re-indexes the updated packet to OpenSearch.
        6. Returns updated claim cards and the validation decision.
        7. Does not fabricate claims, decisions, or ledger events.
    """
    settings = get_settings()
    postgres = _postgres_store(settings)
    vector_store = _opensearch_store(settings)
    now = datetime.now(timezone.utc)
    try:
        packet = await postgres.fetch_review_packet_by_session_id(session_id)
        decision = build_validation_decision(
            claim_id=claim_id,
            status=request.status,
            reviewer_id=request.reviewer_id,
            reviewer_note=request.reviewer_note,
            created_at=now,
        )
        updated_packet = apply_validation_decision_to_packet(
            packet,
            decision,
            created_at=now,
        )
        await postgres.persist_review_packet(updated_packet)
        await persist_review_packet_to_opensearch(
            updated_packet,
            vector_store,
            retrieval_mode=settings.retrieval_mode,
            vector_dimension=settings.vector_dimension,
        )
    except Exception as error:
        raise HTTPException(status_code=422, detail=_http_error_detail(error)) from error
    return {
        "case_id": updated_packet.case_id,
        "session_id": updated_packet.session_id,
        "decision": decision.model_dump(mode="json"),
        "claims": [
            claim.model_dump(mode="json")
            for claim in validation_cards_from_packet(updated_packet)
        ],
    }


def _workflow_config(settings: Settings) -> TranslumeWorkflowConfig:
    return TranslumeWorkflowConfig(
        storage_root=settings.storage_root,
        max_chunk_chars=settings.max_chunk_chars,
        require_mims=settings.require_mims,
        require_opensearch=settings.opensearch_required,
        retrieval_mode=settings.retrieval_mode,
        vector_dimension=settings.vector_dimension,
        require_postgres=settings.postgres_required,
        require_docling=settings.docling_required,
        require_local_vllm=settings.require_local_vllm,
        vllm_model=settings.vllm_model,
        prompts_root=settings.prompts_root,
        report_extraction_batch_max_chunks=(
            settings.report_extraction_batch_max_chunks
        ),
        report_extraction_input_token_budget=(
            settings.report_extraction_input_token_budget
        ),
        report_extraction_initial_max_tokens=settings.report_extraction_max_tokens,
        report_extraction_retry_max_tokens=(
            settings.report_extraction_retry_max_tokens
        ),
        report_extraction_max_split_depth=(
            settings.report_extraction_max_split_depth
        ),
        report_extraction_min_segment_chars=(
            settings.report_extraction_min_segment_chars
        ),
        confirmatory_testing_input_token_budget=(
            settings.confirmatory_testing_input_token_budget
        ),
        tool_workflows=settings.tool_workflows,
        enable_provider_cache=settings.enable_provider_cache,
        graph_cache_ttl_seconds=settings.graph_cache_ttl_seconds,
        tool_cache_ttl_seconds=settings.tool_cache_ttl_seconds,
        medea_cache_ttl_seconds=settings.medea_cache_ttl_seconds,
        async_stage_latency_budget_seconds=(
            settings.async_stage_latency_budget_seconds
        ),
        decision_brief_stage_latency_budget_seconds=(
            settings.decision_brief_stage_latency_budget_seconds
        ),
        stage_latency_budgets_seconds=settings.stage_latency_budgets_seconds,
    )


def _http_error_detail(error: Exception) -> str:
    """Return a non-empty HTTP error detail for API exception boundaries.

    Acceptance criteria:
        1. Determinism: Same exception type and message return the same detail.
        2. No mutation: Do not mutate the exception.
        3. Observability: Include the exception type when the message is blank.
        4. Safety: Preserve existing explicit error messages unchanged.

    Args:
        error: Exception caught by an API boundary.

    Returns:
        Non-empty detail string for `HTTPException`.
    """
    message = str(error).strip()
    if message:
        return message
    return f"{type(error).__name__}: no error message"


def _workflow_providers(settings: Settings) -> TranslumeWorkflowProviders:
    return TranslumeWorkflowProviders(
        graph_provider=OptimusKGServiceClient(
            MimsServiceClientConfig(
                base_url=settings.optimuskg_service_url,
                timeout_seconds=settings.mims_timeout_seconds,
            )
        ),
        tool_provider=ToolUniverseServiceClient(
            MimsServiceClientConfig(
                base_url=settings.tooluniverse_service_url,
                timeout_seconds=settings.mims_timeout_seconds,
            )
        ),
        reasoning_provider_factory=lambda _context: MedeaServiceClient(
            MimsServiceClientConfig(
                base_url=settings.medea_service_url,
                timeout_seconds=settings.mims_timeout_seconds,
            )
        ),
        vector_store=_opensearch_store(settings),
        ledger_store=_postgres_store(settings),
        document_extractor=DoclingServiceClient(
            DoclingClientConfig(
                base_url=settings.docling_service_url,
                timeout_seconds=settings.docling_timeout_seconds,
                extraction_method=settings.docling_extraction_method,
            )
        ),
        model_provider=LocalVLLMProvider(
            LocalVLLMClient(
                base_url=settings.vllm_base_url,
                timeout_seconds=settings.vllm_timeout_seconds,
            ),
            structured_output_max_tokens=(
                settings.vllm_structured_output_max_tokens
            ),
            structured_output_retry_max_tokens=(
                settings.vllm_structured_output_retry_max_tokens
            ),
            report_extraction_max_tokens=settings.report_extraction_max_tokens,
            tumor_behavior_max_tokens=settings.tumor_behavior_max_tokens,
        ),
    )


def _postgres_store(settings: Settings) -> PostgresLedgerStore:
    return PostgresLedgerStore(
        PostgresClientConfig(
            dsn=settings.postgres_dsn,
            connect_timeout_seconds=settings.postgres_connect_timeout_seconds,
        )
    )


def _opensearch_store(settings: Settings) -> OpenSearchVectorStore:
    return OpenSearchVectorStore(
        OpenSearchClientConfig(
            base_url=settings.opensearch_url,
            timeout_seconds=settings.opensearch_timeout_seconds,
        )
    )
