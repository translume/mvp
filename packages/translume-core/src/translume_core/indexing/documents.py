from __future__ import annotations

from collections.abc import Iterable, Sequence
from translume_core.indexing.retrieval_scope import require_lexical_retrieval_scope

from pydantic import BaseModel

from translume_schemas.claims import ClaimEvidenceOutput
from translume_schemas.document import DocumentChunk
from translume_schemas.entities import NormalizedEntitySet
from translume_schemas.export import ReviewPacketExport
from translume_schemas.extraction import ReportExtractionOutput
from translume_schemas.graph import GraphEvidenceArtifact
from translume_schemas.ledger import LedgerEvent
from translume_schemas.medea import MedeaReasoningArtifact
from translume_schemas.provenance import ArtifactProvenance
from translume_schemas.tools import ToolRunArtifact
from translume_schemas.validation import ValidationDecision


INDEX_DOCUMENT_CHUNKS = "translume_document_chunks"
INDEX_REPORT_FINDINGS = "translume_report_findings"
INDEX_ARTIFACTS = "translume_artifacts"
INDEX_NORMALIZED_ENTITIES = "translume_normalized_entities"
INDEX_GRAPH_EVIDENCE = "translume_graph_evidence"
INDEX_TOOL_OUTPUTS = "translume_tool_outputs"
INDEX_MEDEA_REASONING = "translume_medea_reasoning"
INDEX_EVIDENCE_CLAIMS = "translume_evidence_claims"
INDEX_ARTIFACT_PROVENANCE = "translume_artifact_provenance"
INDEX_VALIDATION_DECISIONS = "translume_validation_decisions"
INDEX_LEDGER_EVENTS = "translume_ledger_events"


def _json(value: object) -> object:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {str(key): _json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json(item) for item in value]
    if isinstance(value, tuple):
        return [_json(item) for item in value]
    return value


def _artifact_doc(
    *,
    artifact_id: str,
    artifact_type: str,
    case_id: str,
    session_id: str,
    source_file_id: str,
    source_artifact_ids: Sequence[str],
    summary_text: str,
    payload: object,
) -> dict[str, object]:
    return {
        "document_id": artifact_id,
        "artifact_id": artifact_id,
        "artifact_type": artifact_type,
        "case_id": case_id,
        "session_id": session_id,
        "source_file_id": source_file_id,
        "source_artifact_ids": list(source_artifact_ids),
        "summary_text": summary_text,
        "payload": _json(payload),
    }


def document_chunk_to_opensearch_doc(
    chunk: DocumentChunk,
    embedding: Sequence[float] | None = None,
    *,
    expected_vector_dimension: int | None = None,
    retrieval_mode: str = "lexical",
) -> dict[str, object]:
    """Convert a document chunk into an OpenSearch document.

    Acceptance criteria:
        1. Output includes all required filter fields.
        2. Output includes source text and source block IDs.
        3. Output includes bbox if available.
        4. Lexical MVP mode rejects embeddings instead of pretending vector
           retrieval is active.
        5. Vector/HNSW mode fails until a real embedding provider exists.
        6. Function is pure.

    Args:
        chunk: Source document chunk.
        embedding: Reserved for a future real embedding provider. Must be None
            in lexical MVP mode.
        expected_vector_dimension: Reserved for a future real embedding provider.
        retrieval_mode: Active retrieval mode. The MVP supports only lexical.

    Returns:
        JSON-compatible OpenSearch document.

    Raises:
        ValueError: If embedding inputs are provided in lexical mode or if
            retrieval_mode requests unsupported vector behavior.
    """
    require_lexical_retrieval_scope(retrieval_mode)
    if embedding is not None:
        raise ValueError(
            "embedding was provided, but TRANSLUME_RETRIEVAL_MODE=lexical is "
            "the only MVP-supported retrieval mode. Do not index embeddings "
            "until a real embedding provider is configured and validated."
        )
    if expected_vector_dimension is not None:
        raise ValueError(
            "expected_vector_dimension was provided, but lexical MVP retrieval "
            "does not use vector dimensions."
        )
    doc: dict[str, object] = {
        "document_id": chunk.chunk_id,
        "chunk_id": chunk.chunk_id,
        "case_id": chunk.case_id,
        "session_id": chunk.session_id,
        "source_file_id": chunk.source_file_id,
        "report_type": chunk.report_type,
        "page_start": chunk.page_start,
        "page_end": chunk.page_end,
        "section": chunk.section,
        "chunk_type": chunk.chunk_type,
        "source_text": chunk.source_text,
        "source_block_ids": chunk.source_block_ids,
        "needs_human_review": chunk.needs_human_review,
        "retrieval_mode": "lexical",
        "retrieval_method": "opensearch_metadata_lexical",
    }
    if chunk.bbox is not None:
        doc["bbox"] = chunk.bbox.model_dump(mode="json")
    return doc


def report_findings_to_opensearch_docs(
    extraction: ReportExtractionOutput,
    *,
    case_id: str,
    session_id: str,
) -> list[dict[str, object]]:
    """Convert report findings to OpenSearch documents.

    Acceptance criteria:
        1. Every finding becomes one searchable document.
        2. Each document preserves case/session/source identifiers.
        3. Source text and source page are preserved.
        4. Function is pure.
    """
    return [
        {
            "document_id": finding.finding_id,
            "finding_id": finding.finding_id,
            "artifact_id": extraction.artifact_id,
            "case_id": case_id,
            "session_id": session_id,
            "source_file_id": extraction.source_file_id,
            "gene": finding.gene,
            "alteration": finding.alteration,
            "alteration_type": finding.alteration_type,
            "source_page": finding.source_page,
            "source_text": finding.source_text,
            "source_chunk_id": finding.source_chunk_id,
            "confidence": finding.confidence,
            "needs_human_review": finding.needs_human_review,
            "research_use_only": finding.research_use_only,
        }
        for finding in extraction.molecular_findings
    ]


def normalized_entities_to_opensearch_docs(
    entities: NormalizedEntitySet,
) -> list[dict[str, object]]:
    """Convert normalized entities to OpenSearch documents."""
    return [
        {
            "document_id": entity.entity_id,
            "artifact_id": entities.artifact_id,
            "entity_id": entity.entity_id,
            "case_id": entities.case_id,
            "session_id": entities.session_id,
            "entity_type": entity.entity_type,
            "original_text": entity.original_text,
            "normalized_label": entity.normalized_label,
            "source_finding_id": entity.source_finding_id,
            "source_artifact_id": entity.source_artifact_id,
            "needs_human_review": entity.needs_human_review,
        }
        for entity in entities.entities
    ]


def graph_context_to_opensearch_docs(
    graph: GraphEvidenceArtifact,
    *,
    case_id: str,
    session_id: str,
) -> list[dict[str, object]]:
    """Convert graph evidence into node and edge OpenSearch documents.

    Acceptance criteria:
        1. Every graph node and edge becomes a searchable document.
        2. Each document preserves graph artifact and case/session IDs.
        3. Edges preserve relation type and endpoint IDs.
        4. Function is pure.
    """
    nodes = [
        {
            "document_id": f"{graph.artifact_id}:{node.node_id}",
            "artifact_id": graph.artifact_id,
            "case_id": case_id,
            "session_id": session_id,
            "record_type": "node",
            "node_id": node.node_id,
            "edge_id": None,
            "label": node.label,
            "kind": node.kind,
            "source_node_id": None,
            "target_node_id": None,
            "relation_type": None,
            "source": node.source,
            "source_entity_ids": graph.source_entity_ids,
            "provenance": node.provenance,
        }
        for node in graph.nodes
    ]
    edges = [
        {
            "document_id": f"{graph.artifact_id}:{edge.edge_id}",
            "artifact_id": graph.artifact_id,
            "case_id": case_id,
            "session_id": session_id,
            "record_type": "edge",
            "node_id": None,
            "edge_id": edge.edge_id,
            "label": edge.relation_type,
            "kind": "relation",
            "source_node_id": edge.source_node_id,
            "target_node_id": edge.target_node_id,
            "relation_type": edge.relation_type,
            "source": edge.source,
            "source_entity_ids": graph.source_entity_ids,
            "provenance": edge.provenance,
        }
        for edge in graph.edges
    ]
    return [*nodes, *edges]


def tool_outputs_to_opensearch_docs(
    tools: Sequence[ToolRunArtifact],
    *,
    case_id: str,
    session_id: str,
) -> list[dict[str, object]]:
    """Convert governed tool outputs to OpenSearch documents."""
    return [
        {
            "document_id": tool.artifact_id,
            "artifact_id": tool.artifact_id,
            "case_id": case_id,
            "session_id": session_id,
            "workflow": tool.workflow,
            "input_entity_ids": tool.input_entity_ids,
            "summary": tool.summary,
            "evidence_items": _json(tool.evidence_items),
            "warnings": tool.warnings,
            "requires_human_review": tool.requires_human_review,
        }
        for tool in tools
    ]


def medea_reasoning_to_opensearch_doc(
    medea: MedeaReasoningArtifact,
    *,
    case_id: str,
    session_id: str,
) -> dict[str, object]:
    """Convert bounded Medea reasoning to an OpenSearch document."""
    return {
        "document_id": medea.artifact_id,
        "artifact_id": medea.artifact_id,
        "case_id": case_id,
        "session_id": session_id,
        "reasoning_mode": medea.reasoning_mode,
        "summary": medea.summary,
        "supported_hypotheses": medea.supported_hypotheses,
        "weakened_hypotheses": medea.weakened_hypotheses,
        "warnings": medea.warnings,
        "requires_human_review": medea.requires_human_review,
    }


def claims_to_opensearch_docs(
    claims: Sequence[ClaimEvidenceOutput],
    *,
    case_id: str,
    session_id: str,
) -> list[dict[str, object]]:
    """Convert evidence claim cards to OpenSearch documents."""
    return [
        {
            "document_id": claim.claim_id,
            "claim_id": claim.claim_id,
            "case_id": case_id,
            "session_id": session_id,
            "claim": claim.claim,
            "claim_class": claim.claim_class,
            "evidence_source": claim.evidence_source,
            "limitations": claim.limitations,
            "validation_status": claim.validation_status,
            "source_artifact_ids": claim.source_artifact_ids,
        }
        for claim in claims
    ]


def provenance_to_opensearch_docs(
    provenance: Sequence[ArtifactProvenance],
) -> list[dict[str, object]]:
    """Convert artifact provenance records to OpenSearch documents."""
    return [
        {
            "document_id": record.artifact_id,
            **record.model_dump(mode="json"),
        }
        for record in provenance
    ]


def validation_decisions_to_opensearch_docs(
    decisions: Sequence[ValidationDecision],
    *,
    case_id: str,
    session_id: str,
) -> list[dict[str, object]]:
    """Convert validation decisions to OpenSearch documents."""
    return [
        {
            "document_id": decision.decision_id,
            "claim_id": decision.claim_id,
            "case_id": case_id,
            "session_id": session_id,
            "status": decision.status,
            "reviewer_id": decision.reviewer_id,
            "reviewer_note": decision.reviewer_note,
            "created_at": decision.created_at.isoformat(),
        }
        for decision in decisions
    ]


def ledger_events_to_opensearch_docs(
    events: Sequence[LedgerEvent],
) -> list[dict[str, object]]:
    """Convert ledger events to OpenSearch documents."""
    return [
        {
            "document_id": event.event_id,
            **event.model_dump(mode="json"),
        }
        for event in events
    ]


def artifact_bundle_to_opensearch_docs(
    packet: ReviewPacketExport,
) -> list[dict[str, object]]:
    """Convert top-level structured artifacts into searchable records.

    Acceptance criteria:
        1. Every present top-level artifact becomes one document.
        2. Documents include case/session/source IDs.
        3. Full artifact payload is preserved under `payload`.
        4. Summary text is searchable.
    """
    bundle = packet.bundle
    docs: list[dict[str, object]] = []
    docs.append(
        _artifact_doc(
            artifact_id=bundle.extraction.artifact_id,
            artifact_type="report_extraction",
            case_id=packet.case_id,
            session_id=packet.session_id,
            source_file_id=packet.source_file_id,
            source_artifact_ids=[],
            summary_text=" ".join(
                finding.alteration for finding in bundle.extraction.molecular_findings
            ),
            payload=bundle.extraction,
        )
    )
    optional_artifacts: list[tuple[str, object | None, Iterable[str], str]] = [
        ("normalized_entities", bundle.entities, [bundle.extraction.artifact_id], "normalized biomedical entities"),
        ("evidence_context", bundle.evidence_context, [bundle.extraction.artifact_id], "combined evidence context"),
        ("molecular_phenotype", bundle.phenotype, [bundle.extraction.artifact_id], "molecular phenotype"),
        ("molecular_fit_matrix", bundle.matrix, [bundle.extraction.artifact_id], "molecular fit matrix"),
        ("mechanism_sankey", bundle.sankey, [bundle.extraction.artifact_id], "mechanism sankey"),
        ("confirmatory_testing", bundle.confirmatory, [bundle.extraction.artifact_id], "confirmatory testing"),
        ("tumor_behavior", bundle.tumor_behavior, [bundle.extraction.artifact_id], "tumor behavior model"),
        ("oncologist_decision_brief", bundle.decision_brief, [bundle.extraction.artifact_id], "oncologist decision brief"),
        ("clinical_narrative", bundle.narrative, [bundle.extraction.artifact_id], "clinical narrative"),
        ("narrative_containment", bundle.narrative_containment, [bundle.extraction.artifact_id], "narrative containment report"),
    ]
    for artifact_type, artifact, source_artifact_ids, fallback_summary in optional_artifacts:
        if artifact is None:
            continue
        artifact_id = getattr(artifact, "artifact_id")
        docs.append(
            _artifact_doc(
                artifact_id=artifact_id,
                artifact_type=artifact_type,
                case_id=packet.case_id,
                session_id=packet.session_id,
                source_file_id=packet.source_file_id,
                source_artifact_ids=list(source_artifact_ids),
                summary_text=_summary_text(artifact, fallback_summary),
                payload=artifact,
            )
        )
    return docs


def _summary_text(artifact: object, fallback: str) -> str:
    if hasattr(artifact, "clinical_decision_summary"):
        return str(getattr(artifact, "clinical_decision_summary"))
    if hasattr(artifact, "markdown"):
        return str(getattr(artifact, "markdown"))
    if hasattr(artifact, "summary"):
        return str(getattr(artifact, "summary"))
    return fallback


def review_packet_to_index_batches(
    packet: ReviewPacketExport,
) -> dict[str, list[dict[str, object]]]:
    """Convert a review packet into OpenSearch index batches.

    Acceptance criteria:
        1. Every MVP persistence index is represented in the returned mapping.
        2. Source chunks, artifacts, evidence, claims, provenance, validation,
           and ledger events are included.
        3. Function performs no network I/O.
        4. Function is deterministic and does not mutate the packet.
    """
    bundle = packet.bundle
    batches: dict[str, list[dict[str, object]]] = {
        INDEX_DOCUMENT_CHUNKS: [
            document_chunk_to_opensearch_doc(chunk) for chunk in packet.chunks
        ],
        INDEX_REPORT_FINDINGS: report_findings_to_opensearch_docs(
            bundle.extraction,
            case_id=packet.case_id,
            session_id=packet.session_id,
        ),
        INDEX_ARTIFACTS: artifact_bundle_to_opensearch_docs(packet),
        INDEX_NORMALIZED_ENTITIES: [],
        INDEX_GRAPH_EVIDENCE: [],
        INDEX_TOOL_OUTPUTS: [],
        INDEX_MEDEA_REASONING: [],
        INDEX_EVIDENCE_CLAIMS: claims_to_opensearch_docs(
            bundle.claims,
            case_id=packet.case_id,
            session_id=packet.session_id,
        ),
        INDEX_ARTIFACT_PROVENANCE: provenance_to_opensearch_docs(bundle.provenance),
        INDEX_VALIDATION_DECISIONS: validation_decisions_to_opensearch_docs(
            bundle.validation_decisions,
            case_id=packet.case_id,
            session_id=packet.session_id,
        ),
        INDEX_LEDGER_EVENTS: ledger_events_to_opensearch_docs(bundle.ledger_events),
    }
    if bundle.entities is not None:
        batches[INDEX_NORMALIZED_ENTITIES] = normalized_entities_to_opensearch_docs(
            bundle.entities
        )
    if bundle.evidence_context is not None:
        batches[INDEX_GRAPH_EVIDENCE] = graph_context_to_opensearch_docs(
            bundle.evidence_context.graph_evidence,
            case_id=packet.case_id,
            session_id=packet.session_id,
        )
        batches[INDEX_TOOL_OUTPUTS] = tool_outputs_to_opensearch_docs(
            bundle.evidence_context.tool_outputs,
            case_id=packet.case_id,
            session_id=packet.session_id,
        )
        batches[INDEX_MEDEA_REASONING] = [
            medea_reasoning_to_opensearch_doc(
                bundle.evidence_context.medea_reasoning,
                case_id=packet.case_id,
                session_id=packet.session_id,
            )
        ]
    return batches
