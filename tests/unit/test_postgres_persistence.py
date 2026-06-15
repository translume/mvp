from __future__ import annotations

from datetime import datetime, timezone

import pytest

from translume_core.persistence.postgres_persistence import persist_review_packet_to_postgres
from translume_core.persistence.postgres_records import review_packet_to_postgres_records
from translume_core.persistence.postgres_schema import (
    MVP_POSTGRES_TABLES,
    create_table_sql,
    upsert_sql,
)
from translume_schemas.claims import ClaimEvidenceOutput
from translume_schemas.document import DocumentChunk
from translume_schemas.export import ClinicalArtifactBundle, ReviewPacketExport
from translume_schemas.extraction import MolecularFinding, ReportExtractionOutput
from translume_schemas.ledger import LedgerEvent
from translume_schemas.provenance import ArtifactProvenance


class RecordingLedgerStore:
    def __init__(self) -> None:
        self.ensured = 0
        self.packet: ReviewPacketExport | None = None

    async def ensure_schema(self) -> None:
        self.ensured += 1

    async def persist_review_packet(self, packet: ReviewPacketExport) -> dict[str, int]:
        self.packet = packet
        return review_packet_to_postgres_records(packet).counts()

    async def append_ledger_event(self, event: LedgerEvent) -> None:
        raise AssertionError("not used in this test")


def _packet() -> ReviewPacketExport:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    chunk = DocumentChunk(
        chunk_id="chunk1",
        case_id="case1",
        session_id="session1",
        source_file_id="file1",
        report_type="NGS",
        page_start=1,
        page_end=1,
        section="GENOMIC VARIANTS",
        chunk_type="molecular_finding",
        source_text="CHEK2 LOF",
        source_block_ids=["block1"],
        needs_human_review=True,
    )
    extraction = ReportExtractionOutput(
        artifact_id="artifact_report",
        report_type="NGS",
        source_file_id="file1",
        molecular_findings=[
            MolecularFinding(
                finding_id="finding1",
                gene="CHEK2",
                alteration="LOF",
                alteration_type="variant",
                confidence=0.9,
            )
        ],
    )
    claim = ClaimEvidenceOutput(
        claim_id="claim1",
        claim="CHEK2 LOF is report-derived and requires review.",
        claim_class="patient_specific_finding",
        source_artifact_ids=["artifact_report"],
        evidence_source="report",
        relevance="reviewable",
        limitations="none",
    )
    provenance = ArtifactProvenance(
        artifact_id="artifact_report",
        artifact_type="report_extraction",
        schema_name="ReportExtractionOutput",
        source_file_id="file1",
        source_artifact_ids=[],
        created_at=now,
    )
    ledger = LedgerEvent(
        event_id="event1",
        event_type="report_uploaded",
        case_id="case1",
        session_id="session1",
        source_file_id="file1",
        created_at=now,
        details={"filename": "report.pdf", "sha256": "abc"},
    )
    bundle = ClinicalArtifactBundle(
        case_id="case1",
        session_id="session1",
        extraction=extraction,
        claims=[claim],
        provenance=[provenance],
        ledger_events=[ledger],
    )
    return ReviewPacketExport(
        case_id="case1",
        session_id="session1",
        source_file_id="file1",
        chunks=[chunk],
        bundle=bundle,
    )


def test_postgres_schema_sql_is_generated_for_all_tables() -> None:
    statements = [create_table_sql(table) for table in MVP_POSTGRES_TABLES]
    assert all(statement.startswith("CREATE TABLE IF NOT EXISTS") for statement in statements)
    assert any("ledger_events" in statement for statement in statements)
    assert all("PRIMARY KEY" in statement for statement in statements)


def test_upsert_sql_uses_named_placeholders() -> None:
    sql = upsert_sql(MVP_POSTGRES_TABLES[0])
    assert "%(" in sql
    assert "ON CONFLICT" in sql


def test_review_packet_to_postgres_records_includes_core_tables() -> None:
    records = review_packet_to_postgres_records(_packet())
    counts = records.counts()
    assert counts["case_sessions"] == 1
    assert counts["source_files"] == 1
    assert counts["document_chunks"] == 1
    assert counts["artifacts"] >= 1
    assert counts["report_findings"] == 1
    assert counts["evidence_claims"] == 1
    assert counts["ledger_events"] == 1
    assert counts["review_packets"] == 1


@pytest.mark.asyncio
async def test_persist_review_packet_to_postgres_uses_store_boundary() -> None:
    store = RecordingLedgerStore()
    result = await persist_review_packet_to_postgres(_packet(), store)
    assert store.ensured == 1
    assert store.packet is not None
    assert result.persisted_records_by_table["review_packets"] == 1
