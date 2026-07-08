from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

import pytest

from translume_core.compiler.structured_model_artifacts import (
    StructuredArtifactGenerationError,
    generate_claim_evidence_with_model,
    generate_mechanism_sankey_with_model,
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
from translume_schemas.tumor_behavior import STATE_LABELS


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


class SequencedTumorBehaviorModelProvider:
    """Test provider that returns a configured output per model call."""

    def __init__(self, outputs: list[dict[str, object]]) -> None:
        self.outputs = outputs
        self.schema_names: list[str] = []
        self.user_prompts: list[str] = []

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
        self.user_prompts.append(user_prompt)
        output_index = min(len(self.schema_names), len(self.outputs)) - 1
        payload = deepcopy(self.outputs[output_index])
        payload["artifact_id"] = _planned_artifact_id(user_prompt)
        return payload


class RaisingModelProvider:
    """Test-only provider that raises a configured runtime failure."""

    def __init__(self, message: str) -> None:
        self.message = message
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
        raise RuntimeError(self.message)


class SankeyModelProvider:
    """Test-only provider that returns a configured Sankey artifact."""

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
        payload = deepcopy(self.output)
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
                clinical_use="insufficient_evidence",
                therapy_class="PRMT5 pathway context",
                matched_biomarkers=["MTAP"],
                resistance_risks=["Bypass methylation context requires review."],
                required_before_use_tests=["Confirm MTAP locus or protein status."],
                confidence="needs_review",
                evidence_level="source-backed hypothesis requiring review",
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
        "limitations": ["No transition probability or deterministic outcome prediction is generated."],
    }


def _valid_sankey_output() -> dict[str, object]:
    return {
        "nodes": [
            {
                "node_id": "node_finding",
                "label": "MTAP loss",
                "kind": "finding",
                "evidence_class": "patient_specific_finding",
            },
            {
                "node_id": "node_mechanism",
                "label": "PRMT5 context",
                "kind": "mechanism",
                "evidence_class": "model_derived_hypothesis",
            },
        ],
        "links": [
            {
                "source_node_id": "node_finding",
                "target_node_id": "node_mechanism",
                "value": 1.0,
                "claim_class": "evidence_path_requires_review",
                "validation_required": True,
                "source_artifact_ids": ["artifact_extraction"],
            }
        ],
    }


@pytest.mark.asyncio
async def test_mechanism_sankey_timeout_uses_deterministic_fallback() -> None:
    provider = RaisingModelProvider(
        "Local vLLM request timed out: "
        "http://vllm-clinical:8000/v1/chat/completions: "
        "ReadTimeout after 240 seconds"
    )
    context = _context()
    phenotype = _phenotype()
    matrix = _matrix()
    result = await generate_mechanism_sankey_with_model(
        context=context,
        phenotype=phenotype,
        matrix=matrix,
        model_provider=provider,
        model_name="local-test-model",
        prompts_root=Path("configs/prompts"),
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    assert provider.schema_names == ["MechanismSankeyOutput"]
    assert result.artifact.artifact_id == result.provenance.artifact_id
    assert result.provenance.generation_status == "deterministic_fallback"
    assert result.provenance.model_name == "mechanism_sankey_deterministic_fallback"
    assert result.artifact.nodes
    assert result.artifact.links
    node_ids = {node.node_id for node in result.artifact.nodes}
    assert all(
        link.source_node_id in node_ids and link.target_node_id in node_ids
        for link in result.artifact.links
    )


@pytest.mark.asyncio
async def test_mechanism_sankey_non_timeout_error_still_raises() -> None:
    provider = RaisingModelProvider("vLLM error 500: overloaded")

    with pytest.raises(
        StructuredArtifactGenerationError,
        match="MechanismSankeyOutput structured output failed",
    ):
        await generate_mechanism_sankey_with_model(
            context=_context(),
            phenotype=_phenotype(),
            matrix=_matrix(),
            model_provider=provider,
            model_name="local-test-model",
            prompts_root=Path("configs/prompts"),
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )


@pytest.mark.asyncio
async def test_mechanism_sankey_deduplicates_identical_nodes() -> None:
    output = _valid_sankey_output()
    output["nodes"].append(dict(output["nodes"][0]))
    original = deepcopy(output)
    result = await generate_mechanism_sankey_with_model(
        context=_context(),
        phenotype=_phenotype(),
        matrix=_matrix(),
        model_provider=SankeyModelProvider(output),
        model_name="local-test-model",
        prompts_root=Path("configs/prompts"),
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    assert output == original
    assert [node.node_id for node in result.artifact.nodes] == [
        "node_finding",
        "node_mechanism",
    ]
    assert result.artifact.links[0].source_node_id == "node_finding"


@pytest.mark.asyncio
async def test_mechanism_sankey_rejects_conflicting_duplicate_node_id() -> None:
    output = _valid_sankey_output()
    output["nodes"].append(
        {
            "node_id": "node_finding",
            "label": "Conflicting label",
            "kind": "finding",
            "evidence_class": "patient_specific_finding",
        }
    )

    with pytest.raises(
        StructuredArtifactGenerationError,
        match="duplicate node_id has conflicting content",
    ):
        await generate_mechanism_sankey_with_model(
            context=_context(),
            phenotype=_phenotype(),
            matrix=_matrix(),
            model_provider=SankeyModelProvider(output),
            model_name="local-test-model",
            prompts_root=Path("configs/prompts"),
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )


@pytest.mark.asyncio
async def test_mechanism_sankey_still_rejects_missing_link_node() -> None:
    output = _valid_sankey_output()
    output["links"][0]["target_node_id"] = "node_missing"

    with pytest.raises(
        StructuredArtifactGenerationError,
        match="link references a missing node",
    ):
        await generate_mechanism_sankey_with_model(
            context=_context(),
            phenotype=_phenotype(),
            matrix=_matrix(),
            model_provider=SankeyModelProvider(output),
            model_name="local-test-model",
            prompts_root=Path("configs/prompts"),
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )


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
    assert result.artifact.state_evidence[0].evidence_class == (
        "model_derived_hypothesis"
    )
    assert provider.schema_names == ["TumorBehaviorModelOutput"]


@pytest.mark.asyncio
async def test_tumor_behavior_normalizes_generated_validation_status() -> None:
    output = _valid_output()
    output["transition_hypotheses"][0]["validation_status"] = "validated"
    output["transition_hypotheses"][0]["hypothesis_generating"] = False
    result = await generate_tumor_behavior_model_with_model(
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
    transition = result.artifact.transition_hypotheses[0]
    assert transition.validation_status == "needs_review"
    assert transition.hypothesis_generating is True


@pytest.mark.asyncio
async def test_tumor_behavior_marks_all_states_validation_needed() -> None:
    output = _valid_output()
    output["state_evidence"] = [
        {
            "state_label": state_label,
            "supporting_findings": ["finding_mtap"],
            "graph_support": ["edge_mtap_prmt5"],
            "tool_support": ["artifact_tool_literature_validation"],
            "medea_support": ["artifact_medea"],
            "evidence_class": "model_derived_hypothesis",
            "uncertainty": "State evidence requires human review.",
            "validation_needed": False,
        }
        for state_label in STATE_LABELS
    ]
    original = deepcopy(output)
    result = await generate_tumor_behavior_model_with_model(
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

    assert [state.state_label for state in result.artifact.state_evidence] == (
        STATE_LABELS
    )
    assert all(
        state.validation_needed is True
        for state in result.artifact.state_evidence
    )
    assert all(
        state.evidence_class == "model_derived_hypothesis"
        for state in result.artifact.state_evidence
    )
    assert output == original


@pytest.mark.asyncio
async def test_tumor_behavior_still_rejects_unsupported_ids_after_review_normalization() -> None:
    output = _valid_output()
    output["state_evidence"][0]["validation_needed"] = False
    output["state_evidence"][0]["graph_support"] = ["edge_not_from_case"]

    with pytest.raises(
        StructuredArtifactGenerationError,
        match="state_evidence\\[stress_adapted_survival\\].graph_support",
    ):
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
async def test_tumor_behavior_marks_empty_support_state_as_missing() -> None:
    output = _valid_output()
    output["state_evidence"][0]["supporting_findings"] = []
    output["state_evidence"][0]["graph_support"] = []
    output["state_evidence"][0]["tool_support"] = []
    output["state_evidence"][0]["medea_support"] = []
    output["state_evidence"][0]["validation_needed"] = False
    original = deepcopy(output)
    result = await generate_tumor_behavior_model_with_model(
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
    state = result.artifact.state_evidence[0]
    assert state.supporting_findings == []
    assert state.graph_support == []
    assert state.tool_support == []
    assert state.medea_support == []
    assert state.evidence_class == "missing_speculative_evidence"
    assert state.validation_needed is True
    assert output == original


@pytest.mark.asyncio
async def test_tumor_behavior_accepts_confirmatory_test_support() -> None:
    output = _valid_output()
    output["transition_hypotheses"][0]["supporting_artifacts"] = [
        "artifact_graph",
        "artifact_tool_literature_validation",
        "artifact_medea",
        "test_mtap",
    ]
    result = await generate_tumor_behavior_model_with_model(
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
    assert "test_mtap" in result.artifact.transition_hypotheses[0].supporting_artifacts


@pytest.mark.asyncio
async def test_tumor_behavior_counts_generated_ids_as_mims_support() -> None:
    output = _valid_output()
    output["state_evidence"][0]["graph_support"] = []
    output["state_evidence"][0]["tool_support"] = []
    output["state_evidence"][0]["medea_support"] = []
    output["transition_hypotheses"][0]["supporting_artifacts"] = ["test_mtap"]
    result = await generate_tumor_behavior_model_with_model(
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
    assert result.artifact.transition_hypotheses[0].supporting_artifacts == [
        "test_mtap"
    ]


@pytest.mark.asyncio
async def test_tumor_behavior_removes_self_support_when_valid_support_remains() -> None:
    output = _valid_output()
    output["transition_hypotheses"][0]["supporting_artifacts"] = [
        "artifact_graph",
        "artifact_tool_literature_validation",
        "artifact_self_placeholder",
        "artifact_medea",
    ]

    class SelfReferencingProvider(TumorBehaviorModelProvider):
        async def structured_completion(
            self,
            *,
            model_name: str,
            system_prompt: str,
            user_prompt: str,
            schema_name: str,
            json_schema: dict[str, object],
        ) -> dict[str, object]:
            payload = await super().structured_completion(
                model_name=model_name,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                schema_name=schema_name,
                json_schema=json_schema,
            )
            self_id = str(payload["artifact_id"])
            payload["transition_hypotheses"][0]["supporting_artifacts"] = [
                "artifact_graph",
                self_id,
                "artifact_tool_literature_validation",
                "artifact_medea",
            ]
            return payload

    result = await generate_tumor_behavior_model_with_model(
        context=_context(),
        phenotype=_phenotype(),
        matrix=_matrix(),
        sankey=_sankey(),
        confirmatory=_confirmatory(),
        model_provider=SelfReferencingProvider(output),
        model_name="local-test-model",
        prompts_root=Path("configs/prompts"),
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    support = result.artifact.transition_hypotheses[0].supporting_artifacts
    assert result.artifact.artifact_id not in support
    assert support == [
        "artifact_graph",
        "artifact_tool_literature_validation",
        "artifact_medea",
    ]


@pytest.mark.asyncio
async def test_tumor_behavior_rejects_self_support_without_real_support() -> None:
    output = _valid_output()

    class SelfOnlyProvider(TumorBehaviorModelProvider):
        async def structured_completion(
            self,
            *,
            model_name: str,
            system_prompt: str,
            user_prompt: str,
            schema_name: str,
            json_schema: dict[str, object],
        ) -> dict[str, object]:
            payload = await super().structured_completion(
                model_name=model_name,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                schema_name=schema_name,
                json_schema=json_schema,
            )
            payload["transition_hypotheses"][0]["supporting_artifacts"] = [
                str(payload["artifact_id"])
            ]
            return payload

    with pytest.raises(StructuredArtifactGenerationError, match="missing supporting_artifacts"):
        await generate_tumor_behavior_model_with_model(
            context=_context(),
            phenotype=_phenotype(),
            matrix=_matrix(),
            sankey=_sankey(),
            confirmatory=_confirmatory(),
            model_provider=SelfOnlyProvider(output),
            model_name="local-test-model",
            prompts_root=Path("configs/prompts"),
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )


@pytest.mark.asyncio
async def test_claim_evidence_normalizes_generated_validation_status() -> None:
    provider = TumorBehaviorModelProvider(
        {
            "claims": [
                {
                    "claim_id": "claim_mtap_review",
                    "claim": "MTAP loss supports only a reviewable hypothesis.",
                    "claim_class": "model_derived_hypothesis",
                    "source_artifact_ids": ["artifact_context"],
                    "evidence_source": "report_graph_tool_medea_context",
                    "relevance": "Connects MTAP loss to review workflow.",
                    "limitations": "Requires human validation.",
                    "validation_status": "approved",
                }
            ]
        }
    )
    tumor_provider = TumorBehaviorModelProvider(_valid_output())
    tumor_behavior = await generate_tumor_behavior_model_with_model(
        context=_context(),
        phenotype=_phenotype(),
        matrix=_matrix(),
        sankey=_sankey(),
        confirmatory=_confirmatory(),
        model_provider=tumor_provider,
        model_name="local-test-model",
        prompts_root=Path("configs/prompts"),
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    result = await generate_claim_evidence_with_model(
        context=_context(),
        phenotype=_phenotype(),
        matrix=_matrix(),
        sankey=_sankey(),
        confirmatory=_confirmatory(),
        tumor_behavior=tumor_behavior.artifact,
        model_provider=provider,
        model_name="local-test-model",
        prompts_root=Path("configs/prompts"),
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    assert result.artifact.claims[0].validation_status == "needs_review"


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
async def test_tumor_behavior_repairs_unsupported_support_artifacts() -> None:
    first_output = _valid_output()
    first_output["transition_hypotheses"][0]["supporting_artifacts"] = [
        "artifact_fake_a",
        "artifact_fake_b",
    ]
    repaired_output = _valid_output()
    repaired_output["transition_hypotheses"][0]["supporting_artifacts"] = [
        "artifact_graph",
        "artifact_tool_literature_validation",
        "artifact_medea",
    ]
    provider = SequencedTumorBehaviorModelProvider(
        [first_output, repaired_output]
    )

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

    assert result.artifact.transition_hypotheses[0].supporting_artifacts == [
        "artifact_graph",
        "artifact_tool_literature_validation",
        "artifact_medea",
    ]
    assert provider.schema_names == [
        "TumorBehaviorModelOutput",
        "TumorBehaviorModelOutput",
    ]
    assert "allowed_supporting_artifact_ids" in provider.user_prompts[1]
    assert "artifact_graph" in provider.user_prompts[1]


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
async def test_tumor_behavior_repairs_generic_transition_rationale() -> None:
    first_output = _valid_output()
    first_output["transition_hypotheses"][0]["rationale"] = (
        "Structured findings and enrichment context suggest a reviewable "
        "adaptive hypothesis."
    )
    repaired_output = _valid_output()
    repaired_output["transition_hypotheses"][0]["rationale"] = (
        "MTAP loss and PRMT5 graph context support only a hypothesis-generating "
        "transition for human review."
    )
    provider = SequencedTumorBehaviorModelProvider(
        [first_output, repaired_output]
    )

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

    transition = result.artifact.transition_hypotheses[0]
    assert transition.rationale == repaired_output["transition_hypotheses"][0][
        "rationale"
    ]
    assert provider.schema_names == [
        "TumorBehaviorModelOutput",
        "TumorBehaviorModelOutput",
    ]
    assert "repair_instruction" in provider.user_prompts[1]
    assert "allowed_case_terms" in provider.user_prompts[1]


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
