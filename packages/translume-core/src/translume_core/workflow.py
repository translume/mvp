from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from translume_core.compiler.claim_evidence import classify_evidence_strength
from translume_core.compiler.confirmatory_testing import generate_confirmatory_testing_from_context
from translume_core.compiler.entity_normalization import normalize_report_entities
from translume_core.compiler.evidence_context import combine_evidence_sources
from translume_core.compiler.mechanism_sankey import generate_mechanism_sankey_from_context
from translume_core.compiler.molecular_fit_matrix import generate_molecular_fit_matrix_from_context
from translume_core.compiler.molecular_phenotype import generate_molecular_phenotype_from_context
from translume_core.compiler.narrative import generate_clinical_narrative_from_bundle
from translume_core.compiler.report_extraction import generate_report_extraction_from_chunks
from translume_core.compiler.tumor_behavior import generate_tumor_behavior_model_from_context
from translume_core.document.chunks import build_document_chunks, merge_small_adjacent_chunks
from translume_core.document.pymupdf_adapter import extract_document_with_pymupdf
from translume_core.document.quality import score_extraction_quality, select_best_document_extraction
from translume_core.document.sections import detect_section_headers
from translume_core.export.review_packet import build_review_packet_export
from translume_core.ingestion.ledger_events import record_upload_ledger_event
from translume_core.ingestion.sessions import create_case_session
from translume_core.ingestion.storage import persist_uploaded_pdf
from translume_core.indexing.documents import review_packet_to_index_batches
from translume_core.indexing.persistence import persist_review_packet_to_opensearch
from translume_core.persistence.ledger_events import persistence_ledger_event
from translume_core.persistence.postgres_persistence import persist_review_packet_to_postgres
from translume_core.persistence.postgres_records import review_packet_to_postgres_records
from translume_core.provenance.provenance import build_artifact_provenance
from translume_schemas.document import DocumentChunk
from translume_schemas.evidence import EvidenceContextBundle
from translume_schemas.export import ClinicalArtifactBundle, ReviewPacketExport
from translume_schemas.graph import GraphEvidenceArtifact
from translume_schemas.ledger import LedgerEvent
from translume_schemas.medea import MedeaReasoningArtifact
from translume_schemas.provenance import ArtifactProvenance
from translume_schemas.tools import ToolRunArtifact


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
    """

    graph_provider: object | None = None
    tool_provider: object | None = None
    reasoning_provider_factory: object | None = None
    vector_store: object | None = None
    ledger_store: object | None = None
    document_extractor: object | None = None


@dataclass(frozen=True)
class TranslumeWorkflowConfig:
    """Workflow configuration.

    Attributes:
        storage_root: Root for raw uploads and artifacts.
        max_chunk_chars: Maximum merged chunk size.
        require_mims: Whether graph/tool/Medea providers are required.
        tool_workflows: Allow-listed ToolUniverse workflow names to run.
        require_opensearch: Whether OpenSearch persistence is mandatory.
        require_postgres: Whether Postgres metadata persistence is mandatory.
        vector_dimension: Dense-vector dimension for OpenSearch index specs.
        require_docling: Whether Docling layout extraction must run.
    """

    storage_root: Path
    max_chunk_chars: int = 2400
    require_mims: bool = True
    require_opensearch: bool = True
    require_postgres: bool = True
    vector_dimension: int = 384
    require_docling: bool = True
    tool_workflows: tuple[str, ...] = (
        "literature_validation",
        "pathway_context",
        "target_context",
        "variant_context",
        "trial_context_review",
    )


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
        1. PDF upload creates session and ledger event.
        2. Document extraction creates source-backed chunks.
        3. Report extraction produces source-backed findings.
        4. Entity normalization succeeds for extracted findings.
        5. MIMS providers run in strict mode or explicit missing evidence is
           recorded in non-strict development mode.
        6. Molecular phenotype, matrix, Sankey, confirmatory tests,
           tumor-behavior model, claims, narrative, provenance, and export are
           produced.
        7. No treatment recommendation, outcome prediction, or transition
           probability is generated.

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
    extraction_output = _extract_best_document(stored_file, providers, config)
    sections = detect_section_headers(extraction_output)
    chunks = merge_small_adjacent_chunks(
        build_document_chunks(extraction_output, sections, session, stored_file),
        max_chars=config.max_chunk_chars,
    )
    report = generate_report_extraction_from_chunks(
        chunks,
        report_type=session.report_type,
        source_file_id=stored_file.source_file_id,
    )
    entities = normalize_report_entities(
        report,
        case_id=session.case_id,
        session_id=session.session_id,
    )
    graph = await _get_graph_evidence(entities, providers, config)
    preliminary_context = combine_evidence_sources(
        report,
        graph,
        [],
        _empty_medea_reasoning(report.artifact_id),
    )
    tools = await _get_tool_outputs(entities, graph, providers, config)
    context_without_medea = combine_evidence_sources(
        report,
        graph,
        tools,
        _empty_medea_reasoning(report.artifact_id),
    )
    medea = await _get_medea_reasoning(context_without_medea, providers, config)
    context = combine_evidence_sources(report, graph, tools, medea)
    phenotype = generate_molecular_phenotype_from_context(context)
    matrix = generate_molecular_fit_matrix_from_context(context, phenotype)
    sankey = generate_mechanism_sankey_from_context(context, phenotype, matrix)
    confirmatory = generate_confirmatory_testing_from_context(context, matrix)
    tumor_behavior = generate_tumor_behavior_model_from_context(context)
    claims = classify_evidence_strength(context)
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
        claims=claims,
        provenance=_build_workflow_provenance(
            source_file_id=stored_file.source_file_id,
            chunks=chunks,
            context=context,
            artifact_ids=[
                report.artifact_id,
                entities.artifact_id,
                graph.artifact_id,
                *[tool.artifact_id for tool in tools],
                medea.artifact_id,
                context.artifact_id,
                phenotype.artifact_id,
                matrix.artifact_id,
                sankey.artifact_id,
                confirmatory.artifact_id,
                tumor_behavior.artifact_id,
            ],
            created_at=now,
        ),
        ledger_events=[
            upload_event,
            _workflow_event("document_extracted", session.case_id, session.session_id, stored_file.source_file_id, now),
            _workflow_event("review_packet_compiled", session.case_id, session.session_id, stored_file.source_file_id, now),
        ],
    )
    narrative = generate_clinical_narrative_from_bundle(bundle)
    bundle = bundle.model_copy(update={"narrative": narrative})
    packet = build_review_packet_export(bundle, chunks, stored_file.source_file_id)
    if providers.vector_store is None:
        if config.require_opensearch:
            raise RuntimeError("OpenSearch vector store is required but not configured")
        return packet
    planned_batches = review_packet_to_index_batches(packet)
    persistence_event = _workflow_event(
        "opensearch_persisted",
        session.case_id,
        session.session_id,
        stored_file.source_file_id,
        now,
        details={index_name: str(len(documents)) for index_name, documents in planned_batches.items()},
    )
    persisted_bundle = packet.bundle.model_copy(
        update={"ledger_events": [*packet.bundle.ledger_events, persistence_event]}
    )
    persisted_packet = packet.model_copy(update={"bundle": persisted_bundle})
    await persist_review_packet_to_opensearch(
        persisted_packet,
        providers.vector_store,
        vector_dimension=config.vector_dimension,
    )
    final_packet = _packet_with_postgres_event_if_configured(
        persisted_packet,
        config=config,
        providers=providers,
        created_at=now,
    )
    if providers.ledger_store is None:
        if config.require_postgres:
            raise RuntimeError("Postgres ledger store is required but not configured")
        return final_packet
    await persist_review_packet_to_postgres(final_packet, providers.ledger_store)
    return final_packet


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


async def _get_graph_evidence(
    entities,
    providers: TranslumeWorkflowProviders,
    config: TranslumeWorkflowConfig,
) -> GraphEvidenceArtifact:
    if providers.graph_provider is None:
        if config.require_mims:
            raise RuntimeError("MIMS graph provider is required but not configured")
        return _missing_graph_evidence(entities, "graph_provider_not_configured")
    try:
        return await providers.graph_provider.retrieve_context(entities)
    except Exception as error:
        if config.require_mims:
            raise
        return _missing_graph_evidence(entities, str(error))


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
    try:
        return await providers.tool_provider.run_workflows(
            workflows=list(config.tool_workflows),
            entities=entities,
            graph=graph,
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
        return _missing_medea_reasoning(context.artifact_id, "reasoning_provider_not_configured")
    try:
        provider = providers.reasoning_provider_factory(context)
        return await provider.reason_over_context(context)
    except Exception as error:
        if config.require_mims:
            raise
        return _missing_medea_reasoning(context.artifact_id, str(error))


def _missing_graph_evidence(entities, warning: str) -> GraphEvidenceArtifact:
    artifact_id = f"artifact_{uuid5(NAMESPACE_URL, entities.artifact_id + ':missing_graph').hex[:16]}"
    return GraphEvidenceArtifact(
        artifact_id=artifact_id,
        source_entity_ids=[entity.entity_id for entity in entities.entities],
        nodes=[],
        edges=[],
        missing_entities=[entity.entity_id for entity in entities.entities],
        warnings=[warning],
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
    )


def _build_workflow_provenance(
    *,
    source_file_id: str,
    chunks: Sequence[DocumentChunk],
    context: EvidenceContextBundle,
    artifact_ids: Sequence[str],
    created_at: datetime,
) -> list[ArtifactProvenance]:
    source_ids = [context.extraction.artifact_id, context.graph_evidence.artifact_id]
    source_ids.extend(tool.artifact_id for tool in context.tool_outputs)
    source_ids.append(context.medea_reasoning.artifact_id)
    return [
        build_artifact_provenance(
            artifact_type="workflow_artifact",
            schema_name="translume_mvp",
            model_name="deterministic_compiler_or_external_provider",
            prompt_text=None,
            schema_json=None,
            source_artifact_ids=source_ids,
            created_at=created_at,
            source_file_id=source_file_id,
            artifact_id=artifact_id,
        )
        for artifact_id in artifact_ids
    ]


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
