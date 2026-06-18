from __future__ import annotations

from translume_core.compiler.claim_evidence import classify_evidence_strength
from translume_core.compiler.entity_normalization import normalize_report_entities
from translume_core.compiler.evidence_context import combine_evidence_sources
import pytest

from translume_core.compiler.tumor_behavior import (
    LegacyTumorBehaviorDisabledError,
    generate_tumor_behavior_model_from_context,
)
from translume_schemas.extraction import MolecularFinding, ReportExtractionOutput
from translume_schemas.graph import GraphEdge, GraphEvidenceArtifact, GraphNode
from translume_schemas.medea import MedeaReasoningArtifact
from translume_schemas.tools import ToolRunArtifact


def _extraction() -> ReportExtractionOutput:
    return ReportExtractionOutput(
        artifact_id="artifact_extraction",
        report_type="NGS",
        disease="dedifferentiated chondrosarcoma",
        specimen="soft tissue, chest wall",
        tumor_percentage="80%",
        source_file_id="file_a",
        molecular_findings=[
            MolecularFinding(finding_id="f1", gene="CHEK2", alteration="LOF", alteration_type="variant", confidence=0.9),
            MolecularFinding(finding_id="f2", gene="MTAP", alteration="copy-number loss", alteration_type="copy_number_loss", confidence=0.9),
        ],
    )


def test_entity_normalization_links_to_findings() -> None:
    entities = normalize_report_entities(_extraction(), case_id="case", session_id="sess")
    labels = {entity.normalized_label for entity in entities.entities}
    assert "CHEK2" in labels
    assert "MTAP" in labels
    assert "dedifferentiated chondrosarcoma" in labels


def test_evidence_context_claims_and_tumor_behavior() -> None:
    extraction = _extraction()
    graph = GraphEvidenceArtifact(
        artifact_id="artifact_graph",
        source_entity_ids=["e1"],
        nodes=[GraphNode(node_id="n1", label="CHEK2", kind="gene", source="test")],
        edges=[GraphEdge(edge_id="edge1", source_node_id="n1", target_node_id="n1", relation_type="self", source="test")],
    )
    tool = ToolRunArtifact(artifact_id="artifact_tool", workflow="literature_validation", input_entity_ids=["e1"], summary="Tool evidence requires review.", evidence_items=[])
    medea = MedeaReasoningArtifact(artifact_id="artifact_medea", reasoning_mode="bounded", summary="Medea reasoning requires review.", supported_hypotheses=[], weakened_hypotheses=[])
    context = combine_evidence_sources(extraction, graph, [tool], medea)
    claims = classify_evidence_strength(context)
    assert any(claim.claim_class == "patient_specific_finding" for claim in claims)
    with pytest.raises(LegacyTumorBehaviorDisabledError):
        generate_tumor_behavior_model_from_context(context)
