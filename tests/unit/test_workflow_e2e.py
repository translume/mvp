from __future__ import annotations

import json
import sys
from pathlib import Path
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


def _write_fake_optimuskg_repo(tmp_path: Path):
    """Create a tiny real OptimusKG-shaped package with parquet graph data."""
    import json
    import polars as pl

    repo = tmp_path / "OptimusKG"
    package_dir = repo / "packages" / "optimuskg" / "src" / "optimuskg"
    package_dir.mkdir(parents=True)
    cache_dir = tmp_path / "optimuskg_cache"
    cache_dir.mkdir()
    nodes_path = cache_dir / "largest_connected_component_nodes.parquet"
    edges_path = cache_dir / "largest_connected_component_edges.parquet"
    pl.DataFrame(
        [
            {
                "id": "GENE:CHEK2",
                "label": "gene",
                "properties": json.dumps({"name": "CHEK2", "synonyms": ["CHEK2"]}),
            },
            {
                "id": "GENE:MTAP",
                "label": "gene",
                "properties": json.dumps({"name": "MTAP", "synonyms": ["MTAP"]}),
            },
            {
                "id": "PATHWAY:DNA_DAMAGE_RESPONSE",
                "label": "pathway",
                "properties": json.dumps({"name": "DNA damage response"}),
            },
            {
                "id": "PATHWAY:METHYLATION_CONTEXT",
                "label": "pathway",
                "properties": json.dumps({"name": "Methylation context"}),
            },
        ]
    ).write_parquet(nodes_path)
    pl.DataFrame(
        [
            {
                "from": "GENE:CHEK2",
                "to": "PATHWAY:DNA_DAMAGE_RESPONSE",
                "label": "participates_in",
                "relation": "biolink:participates_in",
                "undirected": False,
                "properties": json.dumps({"source": "fixture_optimuskg_parquet"}),
            },
            {
                "from": "GENE:MTAP",
                "to": "PATHWAY:METHYLATION_CONTEXT",
                "label": "associated_with",
                "relation": "biolink:associated_with",
                "undirected": False,
                "properties": json.dumps({"source": "fixture_optimuskg_parquet"}),
            },
        ]
    ).write_parquet(edges_path)
    (package_dir / "__init__.py").write_text(
        "from pathlib import Path\n"
        f"_CACHE_DIR = Path({str(cache_dir)!r})\n"
        "def set_cache_dir(path):\n"
        "    global _CACHE_DIR\n"
        "    _CACHE_DIR = Path(path)\n"
        "def get_file(relative_path, force=False):\n"
        "    path = _CACHE_DIR / relative_path\n"
        "    if not path.exists():\n"
        "        raise FileNotFoundError(path)\n"
        "    return path\n",
        encoding="utf-8",
    )
    return repo, cache_dir


def _write_fake_tooluniverse_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "ToolUniverse"
    package = repo / "tooluniverse"
    package.mkdir(parents=True)
    package.joinpath("__init__.py").write_text(
        "class ToolUniverse:\n"
        "    def __init__(self):\n"
        "        self.all_tool_dict = {}\n"
        "    def load_tools(self, include_tools=None, quiet=True, **kwargs):\n"
        "        self.all_tool_dict = {name: {} for name in (include_tools or [])}\n"
        "    def run_one_function(self, function_call_json, use_cache=False, validate=True, stream_callback=None):\n"
        "        return {\"summary\": \"ToolUniverse executed \" + function_call_json.get(\"name\", \"\"), \"call\": function_call_json}\n",
        encoding="utf-8",
    )
    return repo


def _write_tooluniverse_workflow_config(tmp_path: Path, workflows: list[str]) -> Path:
    payload = {
        "required_workflows": workflows,
        "workflows": {
            workflow: {
                "steps": [
                    {
                        "tool_name": "PubMed_search_articles",
                        "required_context": ["literature_query"],
                        "arguments": {"query": "$literature_query", "limit": 1},
                    }
                ]
            }
            for workflow in workflows
        },
    }
    path = tmp_path / "tooluniverse_workflows.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


class RecordingVectorStore:
    def __init__(self) -> None:
        self.ensured: list[str] = []
        self.indexed: dict[str, list[dict[str, object]]] = {}

    async def ensure_index(self, index_name: str, body: dict[str, object]) -> None:
        self.ensured.append(index_name)

    async def index(self, index_name: str, documents: list[dict[str, object]]) -> None:
        self.indexed.setdefault(index_name, []).extend(documents)

    async def search(self, index_name: str, query: dict[str, object]) -> list[dict[str, object]]:
        # Test-only fake returns documents previously written to the requested
        # index. Production retrieval is performed by OpenSearchVectorStore.
        return [dict(document, _score=1.0) for document in self.indexed.get(index_name, [])]


class RecordingLedgerStore:
    def __init__(self) -> None:
        self.schema_ensured = 0
        self.packet_counts: dict[str, int] = {}
        self.events: list[object] = []

    async def ensure_schema(self) -> None:
        self.schema_ensured += 1

    async def persist_ingestion_metadata(self, session, stored_file, upload_event) -> dict[str, int]:
        counts = {
            "case_sessions": 1,
            "source_files": 1,
            "ledger_events": 1,
        }
        self.packet_counts = counts
        self.events.append(upload_event)
        return counts

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


class FakeStructuredModelProvider:
    """Test-only provider that returns schema-valid outputs.

    This is a test double only. Production workflow receives LocalVLLMProvider
    from FastAPI settings.
    """

    def __init__(self) -> None:
        self.schema_calls: list[str] = []

    async def structured_completion(
        self,
        *,
        model_name: str,
        system_prompt: str,
        user_prompt: str,
        schema_name: str,
        json_schema: dict[str, object],
    ) -> dict[str, object]:
        self.schema_calls.append(schema_name)
        artifact_id = _planned_artifact_id(user_prompt)
        if schema_name == "ReportExtractionOutput":
            return {
                "artifact_id": artifact_id,
                "report_type": "NGS",
                "disease": "Dedifferentiated chondrosarcoma",
                "specimen": "Soft tissue, chest wall",
                "tumor_percentage": "80%",
                "source_file_id": "source_file_ignored_by_schema_alignment",
                "needs_human_review": True,
                "negative_findings": ["No normal sample was received."],
                "assay_limitations": ["Research-use expression signals require review."],
                "molecular_findings": [
                    {
                        "finding_id": "finding_chek2",
                        "gene": "CHEK2",
                        "alteration": "c.846+4_846+7del Splice region variant-LOF VAF 85.6%",
                        "alteration_type": "variant",
                        "confidence": 0.90,
                        "needs_human_review": True,
                        "research_use_only": False,
                    },
                    {
                        "finding_id": "finding_cdkn2a",
                        "gene": "CDKN2A",
                        "alteration": "copy-number loss",
                        "alteration_type": "copy_number_loss",
                        "confidence": 0.88,
                        "needs_human_review": True,
                        "research_use_only": False,
                    },
                    {
                        "finding_id": "finding_cdkn2b",
                        "gene": "CDKN2B",
                        "alteration": "copy-number loss",
                        "alteration_type": "copy_number_loss",
                        "confidence": 0.88,
                        "needs_human_review": True,
                        "research_use_only": False,
                    },
                    {
                        "finding_id": "finding_lyn",
                        "gene": "LYN",
                        "alteration": "copy-number gain",
                        "alteration_type": "copy_number_gain",
                        "confidence": 0.88,
                        "needs_human_review": True,
                        "research_use_only": False,
                    },
                    {
                        "finding_id": "finding_mtap",
                        "gene": "MTAP",
                        "alteration": "copy-number loss",
                        "alteration_type": "copy_number_loss",
                        "confidence": 0.88,
                        "needs_human_review": True,
                        "research_use_only": False,
                    },
                    {
                        "finding_id": "finding_akt2",
                        "gene": "AKT2",
                        "alteration": "RNA expression overexpressed",
                        "alteration_type": "rna_expression",
                        "confidence": 0.72,
                        "needs_human_review": True,
                        "research_use_only": True,
                    },
                ],
            }
        if schema_name == "MolecularPhenotypeOutput":
            return {
                "artifact_id": artifact_id,
                "axes": [
                    {
                        "axis_id": "axis_source_backed_review",
                        "label": "Source-backed molecular behavior review",
                        "supporting_finding_ids": ["finding_mtap", "finding_cdkn2a"],
                        "evidence_class": "patient_specific_finding_with_graph_context",
                        "uncertainty": "Requires graph/tool/Medea evidence review before clinical interpretation.",
                        "validation_needed": True,
                    }
                ],
                "limitations": ["Model output is hypothesis-generating and requires human review."],
            }
        if schema_name == "TherapyEvidenceMatrixOutput":
            return {
                "artifact_id": artifact_id,
                "rows": [
                    {
                        "rank": 1,
                        "molecular_fit": "Source-backed molecular fit review",
                        "fit_label": "reviewable_molecular_fit",
                        "why_from_omics": "Report findings and evidence context identify a reviewable molecular axis.",
                        "evidence_basis": "patient_specific_finding_with_graph_tool_medea_context",
                        "limitations": "Requires clinician validation and is not treatment-directing.",
                        "required_validation": "Confirm source finding and pathway relevance before clinical interpretation.",
                        "not_a_recommendation": True,
                    }
                ],
            }
        if schema_name == "MechanismSankeyOutput":
            return {
                "artifact_id": artifact_id,
                "nodes": [
                    {"node_id": "finding", "label": "Report finding", "kind": "finding", "evidence_class": "patient_specific_finding"},
                    {"node_id": "mechanism", "label": "Mechanism under review", "kind": "mechanism", "evidence_class": "evidence_supported_context"},
                    {"node_id": "fit", "label": "Molecular fit review", "kind": "molecular_fit", "evidence_class": "model_derived_hypothesis"},
                    {"node_id": "validation", "label": "Validation needed", "kind": "validation", "evidence_class": "needs_review"},
                ],
                "links": [
                    {"source_node_id": "finding", "target_node_id": "mechanism", "value": 1.0, "claim_class": "patient_specific_finding", "validation_required": True, "source_artifact_ids": ["finding_mtap"]},
                    {"source_node_id": "mechanism", "target_node_id": "fit", "value": 1.0, "claim_class": "model_derived_hypothesis", "validation_required": True, "source_artifact_ids": ["artifact_graph"]},
                    {"source_node_id": "fit", "target_node_id": "validation", "value": 1.0, "claim_class": "speculative_requires_validation", "validation_required": True, "source_artifact_ids": ["artifact_tool"]},
                ],
            }
        if schema_name == "ConfirmatoryTestingOutput":
            return {
                "artifact_id": artifact_id,
                "tests": [
                    {
                        "test_id": "test_source_validation",
                        "question": "Is the source-backed molecular interpretation confirmed?",
                        "why_it_matters": "It determines whether the behavior hypothesis is credible for review.",
                        "positive_interpretation": "Increases confidence in the molecular axis under review.",
                        "negative_interpretation": "Lowers confidence and should weaken the claim.",
                        "priority": "high",
                        "evidence_gap": "Confirmatory evidence is required before interpretation.",
                        "source_claim_ids": [],
                    }
                ],
                "must_not_assume": ["Do not assume treatment actionability from molecular fit rows."],
            }
        if schema_name == "TumorBehaviorModelOutput":
            return {
                "artifact_id": artifact_id,
                "state_evidence": [
                    {
                        "state_label": "proliferative",
                        "supporting_findings": ["finding_cdkn2a"],
                        "graph_support": ["artifact_graph"],
                        "tool_support": ["artifact_tool"],
                        "medea_support": ["artifact_medea"],
                        "evidence_class": "model_derived_hypothesis",
                        "uncertainty": "Requires validation before clinical interpretation.",
                        "validation_needed": True,
                    }
                ],
                "transition_hypotheses": [
                    {
                        "from_state": "proliferative",
                        "to_state": "stress_adapted_survival",
                        "rationale": "Evidence context suggests a hypothesis requiring review; no probability is claimed.",
                        "supporting_artifacts": ["artifact_graph", "artifact_tool", "artifact_medea"],
                        "confidence_label": "needs_review",
                        "validation_status": "needs_review",
                        "hypothesis_generating": True,
                    }
                ],
                "limitations": ["No transition probability, treatment recommendation, or outcome prediction is generated."],
            }
        if schema_name == "ClaimEvidenceListOutput":
            return {
                "artifact_id": artifact_id,
                "claims": [
                    {
                        "claim_id": "claim_source_backed_behavior",
                        "claim": "The report supports a source-backed tumor-behavior hypothesis requiring human review.",
                        "claim_class": "model_derived_hypothesis",
                        "source_artifact_ids": _artifact_source_ids_from_prompt(user_prompt),
                        "evidence_source": "report_graph_tool_medea_context",
                        "relevance": "Connects molecular findings to disease-behavior review.",
                        "limitations": "Requires clinician validation and is not treatment-directing.",
                        "validation_status": "needs_review",
                    }
                ],
            }
        if schema_name == "ClinicalNarrativeCompilerOutput":
            return {
                "artifact_id": artifact_id,
                "markdown": "# Translume Review Packet\n\nThis report generated source-backed molecular findings, evidence-context artifacts, and tumor-behavior hypotheses for clinician review. This is not a treatment recommendation.",
                "source_artifact_ids": _artifact_source_ids_from_prompt(user_prompt),
                "safety_note": "Research support only; not a diagnosis or treatment recommendation.",
            }
        raise AssertionError(f"Unexpected schema: {schema_name}")


def _planned_artifact_id(user_prompt: str) -> str:
    lines = user_prompt.splitlines()
    for index, line in enumerate(lines):
        if line.strip() == "The artifact_id must be exactly:" and index + 1 < len(lines):
            return lines[index + 1].strip()
    raise AssertionError("planned artifact id missing from prompt")


def _artifact_source_ids_from_prompt(user_prompt: str) -> list[str]:
    payload = _payload_json_from_prompt(user_prompt)
    bundle = payload.get("clinical_artifact_bundle", payload)
    ids: list[str] = []

    def collect(value):
        if isinstance(value, dict):
            for key in ("artifact_id", "claim_id"):
                item = value.get(key)
                if isinstance(item, str) and item not in ids:
                    ids.append(item)
            for item in value.values():
                collect(item)
        elif isinstance(value, list):
            for item in value:
                collect(item)

    collect(bundle)
    return ids


def _payload_json_from_prompt(user_prompt: str) -> dict[str, object]:
    payload_text = user_prompt.split("Payload JSON:", 1)[1]
    start = payload_text.find("{")
    if start < 0:
        raise AssertionError("payload JSON object missing from prompt")
    depth = 0
    in_string = False
    escape = False
    for offset, char in enumerate(payload_text[start:], start=start):
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return json.loads(payload_text[start : offset + 1])
    raise AssertionError("payload JSON object was not closed")


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
async def test_process_report_pdf_strict_mims_with_local_artifacts(tmp_path, monkeypatch) -> None:
    monkeypatch.delitem(sys.modules, "optimuskg", raising=False)
    optimuskg_repo, optimuskg_cache = _write_fake_optimuskg_repo(tmp_path)
    tool_workflows = [
        "literature_validation",
        "pathway_context",
        "target_context",
        "variant_context",
        "trial_context_review",
    ]
    tooluniverse_repo = _write_fake_tooluniverse_repo(tmp_path)
    tooluniverse_config = _write_tooluniverse_workflow_config(tmp_path, tool_workflows)
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
    model_provider = FakeStructuredModelProvider()
    providers = TranslumeWorkflowProviders(
        graph_provider=OptimusKGGraphProvider(optimuskg_repo, cache_dir=optimuskg_cache, max_edges=10),
        tool_provider=ToolUniverseProvider(
            tooluniverse_repo,
            tooluniverse_config,
        ),
        reasoning_provider_factory=lambda _context: MedeaReasoningProvider(reasoning_json),
        vector_store=vector_store,
        ledger_store=ledger_store,
        model_provider=model_provider,
    )
    packet = await process_report_pdf(
        filename="report.pdf",
        content=_pdf_bytes(),
        report_type="NGS",
        config=TranslumeWorkflowConfig(
            storage_root=tmp_path / "uploads",
            require_mims=True,
            require_docling=False,
            vllm_model="test-local-vllm-model",
        ),
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
    assert packet.bundle.narrative_containment is not None
    assert packet.bundle.narrative_containment.passed is True
    assert "not a treatment recommendation" in packet.bundle.narrative.markdown.lower()
    assert model_provider.schema_calls == [
        "ReportExtractionOutput",
        "MolecularPhenotypeOutput",
        "TherapyEvidenceMatrixOutput",
        "MechanismSankeyOutput",
        "ConfirmatoryTestingOutput",
        "TumorBehaviorModelOutput",
        "ClaimEvidenceListOutput",
        "ClinicalNarrativeCompilerOutput",
    ]
    assert "translume_document_chunks" in vector_store.indexed
    assert "translume_evidence_claims" in vector_store.indexed
    event_types = [event.event_type for event in packet.bundle.ledger_events]
    assert "document_chunk_opensearch_indexing_succeeded" in event_types
    assert "report_extraction_chunk_retrieval_succeeded" in event_types
    assert "narrative_fact_containment_succeeded" in event_types
    assert event_types.index("document_chunk_opensearch_indexing_succeeded") < event_types.index("report_extraction_started")
    assert any(event.event_type == "opensearch_persisted" for event in packet.bundle.ledger_events)
    assert any(event.event_type == "postgres_metadata_persisted" for event in packet.bundle.ledger_events)
    assert ledger_store.schema_ensured >= 1
    assert any(event.event_type == "report_uploaded" for event in ledger_store.events)
    assert any(event.event_type == "document_extraction_started" for event in ledger_store.events)
    assert any(event.event_type == "document_extraction_succeeded" for event in ledger_store.events)


@pytest.mark.asyncio
async def test_process_report_pdf_fails_without_local_model_provider(tmp_path) -> None:
    vector_store = RecordingVectorStore()
    ledger_store = RecordingLedgerStore()
    providers = TranslumeWorkflowProviders(
        graph_provider=None,
        tool_provider=None,
        reasoning_provider_factory=None,
        vector_store=vector_store,
        ledger_store=ledger_store,
    )
    with pytest.raises(RuntimeError, match="Local vLLM structured-output model provider is required"):
        await process_report_pdf(
            filename="report.pdf",
            content=_pdf_bytes(),
            report_type="NGS",
            config=TranslumeWorkflowConfig(
                storage_root=tmp_path / "uploads",
                require_mims=False,
                require_docling=False,
                vllm_model="test-local-vllm-model",
            ),
            providers=providers,
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
