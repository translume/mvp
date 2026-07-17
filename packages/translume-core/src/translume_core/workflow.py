from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from translume_core.compiler.decision_brief import (
    DecisionBriefLatencyBudgets,
    generate_oncologist_decision_brief_with_model,
)
from translume_core.compiler.entity_normalization import normalize_report_entities
from translume_core.compiler.evidence_context import combine_evidence_sources
from translume_core.compiler.structured_model_artifacts import (
    generate_claim_evidence_with_model,
    generate_clinical_narrative_with_model,
    generate_confirmatory_testing_with_model,
    generate_mechanism_sankey_with_model,
    generate_molecular_fit_matrix_with_model,
    generate_molecular_phenotype_with_model,
    generate_report_extraction_with_model,
    generate_tumor_behavior_model_with_model,
)
from translume_core.document.chunks import build_document_chunks, merge_small_adjacent_chunks
from translume_core.document.pymupdf_adapter import extract_document_with_pymupdf
from translume_core.document.quality import score_extraction_quality, select_best_document_extraction
from translume_core.document.sections import detect_section_headers
from translume_core.export.review_packet import build_review_packet_export
from translume_core.ingestion.ledger_events import record_upload_ledger_event
from translume_core.ingestion.sessions import create_case_session
from translume_core.ingestion.storage import persist_uploaded_pdf
from translume_core.indexing.documents import review_packet_to_index_batches
from translume_core.indexing.retrieval import (
    index_document_chunks_for_retrieval,
    retrieve_indexed_document_chunks,
)
from translume_core.indexing.persistence import persist_review_packet_to_opensearch
from translume_core.persistence.ledger_events import persistence_ledger_event
from translume_core.persistence.postgres_persistence import append_ledger_event_to_postgres, persist_ingestion_metadata_to_postgres, persist_review_packet_to_postgres
from translume_core.persistence.postgres_records import review_packet_to_postgres_records
from translume_core.provenance.coverage import (
    provenance_for_claim,
    provenance_for_evidence_context,
    provenance_for_graph_evidence,
    provenance_for_medea_reasoning,
    provenance_for_normalized_entities,
    provenance_for_tool_output,
    require_bundle_provenance_complete,
)
from translume_core.provenance.provenance import build_artifact_provenance
from translume_core.performance import (
    AsyncInMemoryCache,
    run_with_latency_budget,
    stable_cache_key,
)
from translume_core.safety.containment import require_narrative_fact_containment
from translume_schemas.document import DocumentChunk
from translume_schemas.evidence import EvidenceContextBundle
from translume_schemas.export import ClinicalArtifactBundle, NarrativeContainmentReport, ReviewPacketExport
from translume_schemas.graph import GraphEvidenceArtifact, GraphRetrievalMode
from translume_schemas.ledger import LedgerEvent
from translume_schemas.medea import MedeaReasoningArtifact
from translume_schemas.provenance import ArtifactProvenance
from translume_schemas.tools import ToolRunArtifact


_DEFAULT_PROVIDER_CACHE = AsyncInMemoryCache()


def _workflow_cache(
    providers: TranslumeWorkflowProviders,
    config: TranslumeWorkflowConfig,
) -> AsyncInMemoryCache | None:
    if not config.enable_provider_cache:
        return None
    return providers.performance_cache or _DEFAULT_PROVIDER_CACHE


def _workflow_stage_latency_budget(
    config: TranslumeWorkflowConfig,
    stage_name: str,
) -> float | None:
    if stage_name in config.stage_latency_budgets_seconds:
        return config.stage_latency_budgets_seconds[stage_name]
    return config.async_stage_latency_budget_seconds


def _decision_brief_latency_budgets(
    config: TranslumeWorkflowConfig,
) -> DecisionBriefLatencyBudgets:
    return DecisionBriefLatencyBudgets(
        default_timeout_seconds=config.decision_brief_stage_latency_budget_seconds,
        stage_timeout_seconds=config.stage_latency_budgets_seconds,
    )


@dataclass(frozen=True)
class TranslumeWorkflowProviders:
    """External enrichment providers for the workflow.

    Attributes:
        graph_provider: Object with async `retrieve_context(entities)`.
        tool_provider: Object with async `run_workflows(...)`.
        reasoning_provider_factory: Factory that receives preliminary context
            and returns an object with async `reason_over_context(context)`.
        vector_store: Optional OpenSearch-compatible persistence boundary.
        ledger_store: Optional Postgres-compatible metadata boundary.
        document_extractor: Optional Docling-compatible extractor boundary.
        model_provider: Required local structured-output model provider.
    """

    graph_provider: object | None = None
    tool_provider: object | None = None
    reasoning_provider_factory: object | None = None
    vector_store: object | None = None
    ledger_store: object | None = None
    document_extractor: object | None = None
    model_provider: object | None = None
    performance_cache: AsyncInMemoryCache | None = None


@dataclass(frozen=True)
class TranslumeWorkflowConfig:
    """Workflow configuration.

    Attributes:
        storage_root: Root for raw uploads and artifacts.
        max_chunk_chars: Maximum merged chunk size.
        require_mims: Whether graph/tool/Medea providers are required.
        tool_workflows: Allow-listed ToolUniverse workflow names to run.
        graph_retrieval_modes: Targeted OptimusKG retrieval modes for therapy,
            resistance, drug-target-biomarker, and monitoring context.
        require_opensearch: Whether OpenSearch persistence is mandatory.
        require_postgres: Whether Postgres metadata persistence is mandatory.
        retrieval_mode: OpenSearch retrieval scope. The MVP supports lexical only.
        vector_dimension: Reserved for a future real embedding provider.
        require_docling: Whether Docling layout extraction must run.
        require_local_vllm: Whether local vLLM structured outputs are required.
        vllm_model: Model identifier served by local vLLM.
        prompts_root: Directory containing structured-output prompt files.
        report_extraction_batch_max_chunks: Maximum source chunks per
            page-ordered report-extraction request.
    """

    storage_root: Path
    max_chunk_chars: int = 2400
    require_mims: bool = True
    require_opensearch: bool = True
    require_postgres: bool = True
    retrieval_mode: str = "lexical"
    vector_dimension: int | None = None
    require_docling: bool = True
    require_local_vllm: bool = True
    vllm_model: str = ""
    prompts_root: Path = Path("configs/prompts")
    report_extraction_batch_max_chunks: int = 5
    report_extraction_input_token_budget: int = 2200
    report_extraction_initial_max_tokens: int = 2500
    report_extraction_retry_max_tokens: int = 5000
    report_extraction_max_split_depth: int = 6
    report_extraction_min_segment_chars: int = 400
    confirmatory_testing_input_token_budget: int = 8000
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
    graph_retrieval_modes: tuple[GraphRetrievalMode, ...] = (
        "general_context",
        "therapy_pressure",
        "resistance_path",
        "drug_target_biomarker",
        "biomarker_monitoring",
    )
    enable_provider_cache: bool = True
    graph_cache_ttl_seconds: float | None = 3600.0
    tool_cache_ttl_seconds: float | None = 1800.0
    medea_cache_ttl_seconds: float | None = 1800.0
    async_stage_latency_budget_seconds: float | None = None
    decision_brief_stage_latency_budget_seconds: float | None = None
    stage_latency_budgets_seconds: dict[str, float] = field(default_factory=dict)


async def process_report_pdf(
    *,
    filename: str,
    content: bytes,
    report_type: str,
    config: TranslumeWorkflowConfig,
    providers: TranslumeWorkflowProviders,
    created_at: datetime | None = None,
) -> ReviewPacketExport:
    """Run the end-to-end Translume MVP report workflow.

    Acceptance criteria:
        1. Raw upload, session metadata, source-file metadata, and upload
           ledger event are durably persisted before clinical processing.
        2. Every major workflow stage records started/succeeded/failed ledger
           events as it executes.
        3. Stage failures are persisted when a ledger store is configured and
           are never hidden behind a partial review packet.
        4. PDF upload creates source-backed chunks.
        5. Report extraction produces source-backed findings.
        6. MIMS providers run in strict mode or fail explicitly.
        7. OpenSearch and Postgres are required by default and fail loudly when
           unavailable.
        8. Produces evidence-grounded oncologist decision support while
           rejecting unsupported certainty, cure, survival, or deterministic
           outcome claims.

    Args:
        filename: Original uploaded filename.
        content: Raw PDF bytes.
        report_type: User-selected report type.
        config: Workflow configuration.
        providers: External graph/tool/reasoning providers.
        created_at: Optional explicit timestamp.

    Returns:
        Review packet export.
    """
    now = created_at or datetime.now(timezone.utc)
    session = create_case_session(report_type, "research_support_only", now)
    stored_file = persist_uploaded_pdf(session, filename, content, config.storage_root)
    upload_event = record_upload_ledger_event(session, stored_file, now)
    ledger_events: list[LedgerEvent] = [upload_event]
    await _persist_ingestion_metadata_before_processing(
        session=session,
        stored_file=stored_file,
        upload_event=upload_event,
        providers=providers,
        config=config,
    )

    try:
        extraction_output = await _run_sync_workflow_stage(
            "document_extraction",
            ledger_events,
            session,
            stored_file,
            now,
            providers,
            config,
            lambda: _extract_best_document(stored_file, providers, config),
        )
        sections = await _run_sync_workflow_stage(
            "section_detection",
            ledger_events,
            session,
            stored_file,
            now,
            providers,
            config,
            lambda: detect_section_headers(extraction_output),
        )
        chunks = await _run_sync_workflow_stage(
            "document_chunking",
            ledger_events,
            session,
            stored_file,
            now,
            providers,
            config,
            lambda: merge_small_adjacent_chunks(
                build_document_chunks(extraction_output, sections, session, stored_file),
                max_chars=config.max_chunk_chars,
            ),
        )
        await _run_async_workflow_stage(
            "document_chunk_opensearch_indexing",
            ledger_events,
            session,
            stored_file,
            now,
            providers,
            config,
            lambda: _index_document_chunks_before_artifact_generation(
                chunks,
                providers,
                config,
            ),
        )
        retrieved_chunks = await _run_async_workflow_stage(
            "report_extraction_chunk_retrieval",
            ledger_events,
            session,
            stored_file,
            now,
            providers,
            config,
            lambda: _retrieve_chunks_for_report_extraction(
                chunks,
                providers,
                config,
            ),
        )
        report_result = await _run_async_workflow_stage(
            "report_extraction",
            ledger_events,
            session,
            stored_file,
            now,
            providers,
            config,
            lambda: generate_report_extraction_with_model(
                retrieved_chunks=retrieved_chunks,
                report_type=session.report_type,
                source_file_id=stored_file.source_file_id,
                model_provider=_require_model_provider(providers, config),
                model_name=_require_vllm_model(config),
                prompts_root=config.prompts_root,
                created_at=now,
                batch_max_chunks=config.report_extraction_batch_max_chunks,
                input_token_budget=config.report_extraction_input_token_budget,
                initial_max_tokens=config.report_extraction_initial_max_tokens,
                retry_max_tokens=config.report_extraction_retry_max_tokens,
                max_split_depth=config.report_extraction_max_split_depth,
                min_segment_chars=config.report_extraction_min_segment_chars,
            ),
        )
        report = report_result.artifact
        model_provenance: list[ArtifactProvenance] = [report_result.provenance]
        entities = await _run_sync_workflow_stage(
            "entity_normalization",
            ledger_events,
            session,
            stored_file,
            now,
            providers,
            config,
            lambda: normalize_report_entities(
                report,
                case_id=session.case_id,
                session_id=session.session_id,
            ),
        )
        model_provenance.append(
            provenance_for_normalized_entities(entities, report, created_at=now)
        )
        graph = await _run_async_workflow_stage(
            "optimuskg_graph_context",
            ledger_events,
            session,
            stored_file,
            now,
            providers,
            config,
            lambda: _get_graph_evidence(entities, providers, config),
        )
        model_provenance.append(
            provenance_for_graph_evidence(graph, entities, report, created_at=now)
        )
        await _run_sync_workflow_stage(
            "preliminary_evidence_context",
            ledger_events,
            session,
            stored_file,
            now,
            providers,
            config,
            lambda: combine_evidence_sources(
                report,
                graph,
                [],
                _empty_medea_reasoning(report.artifact_id),
            ),
        )
        tools = await _run_async_workflow_stage(
            "tooluniverse_evidence_workflows",
            ledger_events,
            session,
            stored_file,
            now,
            providers,
            config,
            lambda: _get_tool_outputs(entities, graph, providers, config),
        )
        model_provenance.extend(
            provenance_for_tool_output(tool, entities, graph, report, created_at=now)
            for tool in tools
        )
        context_without_medea = await _run_sync_workflow_stage(
            "tool_evidence_context",
            ledger_events,
            session,
            stored_file,
            now,
            providers,
            config,
            lambda: combine_evidence_sources(
                report,
                graph,
                tools,
                _empty_medea_reasoning(report.artifact_id),
            ),
        )
        medea = await _run_async_workflow_stage(
            "medea_bounded_reasoning",
            ledger_events,
            session,
            stored_file,
            now,
            providers,
            config,
            lambda: _get_medea_reasoning(context_without_medea, providers, config),
        )
        model_provenance.append(
            provenance_for_medea_reasoning(medea, context_without_medea, created_at=now)
        )
        context = await _run_sync_workflow_stage(
            "evidence_context",
            ledger_events,
            session,
            stored_file,
            now,
            providers,
            config,
            lambda: combine_evidence_sources(report, graph, tools, medea),
        )
        model_provenance.append(provenance_for_evidence_context(context, created_at=now))
        phenotype_result = await _run_async_workflow_stage(
            "molecular_phenotype",
            ledger_events,
            session,
            stored_file,
            now,
            providers,
            config,
            lambda: generate_molecular_phenotype_with_model(
                context=context,
                model_provider=_require_model_provider(providers, config),
                model_name=_require_vllm_model(config),
                prompts_root=config.prompts_root,
                created_at=now,
            ),
        )
        phenotype = phenotype_result.artifact
        model_provenance.append(phenotype_result.provenance)
        matrix_result = await _run_async_workflow_stage(
            "molecular_fit_matrix",
            ledger_events,
            session,
            stored_file,
            now,
            providers,
            config,
            lambda: generate_molecular_fit_matrix_with_model(
                context=context,
                phenotype=phenotype,
                model_provider=_require_model_provider(providers, config),
                model_name=_require_vllm_model(config),
                prompts_root=config.prompts_root,
                created_at=now,
            ),
        )
        matrix = matrix_result.artifact
        model_provenance.append(matrix_result.provenance)
        sankey_result = await _run_async_workflow_stage(
            "mechanism_sankey",
            ledger_events,
            session,
            stored_file,
            now,
            providers,
            config,
            lambda: generate_mechanism_sankey_with_model(
                context=context,
                phenotype=phenotype,
                matrix=matrix,
                model_provider=_require_model_provider(providers, config),
                model_name=_require_vllm_model(config),
                prompts_root=config.prompts_root,
                created_at=now,
            ),
        )
        sankey = sankey_result.artifact
        model_provenance.append(sankey_result.provenance)
        confirmatory_result = await _run_async_workflow_stage(
            "confirmatory_testing",
            ledger_events,
            session,
            stored_file,
            now,
            providers,
            config,
            lambda: generate_confirmatory_testing_with_model(
                context=context,
                phenotype=phenotype,
                matrix=matrix,
                sankey=sankey,
                model_provider=_require_model_provider(providers, config),
                model_name=_require_vllm_model(config),
                prompts_root=config.prompts_root,
                created_at=now,
                input_token_budget=(
                    config.confirmatory_testing_input_token_budget
                ),
            ),
        )
        confirmatory = confirmatory_result.artifact
        model_provenance.append(confirmatory_result.provenance)
        tumor_behavior_result = await _run_async_workflow_stage(
            "tumor_behavior_model",
            ledger_events,
            session,
            stored_file,
            now,
            providers,
            config,
            lambda: generate_tumor_behavior_model_with_model(
                context=context,
                phenotype=phenotype,
                matrix=matrix,
                sankey=sankey,
                confirmatory=confirmatory,
                model_provider=_require_model_provider(providers, config),
                model_name=_require_vllm_model(config),
                prompts_root=config.prompts_root,
                created_at=now,
            ),
        )
        tumor_behavior = tumor_behavior_result.artifact
        model_provenance.append(tumor_behavior_result.provenance)
        decision_brief_result, claims_result = await asyncio.gather(
            _run_async_workflow_stage(
                "oncologist_decision_brief",
                ledger_events,
                session,
                stored_file,
                now,
                providers,
                config,
                lambda: generate_oncologist_decision_brief_with_model(
                    context=context,
                    phenotype=phenotype,
                    matrix=matrix,
                    sankey=sankey,
                    confirmatory=confirmatory,
                    tumor_behavior=tumor_behavior,
                    model_provider=_require_model_provider(providers, config),
                    model_name=_require_vllm_model(config),
                    prompts_root=config.prompts_root,
                    created_at=now,
                    latency_budgets=_decision_brief_latency_budgets(config),
                ),
            ),
            _run_async_workflow_stage(
                "claim_evidence",
                ledger_events,
                session,
                stored_file,
                now,
                providers,
                config,
                lambda: generate_claim_evidence_with_model(
                    context=context,
                    phenotype=phenotype,
                    matrix=matrix,
                    sankey=sankey,
                    confirmatory=confirmatory,
                    tumor_behavior=tumor_behavior,
                    model_provider=_require_model_provider(providers, config),
                    model_name=_require_vllm_model(config),
                    prompts_root=config.prompts_root,
                    created_at=now,
                ),
            ),
        )
        decision_brief = decision_brief_result.artifact
        model_provenance.append(decision_brief_result.provenance)
        claims = claims_result.artifact.claims
        model_provenance.extend(
            provenance_for_claim(claim, report, created_at=now) for claim in claims
        )
        provenance = await _run_sync_workflow_stage(
            "artifact_provenance",
            ledger_events,
            session,
            stored_file,
            now,
            providers,
            config,
            lambda: list(model_provenance),
        )
        bundle = ClinicalArtifactBundle(
            case_id=session.case_id,
            session_id=session.session_id,
            extraction=report,
            entities=entities,
            evidence_context=context,
            phenotype=phenotype,
            matrix=matrix,
            sankey=sankey,
            confirmatory=confirmatory,
            tumor_behavior=tumor_behavior,
            decision_brief=decision_brief,
            claims=claims,
            provenance=provenance,
            ledger_events=list(ledger_events),
        )
        narrative_result = await _run_async_workflow_stage(
            "clinical_narrative",
            ledger_events,
            session,
            stored_file,
            now,
            providers,
            config,
            lambda: generate_clinical_narrative_with_model(
                bundle=bundle,
                model_provider=_require_model_provider(providers, config),
                model_name=_require_vllm_model(config),
                prompts_root=config.prompts_root,
                created_at=now,
            ),
        )
        narrative = narrative_result.artifact
        containment_report = await _run_sync_workflow_stage(
            "narrative_fact_containment",
            ledger_events,
            session,
            stored_file,
            now,
            providers,
            config,
            lambda: require_narrative_fact_containment(narrative, bundle),
        )
        containment_provenance = _narrative_containment_provenance(
            containment_report,
            narrative,
            report,
            stored_file.source_file_id,
            now,
        )
        provenance = [*provenance, narrative_result.provenance, containment_provenance]
        bundle = bundle.model_copy(
            update={
                "narrative": narrative,
                "narrative_containment": containment_report,
                "provenance": provenance,
                "ledger_events": list(ledger_events),
            }
        )
        require_bundle_provenance_complete(bundle)
        packet = build_review_packet_export(bundle, chunks, stored_file.source_file_id)
        if providers.vector_store is None:
            if config.require_opensearch:
                raise RuntimeError("OpenSearch vector store is required but not configured")
            return packet
        packet = await _persist_packet_to_opensearch_stage(
            packet,
            ledger_events,
            session,
            stored_file,
            now,
            providers,
            config,
        )
        final_packet = _packet_with_postgres_event_if_configured(
            packet,
            config=config,
            providers=providers,
            created_at=now,
        )
        if providers.ledger_store is None:
            if config.require_postgres:
                raise RuntimeError("Postgres ledger store is required but not configured")
            return final_packet
        try:
            await persist_review_packet_to_postgres(final_packet, providers.ledger_store)
        except Exception as error:
            await _record_workflow_failure(
                "postgres_packet_persistence",
                error,
                ledger_events,
                session,
                stored_file,
                now,
                providers,
                config,
            )
            raise
        return final_packet
    except Exception:
        raise



def _require_model_provider(
    providers: TranslumeWorkflowProviders,
    config: TranslumeWorkflowConfig,
):
    """Return the required local structured-output model provider.

    Acceptance criteria:
        1. Production/default mode fails if no local model provider exists.
        2. Does not create a fallback model provider.
        3. Keeps clinical artifact generation on the configured provider path.
    """
    if providers.model_provider is None:
        if config.require_local_vllm:
            raise RuntimeError(
                "Local vLLM structured-output model provider is required "
                "for clinical artifact generation"
            )
        raise RuntimeError(
            "Clinical artifact generation has no configured model provider"
        )
    return providers.model_provider


def _require_vllm_model(config: TranslumeWorkflowConfig) -> str:
    """Return the configured local vLLM model or fail loudly."""
    if not config.vllm_model.strip():
        raise RuntimeError("VLLM_MODEL is required for clinical artifact generation")
    return config.vllm_model


async def _persist_ingestion_metadata_before_processing(
    *,
    session,
    stored_file,
    upload_event: LedgerEvent,
    providers: TranslumeWorkflowProviders,
    config: TranslumeWorkflowConfig,
) -> None:
    """Persist upload/session metadata before clinical processing.

    Acceptance criteria:
        1. Fails before document extraction when Postgres is required but not
           configured.
        2. Persists case session, source-file metadata, and upload ledger event
           before document extraction begins.
        3. Propagates store failures rather than silently continuing.
        4. Performs no clinical interpretation.
    """
    if providers.ledger_store is None:
        if config.require_postgres:
            raise RuntimeError("Postgres ledger store is required before clinical processing")
        return
    await persist_ingestion_metadata_to_postgres(
        session,
        stored_file,
        upload_event,
        providers.ledger_store,
    )


async def _run_sync_workflow_stage(
    stage_name: str,
    ledger_events: list[LedgerEvent],
    session,
    stored_file,
    created_at: datetime,
    providers: TranslumeWorkflowProviders,
    config: TranslumeWorkflowConfig,
    operation,
):
    """Run a synchronous workflow stage with durable ledger events.

    Acceptance criteria:
        1. Records a stage-started event before running the operation.
        2. Records a stage-succeeded event when the operation succeeds.
        3. Records a stage-failed event when the operation raises.
        4. Persists each event to Postgres when a ledger store is configured.
        5. Never converts a failure into a successful placeholder artifact.
    """
    await _record_workflow_event(
        f"{stage_name}_started",
        ledger_events,
        session,
        stored_file,
        created_at,
        providers,
        config,
        details={"stage": stage_name, "status": "started"},
    )
    try:
        result = operation()
    except Exception as error:
        await _record_workflow_failure(
            stage_name,
            error,
            ledger_events,
            session,
            stored_file,
            created_at,
            providers,
            config,
        )
        raise
    await _record_workflow_event(
        f"{stage_name}_succeeded",
        ledger_events,
        session,
        stored_file,
        created_at,
        providers,
        config,
        details={"stage": stage_name, "status": "succeeded"},
    )
    return result


async def _run_async_workflow_stage(
    stage_name: str,
    ledger_events: list[LedgerEvent],
    session,
    stored_file,
    created_at: datetime,
    providers: TranslumeWorkflowProviders,
    config: TranslumeWorkflowConfig,
    operation,
):
    """Run an async workflow stage with durable ledger events.

    Acceptance criteria:
        1. Records a stage-started event before awaiting the operation.
        2. Records a stage-succeeded event when the operation succeeds.
        3. Records a stage-failed event when the operation raises.
        4. Persists each event to Postgres when a ledger store is configured.
        5. Never returns substitute evidence or placeholder success.
    """
    await _record_workflow_event(
        f"{stage_name}_started",
        ledger_events,
        session,
        stored_file,
        created_at,
        providers,
        config,
        details={"stage": stage_name, "status": "started"},
    )
    try:
        result = await run_with_latency_budget(
            stage_name=stage_name,
            timeout_seconds=_workflow_stage_latency_budget(config, stage_name),
            awaitable=operation(),
        )
    except Exception as error:
        await _record_workflow_failure(
            stage_name,
            error,
            ledger_events,
            session,
            stored_file,
            created_at,
            providers,
            config,
        )
        raise
    await _record_workflow_event(
        f"{stage_name}_succeeded",
        ledger_events,
        session,
        stored_file,
        created_at,
        providers,
        config,
        details={"stage": stage_name, "status": "succeeded"},
    )
    return result


async def _persist_packet_to_opensearch_stage(
    packet: ReviewPacketExport,
    ledger_events: list[LedgerEvent],
    session,
    stored_file,
    created_at: datetime,
    providers: TranslumeWorkflowProviders,
    config: TranslumeWorkflowConfig,
) -> ReviewPacketExport:
    """Persist a review packet to OpenSearch with visible stage events.

    Acceptance criteria:
        1. Records OpenSearch persistence started before network I/O.
        2. Records failure if OpenSearch persistence raises.
        3. Records success after persistence completes.
        4. Returns a packet whose ledger contains the success event.
        5. Does not fabricate OpenSearch success.
    """
    planned_batches = review_packet_to_index_batches(packet)
    await _record_workflow_event(
        "opensearch_persistence_started",
        ledger_events,
        session,
        stored_file,
        created_at,
        providers,
        config,
        details={index_name: str(len(documents)) for index_name, documents in planned_batches.items()},
    )
    try:
        packet_with_current_ledger = packet.model_copy(
            update={
                "bundle": packet.bundle.model_copy(
                    update={"ledger_events": list(ledger_events)}
                )
            }
        )
        await persist_review_packet_to_opensearch(
            packet_with_current_ledger,
            providers.vector_store,
            retrieval_mode=config.retrieval_mode,
            vector_dimension=config.vector_dimension,
        )
    except Exception as error:
        await _record_workflow_failure(
            "opensearch_persistence",
            error,
            ledger_events,
            session,
            stored_file,
            created_at,
            providers,
            config,
        )
        raise
    await _record_workflow_event(
        "opensearch_persistence_succeeded",
        ledger_events,
        session,
        stored_file,
        created_at,
        providers,
        config,
        details={index_name: str(len(documents)) for index_name, documents in planned_batches.items()},
    )
    await _record_workflow_event(
        "opensearch_persisted",
        ledger_events,
        session,
        stored_file,
        created_at,
        providers,
        config,
        details={index_name: str(len(documents)) for index_name, documents in planned_batches.items()},
    )
    return packet.model_copy(
        update={
            "bundle": packet.bundle.model_copy(
                update={"ledger_events": list(ledger_events)}
            )
        }
    )


async def _record_workflow_event(
    event_type: str,
    ledger_events: list[LedgerEvent],
    session,
    stored_file,
    created_at: datetime,
    providers: TranslumeWorkflowProviders,
    config: TranslumeWorkflowConfig,
    *,
    details: dict[str, str] | None = None,
) -> LedgerEvent:
    event = _workflow_event(
        event_type,
        session.case_id,
        session.session_id,
        stored_file.source_file_id,
        created_at,
        details=details,
    )
    ledger_events.append(event)
    if providers.ledger_store is not None:
        await append_ledger_event_to_postgres(event, providers.ledger_store)
    elif config.require_postgres:
        raise RuntimeError("Postgres ledger store is required for workflow event persistence")
    return event


async def _record_workflow_failure(
    stage_name: str,
    error: Exception,
    ledger_events: list[LedgerEvent],
    session,
    stored_file,
    created_at: datetime,
    providers: TranslumeWorkflowProviders,
    config: TranslumeWorkflowConfig,
) -> LedgerEvent:
    """Record a durable failure event for one workflow stage.

    Acceptance criteria:
        1. Preserves the failed stage name.
        2. Preserves a non-secret error type and message.
        3. Persists through the ledger store when configured.
        4. Does not suppress the original exception.
    """
    return await _record_workflow_event(
        f"{stage_name}_failed",
        ledger_events,
        session,
        stored_file,
        created_at,
        providers,
        config,
        details={
            "stage": stage_name,
            "status": "failed",
            "error_type": type(error).__name__,
            "error_message": _safe_error_message(error),
        },
    )


def _safe_error_message(error: Exception, max_chars: int = 500) -> str:
    """Return a bounded non-secret error message for ledger diagnostics."""
    message = str(error).replace("\n", " ").strip()
    if len(message) <= max_chars:
        return message
    return message[: max_chars - 3] + "..."



def _narrative_containment_provenance(
    containment_report: NarrativeContainmentReport,
    narrative,
    extraction,
    source_file_id: str,
    created_at: datetime,
) -> ArtifactProvenance:
    """Return provenance for deterministic narrative containment validation.

    Acceptance criteria:
        1. Records NarrativeContainmentReport as a validation artifact.
        2. Links the report to the narrative and supporting source artifacts.
        3. Uses the concrete schema hash for containment output.
        4. Does not perform I/O or mutate inputs.
    """
    return build_artifact_provenance(
        artifact_type="NarrativeContainmentReport",
        schema_name="NarrativeContainmentReport",
        model_name="translume_narrative_containment_validator_v1",
        prompt_text="Validate generated narrative against source-backed clinical artifact bundle before export.",
        schema_json=NarrativeContainmentReport.model_json_schema(),
        source_artifact_ids=[narrative.artifact_id, *containment_report.source_artifact_ids],
        source_chunk_ids=[
            finding.source_chunk_id
            for finding in extraction.molecular_findings
            if finding.source_chunk_id
        ],
        created_at=created_at,
        source_file_id=source_file_id,
        artifact_id=containment_report.artifact_id,
    )


def _packet_with_postgres_event_if_configured(
    packet: ReviewPacketExport,
    *,
    config: TranslumeWorkflowConfig,
    providers: TranslumeWorkflowProviders,
    created_at: datetime,
) -> ReviewPacketExport:
    if providers.ledger_store is None and not config.require_postgres:
        return packet
    planned_counts = review_packet_to_postgres_records(packet).counts()
    persistence_event = persistence_ledger_event(
        event_type="postgres_metadata_persisted",
        case_id=packet.case_id,
        session_id=packet.session_id,
        source_file_id=packet.source_file_id,
        created_at=created_at,
        counts_by_target=planned_counts,
    )
    bundle = packet.bundle.model_copy(
        update={"ledger_events": [*packet.bundle.ledger_events, persistence_event]}
    )
    return packet.model_copy(update={"bundle": bundle})


def _extract_best_document(
    stored_file,
    providers: TranslumeWorkflowProviders,
    config: TranslumeWorkflowConfig,
):
    """Run Docling plus PyMuPDF extraction and select the best output.

    Acceptance criteria:
        1. Runs Docling service extraction when configured.
        2. Fails explicitly when Docling is required but unavailable.
        3. Runs PyMuPDF baseline extraction for quality comparison.
        4. Scores every extraction candidate using explicit quality rules.
        5. Returns the highest-quality extraction, preferring Docling on ties.
        6. Does not perform clinical interpretation.

    Args:
        stored_file: Stored PDF metadata.
        providers: Workflow provider boundaries.
        config: Workflow configuration.

    Returns:
        Selected document extraction output.
    """
    candidates = []
    errors: list[str] = []
    if providers.document_extractor is not None:
        try:
            candidates.append(providers.document_extractor.extract(stored_file))
        except Exception as error:
            errors.append(f"docling_extraction_failed:{error}")
            if config.require_docling:
                raise RuntimeError(errors[-1]) from error
    elif config.require_docling:
        raise RuntimeError("Docling document extractor is required but not configured")
    try:
        candidates.append(extract_document_with_pymupdf(stored_file))
    except Exception as error:
        errors.append(f"pymupdf_extraction_failed:{error}")
        if not candidates:
            raise RuntimeError("no document extraction succeeded: " + ";".join(errors)) from error
    quality_reports = [score_extraction_quality(candidate) for candidate in candidates]
    selected = select_best_document_extraction(candidates, quality_reports)
    selected_quality = quality_reports[candidates.index(selected)]
    return selected.model_copy(
        update={
            "quality_score": selected_quality.quality_score,
            "needs_human_review": selected_quality.needs_human_review,
            "warnings": [*selected.warnings, *selected_quality.warnings, *errors],
        }
    )



async def _index_document_chunks_before_artifact_generation(
    chunks: list[DocumentChunk],
    providers: TranslumeWorkflowProviders,
    config: TranslumeWorkflowConfig,
):
    """Index source chunks in OpenSearch before artifact generation.

    Acceptance criteria:
        1. Fails when OpenSearch is required but no vector store is configured.
        2. Submits real source-backed chunk documents to OpenSearch.
        3. Does not proceed by pretending in-memory chunks were retrieval-backed.
        4. Does not create embeddings or claim vector search in this step.
        5. Fails loudly if vector/HNSW mode is requested before a real
           embedding provider exists.
    """
    if providers.vector_store is None:
        if config.require_opensearch:
            raise RuntimeError(
                "OpenSearch vector store is required before clinical artifact generation"
            )
        return None
    return await index_document_chunks_for_retrieval(
        vector_store=providers.vector_store,
        chunks=list(chunks),
        retrieval_mode=config.retrieval_mode,
        vector_dimension=config.vector_dimension,
    )


async def _retrieve_chunks_for_report_extraction(
    chunks: list[DocumentChunk],
    providers: TranslumeWorkflowProviders,
    config: TranslumeWorkflowConfig,
):
    """Retrieve indexed source chunks for report extraction.

    Acceptance criteria:
        1. Uses OpenSearch retrieval when OpenSearch is required.
        2. Fails if retrieval returns zero chunks.
        3. Allows explicit local-development fallback only when OpenSearch is
           not required.
        4. Does not silently substitute in-memory chunks in required mode.
    """
    if providers.vector_store is None:
        if config.require_opensearch:
            raise RuntimeError(
                "OpenSearch retrieval is required before report extraction"
            )
        from translume_schemas.document import RetrievedDocumentChunk

        return [
            RetrievedDocumentChunk(
                chunk=chunk,
                score=None,
                retrieval_method="in_memory_development_fallback",
            )
            for chunk in chunks
        ]
    if not chunks:
        raise RuntimeError("no source chunks are available for OpenSearch retrieval")
    first = chunks[0]
    return await retrieve_indexed_document_chunks(
        vector_store=providers.vector_store,
        case_id=first.case_id,
        session_id=first.session_id,
        source_file_id=first.source_file_id,
        top_k=len(chunks),
        retrieval_mode=config.retrieval_mode,
    )

async def _get_graph_evidence(
    entities,
    providers: TranslumeWorkflowProviders,
    config: TranslumeWorkflowConfig,
) -> GraphEvidenceArtifact:
    if providers.graph_provider is None:
        if config.require_mims:
            raise RuntimeError("MIMS graph provider is required but not configured")
        return _missing_graph_evidence(
            entities,
            "graph_provider_not_configured",
            config.graph_retrieval_modes,
        )

    async def retrieve() -> GraphEvidenceArtifact:
        return await providers.graph_provider.retrieve_context(
            entities,
            retrieval_modes=config.graph_retrieval_modes,
        )

    try:
        cache = _workflow_cache(providers, config)
        if cache is None:
            return await retrieve()
        return await cache.get_or_set(
            stable_cache_key("optimuskg_graph", entities, config.graph_retrieval_modes),
            retrieve,
            ttl_seconds=config.graph_cache_ttl_seconds,
        )
    except Exception as error:
        if config.require_mims:
            raise
        return _missing_graph_evidence(entities, str(error), config.graph_retrieval_modes)


async def _get_tool_outputs(
    entities,
    graph: GraphEvidenceArtifact,
    providers: TranslumeWorkflowProviders,
    config: TranslumeWorkflowConfig,
) -> list[ToolRunArtifact]:
    if providers.tool_provider is None:
        if config.require_mims:
            raise RuntimeError("MIMS tool provider is required but not configured")
        return []

    async def run_tools() -> list[ToolRunArtifact]:
        return await providers.tool_provider.run_workflows(
            workflows=list(config.tool_workflows),
            entities=entities,
            graph=graph,
        )

    try:
        cache = _workflow_cache(providers, config)
        if cache is None:
            return await run_tools()
        return await cache.get_or_set(
            stable_cache_key(
                "tooluniverse_workflows",
                config.tool_workflows,
                entities,
                graph,
            ),
            run_tools,
            ttl_seconds=config.tool_cache_ttl_seconds,
        )
    except Exception:
        if config.require_mims:
            raise
        return []


async def _get_medea_reasoning(
    context: EvidenceContextBundle,
    providers: TranslumeWorkflowProviders,
    config: TranslumeWorkflowConfig,
) -> MedeaReasoningArtifact:
    if providers.reasoning_provider_factory is None:
        if config.require_mims:
            raise RuntimeError("MIMS reasoning provider is required but not configured")
        return _missing_medea_reasoning(
            context.artifact_id,
            "reasoning_provider_not_configured",
        )

    async def reason() -> MedeaReasoningArtifact:
        provider = providers.reasoning_provider_factory(context)
        return await provider.reason_over_context(context)

    try:
        cache = _workflow_cache(providers, config)
        if cache is None:
            return await reason()
        return await cache.get_or_set(
            stable_cache_key("medea_reasoning", context),
            reason,
            ttl_seconds=config.medea_cache_ttl_seconds,
        )
    except Exception as error:
        if config.require_mims:
            raise
        return _missing_medea_reasoning(context.artifact_id, str(error))


def _missing_graph_evidence(
    entities,
    warning: str,
    retrieval_modes: Sequence[GraphRetrievalMode] | None = None,
) -> GraphEvidenceArtifact:
    artifact_id = f"artifact_{uuid5(NAMESPACE_URL, entities.artifact_id + ':missing_graph').hex[:16]}"
    return GraphEvidenceArtifact(
        artifact_id=artifact_id,
        source_entity_ids=[entity.entity_id for entity in entities.entities],
        nodes=[],
        edges=[],
        missing_entities=[entity.entity_id for entity in entities.entities],
        warnings=[warning],
        retrieval_modes=list(retrieval_modes or []),
    )


def _empty_medea_reasoning(seed: str) -> MedeaReasoningArtifact:
    artifact_id = f"artifact_{uuid5(NAMESPACE_URL, seed + ':empty_medea').hex[:16]}"
    return MedeaReasoningArtifact(
        artifact_id=artifact_id,
        reasoning_mode="not_yet_run",
        summary="",
        supported_hypotheses=[],
        weakened_hypotheses=[],
        warnings=[],
        requires_human_review=True,
        decision_support_role="hypothesis_support_only",
        downstream_uses=[],
    )


def _missing_medea_reasoning(seed: str, warning: str) -> MedeaReasoningArtifact:
    artifact_id = f"artifact_{uuid5(NAMESPACE_URL, seed + ':missing_medea').hex[:16]}"
    return MedeaReasoningArtifact(
        artifact_id=artifact_id,
        reasoning_mode="missing_bounded_reasoning",
        summary="Medea bounded reasoning was unavailable; claims must remain needs_review.",
        supported_hypotheses=[],
        weakened_hypotheses=[],
        warnings=[warning],
        requires_human_review=True,
        decision_support_role="hypothesis_support_only",
        downstream_uses=["evidence_limitations"],
    )



def _workflow_event(
    event_type: str,
    case_id: str,
    session_id: str,
    source_file_id: str,
    created_at: datetime,
    *,
    details: dict[str, str] | None = None,
) -> LedgerEvent:
    event_id = f"event_{uuid5(NAMESPACE_URL, f'{case_id}:{session_id}:{source_file_id}:{event_type}').hex[:16]}"
    return LedgerEvent(
        event_id=event_id,
        event_type=event_type,
        case_id=case_id,
        session_id=session_id,
        source_file_id=source_file_id,
        created_at=created_at,
        details={} if details is None else dict(details),
    )
