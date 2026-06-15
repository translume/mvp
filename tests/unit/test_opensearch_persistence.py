from __future__ import annotations

from datetime import datetime, timezone

import pytest

from translume_core.indexing.documents import review_packet_to_index_batches
from translume_core.indexing.index_specs import build_all_mvp_index_specs
from translume_core.indexing.persistence import persist_review_packet_to_opensearch
from translume_schemas.claims import ClaimEvidenceOutput
from translume_schemas.document import DocumentChunk
from translume_schemas.evidence import EvidenceContextBundle
from translume_schemas.export import ClinicalArtifactBundle, ReviewPacketExport
from translume_schemas.extraction import MolecularFinding, ReportExtractionOutput
from translume_schemas.graph import GraphEdge, GraphEvidenceArtifact, GraphNode
from translume_schemas.ledger import LedgerEvent
from translume_schemas.medea import MedeaReasoningArtifact
from translume_schemas.provenance import ArtifactProvenance
from translume_schemas.tools import ToolRunArtifact


class RecordingVectorStore:
    def __init__(self) -> None:
        self.ensured: list[str] = []
        self.indexed: dict[str, list[dict[str, object]]] = {}

    async def ensure_index(self, index_name: str, body: dict[str, object]) -> None:
        self.ensured.append(index_name)

    async def index(self, index_name: str, documents: list[dict[str, object]]) -> None:
        self.indexed.setdefault(index_name, []).extend(documents)

    async def search(self, index_name: str, query: dict[str, object]) -> list[dict[str, object]]:
        return []


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
        molecular_findings=[
            MolecularFinding(
                finding_id="finding1",
                gene="CHEK2",
                alteration="LOF",
                alteration_type="variant",
                source_page=1,
                source_text="CHEK2 LOF",
                source_chunk_id="chunk1",
                confidence=0.9,
            )
        ],
        source_file_id="file1",
    )
    graph = GraphEvidenceArtifact(
        artifact_id="artifact_graph",
        source_entity_ids=["entity1"],
        nodes=[GraphNode(node_id="CHEK2", label="CHEK2", kind="gene", source="optimuskg")],
        edges=[
            GraphEdge(
                edge_id="edge1",
                source_node_id="CHEK2",
                target_node_id="DDR",
                relation_type="participates_in",
                source="optimuskg",
            )
        ],
    )
    tool = ToolRunArtifact(
        artifact_id="artifact_tool",
        workflow="literature_validation",
        input_entity_ids=["entity1"],
        summary="Evidence requires review.",
        evidence_items=[{"source": "local"}],
    )
    medea = MedeaReasoningArtifact(
        artifact_id="artifact_medea",
        reasoning_mode="bounded_review_support",
        summary="Hypothesis support only.",
        supported_hypotheses=["CHEK2 context"],
        weakened_hypotheses=[],
    )
    context = EvidenceContextBundle(
        artifact_id="artifact_context",
        extraction=extraction,
        graph_evidence=graph,
        tool_outputs=[tool],
        medea_reasoning=medea,
    )
    claim = ClaimEvidenceOutput(
        claim_id="claim1",
        claim="CHEK2 finding requires review.",
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
        details={},
    )
    bundle = ClinicalArtifactBundle(
        case_id="case1",
        session_id="session1",
        extraction=extraction,
        evidence_context=context,
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


def test_all_index_specs_include_required_indexes() -> None:
    names = {spec["index_name"] for spec in build_all_mvp_index_specs(384)}
    assert "translume_document_chunks" in names
    assert "translume_graph_evidence" in names
    assert "translume_tool_outputs" in names
    assert "translume_medea_reasoning" in names
    assert "translume_evidence_claims" in names


def test_review_packet_to_index_batches_preserves_evidence() -> None:
    batches = review_packet_to_index_batches(_packet())
    assert len(batches["translume_document_chunks"]) == 1
    assert len(batches["translume_report_findings"]) == 1
    assert len(batches["translume_graph_evidence"]) == 2
    assert len(batches["translume_tool_outputs"]) == 1
    assert len(batches["translume_medea_reasoning"]) == 1
    assert batches["translume_evidence_claims"][0]["validation_status"] == "needs_review"


@pytest.mark.asyncio
async def test_persist_review_packet_to_opensearch_indexes_batches() -> None:
    store = RecordingVectorStore()
    result = await persist_review_packet_to_opensearch(
        _packet(),
        store,
        vector_dimension=384,
    )
    assert "translume_document_chunks" in store.ensured
    assert "translume_document_chunks" in store.indexed
    assert result.indexed_documents_by_index["translume_graph_evidence"] == 2
