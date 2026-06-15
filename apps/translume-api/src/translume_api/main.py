from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from translume_api.config import Settings, get_settings
from translume_clients.docling import DoclingClientConfig, DoclingServiceClient
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
from translume_core.workflow import (
    TranslumeWorkflowConfig,
    TranslumeWorkflowProviders,
    process_report_pdf,
)

app = FastAPI(title="Translume API")


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
        raise HTTPException(status_code=422, detail=str(error)) from error
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
        raise HTTPException(status_code=404, detail=str(error)) from error
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
        raise HTTPException(status_code=404, detail=str(error)) from error
    return packet.model_dump(mode="json")


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
            vector_dimension=settings.vector_dimension,
        )
    except Exception as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
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
        vector_dimension=settings.vector_dimension,
        require_postgres=settings.postgres_required,
        require_docling=settings.docling_required,
        tool_workflows=settings.tool_workflows,
    )


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
