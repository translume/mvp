from __future__ import annotations

import json
from datetime import datetime, timezone

import fitz
import pytest

from translume_adapters.graph_providers.optimuskg_graph_provider import OptimusKGGraphProvider
from translume_adapters.reasoning_providers.medea_reasoning_provider import MedeaReasoningProvider
from translume_adapters.tool_providers.tooluniverse_provider import ToolUniverseProvider
from translume_core.workflow import (
    TranslumeWorkflowConfig,
    TranslumeWorkflowProviders,
    process_report_pdf,
)




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


class RecordingLedgerStore:
    def __init__(self) -> None:
        self.schema_ensured = 0
        self.packet_counts: dict[str, int] = {}
        self.events: list[object] = []

    async def ensure_schema(self) -> None:
        self.schema_ensured += 1

    async def persist_review_packet(self, packet) -> dict[str, int]:
        counts = {
            "ledger_events": len(packet.bundle.ledger_events),
            "artifacts": 1,
            "review_packets": 1,
        }
        self.packet_counts = counts
        return counts

    async def append_ledger_event(self, event) -> None:
        self.events.append(event)


def _pdf_bytes() -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text(
        (72, 72),
        "Diagnosis Dedifferentiated chondrosarcoma\n"
        "Tumor specimen Soft tissue, chest wall\n"
        "Tumor Percentage: 80%\n"
        "GENOMIC VARIANTS\n"
        "CHEK2 c.846+4_846+7del Splice region variant-LOF VAF 85.6%\n"
        "CDKN2A Copy number loss\n"
        "CDKN2B Copy number loss\n"
        "LYN Copy number gain\n"
        "MTAP Copy number loss\n"
        "No normal sample was received.\n"
        "EXPRESSION DETAILS\n"
        "AKT2 Overexpressed\n"
        "CDKN2B Underexpressed\n"
        "FOR RESEARCH USE ONLY.\n",
    )
    data = doc.tobytes()
    doc.close()
    return data


@pytest.mark.asyncio
async def test_process_report_pdf_strict_mims_with_local_artifacts(tmp_path) -> None:
    edge_csv = tmp_path / "edges.csv"
    edge_csv.write_text(
        "subject,subject_kind,relation_type,object,object_kind,source\n"
        "MTAP,gene,associated_with,METHYLATION_DEPENDENCY,pathway,local_optimuskg\n"
        "CDKN2A,gene,participates_in,CELL_CYCLE,pathway,local_optimuskg\n",
        encoding="utf-8",
    )
    evidence_dir = tmp_path / "tool"
    evidence_dir.mkdir()
    for workflow in [
        "literature_validation",
        "pathway_context",
        "target_context",
        "variant_context",
        "trial_context_review",
    ]:
        (evidence_dir / f"{workflow}.json").write_text(
            json.dumps(
                {
                    "summary": f"{workflow} evidence requires review.",
                    "evidence_items": [{"source": "local_tooluniverse"}],
                }
            ),
            encoding="utf-8",
        )
    reasoning_json = tmp_path / "reasoning.json"
    reasoning_json.write_text(
        json.dumps(
            {
                "reasoning_mode": "bounded_review_support",
                "summary": "Medea bounded reasoning supports review only.",
                "supported_hypotheses": ["MTAP context requires review"],
                "weakened_hypotheses": [],
            }
        ),
        encoding="utf-8",
    )
    vector_store = RecordingVectorStore()
    ledger_store = RecordingLedgerStore()
    providers = TranslumeWorkflowProviders(
        graph_provider=OptimusKGGraphProvider(edge_csv),
        tool_provider=ToolUniverseProvider(
            {
                "literature_validation",
                "pathway_context",
                "target_context",
                "variant_context",
                "trial_context_review",
            },
            evidence_dir,
        ),
        reasoning_provider_factory=lambda _context: MedeaReasoningProvider(reasoning_json),
        vector_store=vector_store,
        ledger_store=ledger_store,
    )
    packet = await process_report_pdf(
        filename="report.pdf",
        content=_pdf_bytes(),
        report_type="NGS",
        config=TranslumeWorkflowConfig(storage_root=tmp_path / "uploads", require_mims=True, require_docling=False),
        providers=providers,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    genes = {finding.gene for finding in packet.bundle.extraction.molecular_findings}
    assert {"CHEK2", "CDKN2A", "CDKN2B", "LYN", "MTAP", "AKT2"} <= genes
    assert packet.bundle.evidence_context is not None
    assert packet.bundle.evidence_context.graph_evidence.edges
    assert len(packet.bundle.evidence_context.tool_outputs) == 5
    assert packet.bundle.tumor_behavior is not None
    assert packet.bundle.confirmatory is not None
    assert packet.bundle.sankey is not None
    assert packet.bundle.claims
    assert packet.bundle.narrative is not None
    assert "not a treatment recommendation" in packet.bundle.narrative.markdown.lower()
    assert "translume_document_chunks" in vector_store.indexed
    assert "translume_evidence_claims" in vector_store.indexed
    assert any(event.event_type == "opensearch_persisted" for event in packet.bundle.ledger_events)
    assert any(event.event_type == "postgres_metadata_persisted" for event in packet.bundle.ledger_events)
    assert ledger_store.schema_ensured == 1
