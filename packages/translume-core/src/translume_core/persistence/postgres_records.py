from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid5

from pydantic import BaseModel

from translume_core.indexing.documents import artifact_bundle_to_opensearch_docs
from translume_core.persistence.postgres_schema import (
    TABLE_ARTIFACT_PROVENANCE,
    TABLE_ARTIFACTS,
    TABLE_CASE_SESSIONS,
    TABLE_DOCUMENT_CHUNKS,
    TABLE_EVIDENCE_CLAIMS,
    TABLE_GRAPH_EVIDENCE,
    TABLE_LEDGER_EVENTS,
    TABLE_MEDEA_REASONING,
    TABLE_NORMALIZED_ENTITIES,
    TABLE_REPORT_FINDINGS,
    TABLE_REVIEW_PACKETS,
    TABLE_SOURCE_FILES,
    TABLE_TOOL_OUTPUTS,
    TABLE_VALIDATION_DECISIONS,
)
from translume_schemas.export import ReviewPacketExport
from translume_schemas.graph import GraphEvidenceArtifact
from translume_schemas.ledger import LedgerEvent
from translume_schemas.session import CaseSession, StoredFile


@dataclass(frozen=True)
class PostgresRecord:
    """Database row for one Postgres metadata table.

    Attributes:
        table_name: Target table name.
        values: Column values keyed by column name.
    """

    table_name: str
    values: Mapping[str, object]


@dataclass(frozen=True)
class PostgresRecordBatch:
    """Collection of database records grouped by table name.

    Attributes:
        records_by_table: Mapping of table name to records.
    """

    records_by_table: Mapping[str, tuple[PostgresRecord, ...]]

    def counts(self) -> dict[str, int]:
        """Return record counts by table."""
        return {table: len(records) for table, records in self.records_by_table.items()}



def ingestion_metadata_to_postgres_records(
    session: CaseSession,
    stored_file: StoredFile,
    upload_event: LedgerEvent,
) -> PostgresRecordBatch:
    """Convert upload/session metadata into Postgres records.

    Acceptance criteria:
        1. Produces exactly one session row, one source-file row, and one
           upload ledger-event row.
        2. Preserves source-file path, size, hash, and original filename.
        3. Performs no database or filesystem I/O.
        4. Does not mutate session, stored_file, or upload_event.
    """
    records: dict[str, list[PostgresRecord]] = {table: [] for table in _table_order()}
    records[TABLE_CASE_SESSIONS].append(case_session_to_postgres_record(session))
    records[TABLE_SOURCE_FILES].append(stored_file_to_postgres_record(stored_file))
    records[TABLE_LEDGER_EVENTS].append(ledger_event_to_postgres_record(upload_event))
    return PostgresRecordBatch(
        records_by_table={table: tuple(items) for table, items in records.items()}
    )


def case_session_to_postgres_record(session: CaseSession) -> PostgresRecord:
    """Convert a case session into a Postgres record.

    Acceptance criteria:
        1. Preserves case_id, session_id, report_type, safety_mode, and
           created_at.
        2. Serializes the complete session payload as JSON.
        3. Performs no I/O.
        4. Does not mutate the session.
    """
    return _record(
        TABLE_CASE_SESSIONS,
        session_id=session.session_id,
        case_id=session.case_id,
        report_type=session.report_type,
        safety_mode=session.safety_mode,
        created_at=session.created_at,
        payload=_json(session),
    )


def stored_file_to_postgres_record(stored_file: StoredFile) -> PostgresRecord:
    """Convert source-file metadata into a Postgres record.

    Acceptance criteria:
        1. Preserves source_file_id, case_id, session_id, filename, path,
           size_bytes, and sha256.
        2. Serializes the complete stored-file payload as JSON.
        3. Performs no I/O.
        4. Does not mutate the stored file metadata.
    """
    return _record(
        TABLE_SOURCE_FILES,
        source_file_id=stored_file.source_file_id,
        case_id=stored_file.case_id,
        session_id=stored_file.session_id,
        filename=stored_file.filename,
        path=str(stored_file.path),
        size_bytes=stored_file.size_bytes,
        sha256=stored_file.sha256,
        payload=_json(stored_file),
    )


def review_packet_to_postgres_records(
    packet: ReviewPacketExport,
) -> PostgresRecordBatch:
    """Convert a review packet into durable Postgres metadata rows.

    Acceptance criteria:
        1. Produces rows for sessions, chunks, artifacts, findings, entities,
           graph evidence, tool outputs, Medea reasoning, claims, provenance,
           validation decisions, ledger events, and full review packet JSON.
        2. Preserves case/session/source identifiers in every domain row.
        3. Performs no database or filesystem I/O.
        4. Does not mutate the packet.

    Args:
        packet: Review packet export.

    Returns:
        Records grouped by table name.
    """
    bundle = packet.bundle
    records: dict[str, list[PostgresRecord]] = {table: [] for table in _table_order()}
    created_at = _first_event_time(bundle.ledger_events)
    records[TABLE_CASE_SESSIONS].append(
        _record(
            TABLE_CASE_SESSIONS,
            session_id=packet.session_id,
            case_id=packet.case_id,
            report_type=bundle.extraction.report_type,
            safety_mode="research_support_only",
            created_at=created_at,
            payload={
                "case_id": packet.case_id,
                "session_id": packet.session_id,
                "report_type": bundle.extraction.report_type,
            },
        )
    )
    records[TABLE_SOURCE_FILES].append(
        _record(
            TABLE_SOURCE_FILES,
            source_file_id=packet.source_file_id,
            case_id=packet.case_id,
            session_id=packet.session_id,
            filename=_upload_filename(bundle.ledger_events),
            path=_upload_path(bundle.ledger_events),
            size_bytes=_upload_size_bytes(bundle.ledger_events),
            sha256=_upload_sha256(bundle.ledger_events),
            payload={
                "source_file_id": packet.source_file_id,
                "filename": _upload_filename(bundle.ledger_events),
                "path": _upload_path(bundle.ledger_events),
                "size_bytes": _upload_size_bytes(bundle.ledger_events),
                "sha256": _upload_sha256(bundle.ledger_events),
            },
        )
    )
    for chunk in packet.chunks:
        records[TABLE_DOCUMENT_CHUNKS].append(
            _record(
                TABLE_DOCUMENT_CHUNKS,
                chunk_id=chunk.chunk_id,
                case_id=chunk.case_id,
                session_id=chunk.session_id,
                source_file_id=chunk.source_file_id,
                report_type=chunk.report_type,
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                section=chunk.section,
                chunk_type=chunk.chunk_type,
                needs_human_review=chunk.needs_human_review,
                payload=_json(chunk),
            )
        )
    for artifact_doc in artifact_bundle_to_opensearch_docs(packet):
        records[TABLE_ARTIFACTS].append(
            _record(
                TABLE_ARTIFACTS,
                artifact_id=artifact_doc["artifact_id"],
                artifact_type=artifact_doc["artifact_type"],
                case_id=packet.case_id,
                session_id=packet.session_id,
                source_file_id=packet.source_file_id,
                payload=artifact_doc["payload"],
            )
        )
    for finding in bundle.extraction.molecular_findings:
        records[TABLE_REPORT_FINDINGS].append(
            _record(
                TABLE_REPORT_FINDINGS,
                finding_id=finding.finding_id,
                artifact_id=bundle.extraction.artifact_id,
                case_id=packet.case_id,
                session_id=packet.session_id,
                source_file_id=packet.source_file_id,
                gene=finding.gene,
                alteration=finding.alteration,
                alteration_type=finding.alteration_type,
                confidence=finding.confidence,
                needs_human_review=finding.needs_human_review,
                payload=_json(finding),
            )
        )
    if bundle.entities is not None:
        for entity in bundle.entities.entities:
            records[TABLE_NORMALIZED_ENTITIES].append(
                _record(
                    TABLE_NORMALIZED_ENTITIES,
                    entity_id=entity.entity_id,
                    artifact_id=bundle.entities.artifact_id,
                    case_id=packet.case_id,
                    session_id=packet.session_id,
                    entity_type=entity.entity_type,
                    normalized_label=entity.normalized_label,
                    source_finding_id=entity.source_finding_id,
                    needs_human_review=entity.needs_human_review,
                    payload=_json(entity),
                )
            )
    if bundle.evidence_context is not None:
        _append_graph_records(
            records[TABLE_GRAPH_EVIDENCE],
            bundle.evidence_context.graph_evidence,
            case_id=packet.case_id,
            session_id=packet.session_id,
        )
        for tool in bundle.evidence_context.tool_outputs:
            records[TABLE_TOOL_OUTPUTS].append(
                _record(
                    TABLE_TOOL_OUTPUTS,
                    artifact_id=tool.artifact_id,
                    case_id=packet.case_id,
                    session_id=packet.session_id,
                    workflow=tool.workflow,
                    requires_human_review=tool.requires_human_review,
                    payload=_json(tool),
                )
            )
        medea = bundle.evidence_context.medea_reasoning
        records[TABLE_MEDEA_REASONING].append(
            _record(
                TABLE_MEDEA_REASONING,
                artifact_id=medea.artifact_id,
                case_id=packet.case_id,
                session_id=packet.session_id,
                reasoning_mode=medea.reasoning_mode,
                requires_human_review=medea.requires_human_review,
                payload=_json(medea),
            )
        )
    for claim in bundle.claims:
        records[TABLE_EVIDENCE_CLAIMS].append(
            _record(
                TABLE_EVIDENCE_CLAIMS,
                claim_id=claim.claim_id,
                case_id=packet.case_id,
                session_id=packet.session_id,
                claim_class=claim.claim_class,
                validation_status=claim.validation_status,
                payload=_json(claim),
            )
        )
    for provenance in bundle.provenance:
        records[TABLE_ARTIFACT_PROVENANCE].append(
            _record(
                TABLE_ARTIFACT_PROVENANCE,
                artifact_id=provenance.artifact_id,
                artifact_type=provenance.artifact_type,
                schema_name=provenance.schema_name,
                case_id=packet.case_id,
                session_id=packet.session_id,
                created_at=provenance.created_at,
                validation_status=provenance.validation_status,
                payload=_json(provenance),
            )
        )
    for decision in bundle.validation_decisions:
        records[TABLE_VALIDATION_DECISIONS].append(
            _record(
                TABLE_VALIDATION_DECISIONS,
                decision_id=decision.decision_id,
                claim_id=decision.claim_id,
                case_id=packet.case_id,
                session_id=packet.session_id,
                status=decision.status,
                reviewer_id=decision.reviewer_id,
                created_at=decision.created_at,
                payload=_json(decision),
            )
        )
    for event in bundle.ledger_events:
        records[TABLE_LEDGER_EVENTS].append(ledger_event_to_postgres_record(event))
    packet_id = stable_review_packet_id(packet)
    records[TABLE_REVIEW_PACKETS].append(
        _record(
            TABLE_REVIEW_PACKETS,
            packet_id=packet_id,
            case_id=packet.case_id,
            session_id=packet.session_id,
            source_file_id=packet.source_file_id,
            payload=_json(packet),
        )
    )
    return PostgresRecordBatch(
        records_by_table={table: tuple(items) for table, items in records.items()}
    )


def ledger_event_to_postgres_record(event: LedgerEvent) -> PostgresRecord:
    """Convert a ledger event into a Postgres record.

    Acceptance criteria:
        1. Preserves event ID, type, case/session, artifact/source references,
           timestamp, and full JSON payload.
        2. Performs no I/O.
        3. Does not mutate the event.
    """
    return _record(
        TABLE_LEDGER_EVENTS,
        event_id=event.event_id,
        event_type=event.event_type,
        case_id=event.case_id,
        session_id=event.session_id,
        artifact_id=event.artifact_id,
        source_file_id=event.source_file_id,
        created_at=event.created_at,
        payload=_json(event),
    )


def stable_review_packet_id(packet: ReviewPacketExport) -> str:
    """Return a stable review packet ID for case/session/source file."""
    seed = f"{packet.case_id}:{packet.session_id}:{packet.source_file_id}"
    return f"packet_{uuid5(NAMESPACE_URL, seed).hex}"


def _append_graph_records(
    records: list[PostgresRecord],
    graph: GraphEvidenceArtifact,
    *,
    case_id: str,
    session_id: str,
) -> None:
    for node in graph.nodes:
        records.append(
            _record(
                TABLE_GRAPH_EVIDENCE,
                record_id=f"{graph.artifact_id}:{node.node_id}",
                artifact_id=graph.artifact_id,
                case_id=case_id,
                session_id=session_id,
                record_type="node",
                relation_type=None,
                payload=_json(node),
            )
        )
    for edge in graph.edges:
        records.append(
            _record(
                TABLE_GRAPH_EVIDENCE,
                record_id=f"{graph.artifact_id}:{edge.edge_id}",
                artifact_id=graph.artifact_id,
                case_id=case_id,
                session_id=session_id,
                record_type="edge",
                relation_type=edge.relation_type,
                payload=_json(edge),
            )
        )


def _record(table_name: str, **values: object) -> PostgresRecord:
    return PostgresRecord(table_name=table_name, values=values)


def _json(value: object) -> object:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {str(key): _json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json(item) for item in value]
    if isinstance(value, tuple):
        return [_json(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _first_event_time(events: Sequence[LedgerEvent]) -> datetime:
    if events:
        return events[0].created_at
    return datetime.now(timezone.utc)


def _upload_filename(events: Sequence[LedgerEvent]) -> str | None:
    for event in events:
        filename = event.details.get("filename")
        if filename:
            return filename
    return None



def _upload_path(events: Sequence[LedgerEvent]) -> str | None:
    for event in events:
        path = event.details.get("storage_path")
        if path:
            return path
    return None


def _upload_size_bytes(events: Sequence[LedgerEvent]) -> int:
    for event in events:
        size_bytes = event.details.get("size_bytes")
        if size_bytes:
            try:
                return int(size_bytes)
            except ValueError:
                return 0
    return 0

def _upload_sha256(events: Sequence[LedgerEvent]) -> str | None:
    for event in events:
        sha256 = event.details.get("sha256")
        if sha256:
            return sha256
    return None


def _table_order() -> tuple[str, ...]:
    return (
        TABLE_CASE_SESSIONS,
        TABLE_SOURCE_FILES,
        TABLE_DOCUMENT_CHUNKS,
        TABLE_ARTIFACTS,
        TABLE_REPORT_FINDINGS,
        TABLE_NORMALIZED_ENTITIES,
        TABLE_GRAPH_EVIDENCE,
        TABLE_TOOL_OUTPUTS,
        TABLE_MEDEA_REASONING,
        TABLE_EVIDENCE_CLAIMS,
        TABLE_ARTIFACT_PROVENANCE,
        TABLE_VALIDATION_DECISIONS,
        TABLE_LEDGER_EVENTS,
        TABLE_REVIEW_PACKETS,
    )
