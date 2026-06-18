from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from translume_core.compiler.structured_model_artifacts import (
    StructuredArtifactGenerationError,
    generate_tumor_behavior_model_with_model,
)
from translume_schemas.confirmatory import ConfirmatoryTest, ConfirmatoryTestingOutput
from translume_schemas.evidence import EvidenceContextBundle
from translume_schemas.extraction import MolecularFinding, ReportExtractionOutput
from translume_schemas.graph import GraphEdge, GraphEvidenceArtifact, GraphNode
from translume_schemas.matrix import MolecularFitRow, TherapyEvidenceMatrixOutput
from translume_schemas.medea import MedeaReasoningArtifact
from translume_schemas.phenotype import BiologicalAxis, MolecularPhenotypeOutput
from translume_schemas.sankey import MechanismSankeyOutput, SankeyLink, SankeyNode
from translume_schemas.tools import ToolRunArtifact


class TumorBehaviorModelProvider:
    """Test-only structured-output model provider.

    This provider is a test double only. The production path receives
    LocalVLLMProvider from FastAPI settings and fails if it is absent.
    """

    def __init__(self, output: dict[str, object]) -> None:
        self.output = output
        self.schema_names: list[str] = []

    async def structured_completion(
        self,
        *,
        model_name: str,
        system_prompt: str,
        user_prompt: str,
        schema_name: str,
        json_schema: dict[str, object],
    ) -> dict[str, object]:
        self.schema_names.append(schema_name)
        payload = dict(self.output)
        payload["artifact_id"] = _planned_artifact_id(user_prompt)
        return payload


def _context() -> EvidenceContextBundle:
    extraction = ReportExtractionOutput(
        artifact_id="artifact_extraction",
        report_type="NGS",
        disease="dedifferentiated chondrosarcoma",
        source_file_id="source_file_1",
        molecular_findings=[
            MolecularFinding(
                finding_id="finding_mtap",
                gene="MTAP",
                alteration="copy-number loss",
                alteration_type="copy_number_loss",
                source_text="MTAP copy-number loss",
                confidence=0.9,
            ),
            MolecularFinding(
                finding_id="finding_cdkn2a",
                gene="CDKN2A",
                alteration="copy-number loss",
                alteration_type="copy_number_loss",
                source_text="CDKN2A copy-number loss",
                confidence=0.9,
            ),
        ],
    )
    graph = GraphEvidenceArtifact(
        artifact_id="artifact_graph",
        source_entity_ids=["entity_mtap"],
        nodes=[
            GraphNode(
                node_id="node_mtap",
                label="MTAP",
                kind="gene",
                source="optimuskg",
            ),
            GraphNode(
                node_id="node_prmt5",
                label="PRMT5 dependency context",
                kind="pathway",
                source="optimuskg",
            ),
        ],
        edges=[
            GraphEdge(
                edge_id="edge_mtap_prmt5",
                source_node_id="node_mtap",
                target_node_id="node_prmt5",
                relation_type="related_to",
                source="optimuskg",
            )
        ],
    )
    tool = ToolRunArtifact(
        artifact_id="artifact_tool_literature_validation",
        workflow="literature_validation",
        input_entity_ids=["entity_mtap"],
        summary="ToolUniverse literature_validation reviewed MTAP and PRMT5 context.",
        evidence_items=[{"entity": "MTAP", "context": "PRMT5 review"}],
    )
    medea = MedeaReasoningArtifact(
        artifact_id="artifact_medea",
        reasoning_mode="bounded_review_support",
        summary="Medea bounded reasoning supports MTAP hypothesis review.",
        supported_hypotheses=["MTAP context requires review"],
        weakened_hypotheses=[],
    )
    return EvidenceContextBundle(
        artifact_id="artifact_context",
        extraction=extraction,
        graph_evidence=graph,
        tool_outputs=[tool],
        medea_reasoning=medea,
    )


def _phenotype() -> MolecularPhenotypeOutput:
    return MolecularPhenotypeOutput(
        artifact_id="artifact_phenotype",
        axes=[
            BiologicalAxis(
                axis_id="axis_mtap",
                label="MTAP methylation dependency review axis",
                supporting_finding_ids=["finding_mtap"],
                evidence_class="model_derived_hypothesis",
                uncertainty="Requires validation before clinical interpretation.",
                validation_needed=True,
            )
        ],
    )


def _matrix() -> TherapyEvidenceMatrixOutput:
    return TherapyEvidenceMatrixOutput(
        artifact_id="artifact_matrix",
        rows=[
            MolecularFitRow(
                rank=1,
                molecular_fit="MTAP PRMT5 review context",
                fit_label="reviewable_molecular_fit",
                why_from_omics="MTAP copy-number loss is present in the report.",
                evidence_basis="source finding with OptimusKG ToolUniverse Medea support",
                limitations="Requires human validation.",
                required_validation="Confirm MTAP locus or protein status.",
                not_a_recommendation=True,
            )
        ],
    )


def _sankey() -> MechanismSankeyOutput:
    return MechanismSankeyOutput(
        artifact_id="artifact_sankey",
        nodes=[
            SankeyNode(node_id="finding", label="MTAP loss", kind="finding", evidence_class="patient_specific_finding"),
            SankeyNode(node_id="mechanism", label="PRMT5 context", kind="mechanism", evidence_class="graph_supported_context"),
        ],
        links=[
            SankeyLink(
                source_node_id="finding",
                target_node_id="mechanism",
                value=1.0,
                claim_class="model_derived_hypothesis",
                validation_required=True,
                source_artifact_ids=["finding_mtap", "edge_mtap_prmt5"],
            )
        ],
    )


def _confirmatory() -> ConfirmatoryTestingOutput:
    return ConfirmatoryTestingOutput(
        artifact_id="artifact_confirmatory",
        tests=[
            ConfirmatoryTest(
                test_id="test_mtap",
                question="Confirm MTAP status for review.",
                why_it_matters="MTAP status is needed before interpreting PRMT5 context.",
                positive_interpretation="Supports continued review of the MTAP axis.",
                negative_interpretation="Weakens the MTAP axis.",
                priority="high",
                evidence_gap="MTAP confirmation is missing.",
                source_claim_ids=["finding_mtap"],
            )
        ],
    )


def _valid_output() -> dict[str, object]:
    return {
        "state_evidence": [
            {
                "state_label": "stress_adapted_survival",
                "supporting_findings": ["finding_mtap"],
                "graph_support": ["edge_mtap_prmt5"],
                "tool_support": ["artifact_tool_literature_validation"],
                "medea_support": ["artifact_medea"],
                "evidence_class": "model_derived_hypothesis",
                "uncertainty": "MTAP and PRMT5 context requires human validation.",
                "validation_needed": True,
            }
        ],
        "transition_hypotheses": [
            {
                "from_state": "proliferative",
                "to_state": "stress_adapted_survival",
                "rationale": "MTAP loss and PRMT5 graph context support only a hypothesis-generating stress survival transition for review.",
                "supporting_artifacts": ["artifact_graph", "artifact_tool_literature_validation", "artifact_medea"],
                "confidence_label": "needs_review",
                "validation_status": "needs_review",
                "hypothesis_generating": True,
            }
        ],
        "limitations": ["No transition probability, treatment recommendation, or outcome prediction is generated."],
    }


@pytest.mark.asyncio
async def test_tumor_behavior_accepts_case_derived_model(tmp_path: Path) -> None:
    provider = TumorBehaviorModelProvider(_valid_output())
    result = await generate_tumor_behavior_model_with_model(
        context=_context(),
        phenotype=_phenotype(),
        matrix=_matrix(),
        sankey=_sankey(),
        confirmatory=_confirmatory(),
        model_provider=provider,
        model_name="local-test-model",
        prompts_root=Path("configs/prompts"),
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    assert result.artifact.state_evidence[0].graph_support == ["edge_mtap_prmt5"]
    assert provider.schema_names == ["TumorBehaviorModelOutput"]


@pytest.mark.asyncio
async def test_tumor_behavior_rejects_unsupported_support_artifact() -> None:
    output = _valid_output()
    output["transition_hypotheses"][0]["supporting_artifacts"] = ["artifact_fake"]
    with pytest.raises(StructuredArtifactGenerationError, match="unsupported IDs"):
        await generate_tumor_behavior_model_with_model(
            context=_context(),
            phenotype=_phenotype(),
            matrix=_matrix(),
            sankey=_sankey(),
            confirmatory=_confirmatory(),
            model_provider=TumorBehaviorModelProvider(output),
            model_name="local-test-model",
            prompts_root=Path("configs/prompts"),
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )


@pytest.mark.asyncio
async def test_tumor_behavior_rejects_generic_template_rationale() -> None:
    output = _valid_output()
    output["transition_hypotheses"][0]["rationale"] = "Structured findings and enrichment context suggest a reviewable adaptive hypothesis."
    with pytest.raises(StructuredArtifactGenerationError, match="case-derived evidence terms"):
        await generate_tumor_behavior_model_with_model(
            context=_context(),
            phenotype=_phenotype(),
            matrix=_matrix(),
            sankey=_sankey(),
            confirmatory=_confirmatory(),
            model_provider=TumorBehaviorModelProvider(output),
            model_name="local-test-model",
            prompts_root=Path("configs/prompts"),
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )


@pytest.mark.asyncio
async def test_tumor_behavior_rejects_probability_language() -> None:
    output = _valid_output()
    output["transition_hypotheses"][0]["rationale"] = "MTAP predicts a 70% relapse probability."
    with pytest.raises(StructuredArtifactGenerationError, match="probability"):
        await generate_tumor_behavior_model_with_model(
            context=_context(),
            phenotype=_phenotype(),
            matrix=_matrix(),
            sankey=_sankey(),
            confirmatory=_confirmatory(),
            model_provider=TumorBehaviorModelProvider(output),
            model_name="local-test-model",
            prompts_root=Path("configs/prompts"),
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )


def _planned_artifact_id(user_prompt: str) -> str:
    lines = user_prompt.splitlines()
    for index, line in enumerate(lines):
        if line.strip() == "The artifact_id must be exactly:" and index + 1 < len(lines):
            return lines[index + 1].strip()
    raise AssertionError("planned artifact id missing from prompt")
