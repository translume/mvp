from __future__ import annotations

from datetime import datetime, timezone

import pytest

from translume_core.validation.review import (
    ClaimValidationError,
    apply_validation_decision_to_packet,
    build_validation_decision,
    validation_cards_from_packet,
)
from translume_schemas.claims import ClaimEvidenceOutput
from translume_schemas.document import DocumentChunk
from translume_schemas.export import ClinicalArtifactBundle, ReviewPacketExport
from translume_schemas.extraction import MolecularFinding, ReportExtractionOutput
from translume_schemas.ledger import LedgerEvent


def _packet() -> ReviewPacketExport:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
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
        limitations="Requires human validation.",
    )
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
    event = LedgerEvent(
        event_id="event1",
        event_type="report_uploaded",
        case_id="case1",
        session_id="session1",
        source_file_id="file1",
        created_at=now,
        details={"filename": "report.pdf"},
    )
    bundle = ClinicalArtifactBundle(
        case_id="case1",
        session_id="session1",
        extraction=extraction,
        claims=[claim],
        ledger_events=[event],
    )
    return ReviewPacketExport(
        case_id="case1",
        session_id="session1",
        source_file_id="file1",
        chunks=[chunk],
        bundle=bundle,
    )


def test_validation_cards_from_packet_returns_real_claims() -> None:
    cards = validation_cards_from_packet(_packet())
    assert len(cards) == 1
    assert cards[0].claim_id == "claim1"
    assert cards[0].validation_status == "needs_review"


def test_build_validation_decision_normalizes_blank_fields() -> None:
    now = datetime(2026, 1, 2, tzinfo=timezone.utc)
    decision = build_validation_decision(
        claim_id=" claim1 ",
        status="validated",
        reviewer_id=" ",
        reviewer_note=" ",
        created_at=now,
    )
    assert decision.claim_id == "claim1"
    assert decision.status == "validated"
    assert decision.reviewer_id is None
    assert decision.reviewer_note is None


def test_apply_validation_decision_updates_claim_and_ledger_without_mutation() -> None:
    packet = _packet()
    now = datetime(2026, 1, 2, tzinfo=timezone.utc)
    decision = build_validation_decision(
        claim_id="claim1",
        status="rejected",
        reviewer_id="reviewer-a",
        reviewer_note="Source support is insufficient.",
        created_at=now,
    )
    updated = apply_validation_decision_to_packet(packet, decision, created_at=now)
    assert packet.bundle.claims[0].validation_status == "needs_review"
    assert updated.bundle.claims[0].validation_status == "rejected"
    assert updated.bundle.validation_decisions[0].decision_id == decision.decision_id
    assert updated.bundle.ledger_events[-1].event_type == "claim_validation_decision_recorded"
    assert updated.bundle.ledger_events[-1].details["reviewer_id"] == "reviewer-a"


def test_apply_validation_decision_requires_existing_claim() -> None:
    now = datetime(2026, 1, 2, tzinfo=timezone.utc)
    decision = build_validation_decision(
        claim_id="missing",
        status="validated",
        created_at=now,
    )
    with pytest.raises(ClaimValidationError):
        apply_validation_decision_to_packet(_packet(), decision, created_at=now)
