from __future__ import annotations

from collections.abc import Mapping


IndexSpec = dict[str, object]


def _keyword() -> dict[str, str]:
    return {"type": "keyword"}


def _text() -> dict[str, str]:
    return {"type": "text"}


def _integer() -> dict[str, str]:
    return {"type": "integer"}


def _boolean() -> dict[str, str]:
    return {"type": "boolean"}


def _date() -> dict[str, str]:
    return {"type": "date"}


def _object(enabled: bool = True) -> dict[str, object]:
    return {"type": "object", "enabled": enabled}


def _index_spec(index_name: str, properties: Mapping[str, object]) -> IndexSpec:
    return {
        "index_name": index_name,
        "body": {
            "settings": {"index": {"knn": True}},
            "mappings": {"properties": dict(properties)},
        },
    }


def build_document_chunk_index_spec(vector_dimension: int) -> IndexSpec:
    """Build OpenSearch mapping for document chunks.

    Acceptance criteria:
        1. Mapping includes case/session/source IDs as keyword fields.
        2. Mapping includes page fields as integers.
        3. Mapping includes section/report/chunk type filters.
        4. Mapping includes source_text as text.
        5. Mapping includes embedding vector field.
        6. Function is deterministic.

    Args:
        vector_dimension: Dense vector dimension.

    Returns:
        OpenSearch index specification.
    """
    if vector_dimension <= 0:
        raise ValueError("vector_dimension must be positive")
    return _index_spec(
        "translume_document_chunks",
        {
            "document_id": _keyword(),
            "chunk_id": _keyword(),
            "case_id": _keyword(),
            "session_id": _keyword(),
            "source_file_id": _keyword(),
            "report_type": _keyword(),
            "section": _keyword(),
            "chunk_type": _keyword(),
            "page_start": _integer(),
            "page_end": _integer(),
            "source_text": _text(),
            "source_block_ids": _keyword(),
            "needs_human_review": _boolean(),
            "bbox": _object(),
            "embedding": {"type": "knn_vector", "dimension": vector_dimension},
        },
    )


def build_report_finding_index_spec() -> IndexSpec:
    """Build OpenSearch mapping for report molecular findings."""
    return _index_spec(
        "translume_report_findings",
        {
            "document_id": _keyword(),
            "finding_id": _keyword(),
            "artifact_id": _keyword(),
            "case_id": _keyword(),
            "session_id": _keyword(),
            "source_file_id": _keyword(),
            "gene": _keyword(),
            "alteration": _text(),
            "alteration_type": _keyword(),
            "source_page": _integer(),
            "source_text": _text(),
            "source_chunk_id": _keyword(),
            "confidence": {"type": "float"},
            "needs_human_review": _boolean(),
            "research_use_only": _boolean(),
        },
    )


def build_artifact_index_spec() -> IndexSpec:
    """Build OpenSearch mapping for structured clinical artifacts."""
    return _index_spec(
        "translume_artifacts",
        {
            "document_id": _keyword(),
            "artifact_id": _keyword(),
            "artifact_type": _keyword(),
            "case_id": _keyword(),
            "session_id": _keyword(),
            "source_file_id": _keyword(),
            "source_artifact_ids": _keyword(),
            "summary_text": _text(),
            "payload": _object(enabled=False),
        },
    )


def build_normalized_entity_index_spec() -> IndexSpec:
    """Build OpenSearch mapping for normalized report entities."""
    return _index_spec(
        "translume_normalized_entities",
        {
            "document_id": _keyword(),
            "artifact_id": _keyword(),
            "entity_id": _keyword(),
            "case_id": _keyword(),
            "session_id": _keyword(),
            "entity_type": _keyword(),
            "original_text": _text(),
            "normalized_label": _keyword(),
            "source_finding_id": _keyword(),
            "source_artifact_id": _keyword(),
            "needs_human_review": _boolean(),
        },
    )


def build_graph_evidence_index_spec() -> IndexSpec:
    """Build OpenSearch mapping for graph evidence nodes and edges."""
    return _index_spec(
        "translume_graph_evidence",
        {
            "document_id": _keyword(),
            "artifact_id": _keyword(),
            "case_id": _keyword(),
            "session_id": _keyword(),
            "record_type": _keyword(),
            "node_id": _keyword(),
            "edge_id": _keyword(),
            "label": _text(),
            "kind": _keyword(),
            "source_node_id": _keyword(),
            "target_node_id": _keyword(),
            "relation_type": _keyword(),
            "source": _keyword(),
            "source_entity_ids": _keyword(),
            "provenance": _object(),
        },
    )


def build_tool_output_index_spec() -> IndexSpec:
    """Build OpenSearch mapping for governed ToolUniverse outputs."""
    return _index_spec(
        "translume_tool_outputs",
        {
            "document_id": _keyword(),
            "artifact_id": _keyword(),
            "case_id": _keyword(),
            "session_id": _keyword(),
            "workflow": _keyword(),
            "input_entity_ids": _keyword(),
            "summary": _text(),
            "evidence_items": _object(enabled=False),
            "warnings": _text(),
            "requires_human_review": _boolean(),
        },
    )


def build_medea_reasoning_index_spec() -> IndexSpec:
    """Build OpenSearch mapping for bounded Medea reasoning artifacts."""
    return _index_spec(
        "translume_medea_reasoning",
        {
            "document_id": _keyword(),
            "artifact_id": _keyword(),
            "case_id": _keyword(),
            "session_id": _keyword(),
            "reasoning_mode": _keyword(),
            "summary": _text(),
            "supported_hypotheses": _text(),
            "weakened_hypotheses": _text(),
            "warnings": _text(),
            "requires_human_review": _boolean(),
        },
    )


def build_evidence_claim_index_spec() -> IndexSpec:
    """Build OpenSearch mapping for claim evidence cards."""
    return _index_spec(
        "translume_evidence_claims",
        {
            "document_id": _keyword(),
            "claim_id": _keyword(),
            "case_id": _keyword(),
            "session_id": _keyword(),
            "claim": _text(),
            "claim_class": _keyword(),
            "evidence_source": _keyword(),
            "limitations": _text(),
            "validation_status": _keyword(),
            "source_artifact_ids": _keyword(),
        },
    )


def build_artifact_provenance_index_spec() -> IndexSpec:
    """Build OpenSearch mapping for artifact provenance."""
    return _index_spec(
        "translume_artifact_provenance",
        {
            "document_id": _keyword(),
            "artifact_id": _keyword(),
            "artifact_type": _keyword(),
            "schema_name": _keyword(),
            "model_name": _keyword(),
            "prompt_hash": _keyword(),
            "schema_hash": _keyword(),
            "source_file_id": _keyword(),
            "source_artifact_ids": _keyword(),
            "created_at": _date(),
            "validation_status": _keyword(),
        },
    )


def build_validation_decision_index_spec() -> IndexSpec:
    """Build OpenSearch mapping for human validation decisions."""
    return _index_spec(
        "translume_validation_decisions",
        {
            "document_id": _keyword(),
            "claim_id": _keyword(),
            "case_id": _keyword(),
            "session_id": _keyword(),
            "status": _keyword(),
            "reviewer_note": _text(),
            "created_at": _date(),
        },
    )


def build_ledger_event_index_spec() -> IndexSpec:
    """Build OpenSearch mapping for ledger events."""
    return _index_spec(
        "translume_ledger_events",
        {
            "document_id": _keyword(),
            "event_id": _keyword(),
            "event_type": _keyword(),
            "case_id": _keyword(),
            "session_id": _keyword(),
            "artifact_id": _keyword(),
            "source_file_id": _keyword(),
            "created_at": _date(),
            "details": _object(),
        },
    )


def build_all_mvp_index_specs(vector_dimension: int) -> list[IndexSpec]:
    """Build every OpenSearch index spec required by the MVP.

    Acceptance criteria:
        1. Returns all required MVP persistence indexes.
        2. The document chunk index uses the configured vector dimension.
        3. Function is deterministic.
    """
    return [
        build_document_chunk_index_spec(vector_dimension),
        build_report_finding_index_spec(),
        build_artifact_index_spec(),
        build_normalized_entity_index_spec(),
        build_graph_evidence_index_spec(),
        build_tool_output_index_spec(),
        build_medea_reasoning_index_spec(),
        build_evidence_claim_index_spec(),
        build_artifact_provenance_index_spec(),
        build_validation_decision_index_spec(),
        build_ledger_event_index_spec(),
    ]
