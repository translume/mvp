from __future__ import annotations

import json
from copy import deepcopy

from translume_core.compiler.structured_model_artifacts import (
    _MAX_PROMPT_AXES,
    _MAX_PROMPT_CLAIMS,
    _MAX_PROMPT_CLAIM_INPUT_CONFIRMATORY_TESTS,
    _MAX_PROMPT_CLAIM_INPUT_GRAPH_EDGES,
    _MAX_PROMPT_CLAIM_INPUT_GRAPH_NODES,
    _MAX_PROMPT_CLAIM_INPUT_MATRIX_ROWS,
    _MAX_PROMPT_CLAIM_INPUT_SANKEY_LINKS,
    _MAX_PROMPT_CLAIM_INPUT_SANKEY_NODES,
    _MAX_PROMPT_CLAIM_INPUT_TEXT_CHARS,
    _MAX_PROMPT_CLAIM_INPUT_TOOL_EVIDENCE_ITEMS,
    _MAX_PROMPT_CLAIM_INPUT_TOOL_OUTPUTS,
    _MAX_PROMPT_CLAIM_INPUT_TRANSITIONS,
    _MAX_PROMPT_CLAIM_INPUT_TUMOR_STATES,
    _MAX_PROMPT_CONFIRMATORY_TESTS,
    _MAX_PROMPT_GENERATED_TEXT_CHARS,
    _MAX_PROMPT_GRAPH_EDGES,
    _MAX_PROMPT_GRAPH_NODES,
    _MAX_PROMPT_HYPOTHESES,
    _MAX_PROMPT_MATRIX_ROWS,
    _MAX_PROMPT_MISC_TEXT_CHARS,
    _MAX_PROMPT_NARRATIVE_CLAIMS,
    _MAX_PROMPT_NARRATIVE_CONFIRMATORY_TESTS,
    _MAX_PROMPT_NARRATIVE_DECISION_ROWS,
    _MAX_PROMPT_NARRATIVE_MATRIX_ROWS,
    _MAX_PROMPT_NARRATIVE_SANKEY_LINKS,
    _MAX_PROMPT_NARRATIVE_SANKEY_NODES,
    _MAX_PROMPT_NARRATIVE_TEXT_CHARS,
    _MAX_PROMPT_NARRATIVE_TUMOR_STATES,
    _MAX_PROMPT_PHENOTYPE_FINDINGS,
    _MAX_PROMPT_PHENOTYPE_GRAPH_EDGES,
    _MAX_PROMPT_PHENOTYPE_GRAPH_NODES,
    _MAX_PROMPT_PHENOTYPE_HYPOTHESES,
    _MAX_PROMPT_PHENOTYPE_SUMMARY_CHARS,
    _MAX_PROMPT_PHENOTYPE_TEXT_CHARS,
    _MAX_PROMPT_PHENOTYPE_TOOL_EVIDENCE_ITEMS,
    _MAX_PROMPT_PHENOTYPE_TOOL_OUTPUTS,
    _MAX_PROMPT_SANKEY_LINKS,
    _MAX_PROMPT_SANKEY_INPUT_AXES,
    _MAX_PROMPT_SANKEY_INPUT_GRAPH_EDGES,
    _MAX_PROMPT_SANKEY_INPUT_GRAPH_NODES,
    _MAX_PROMPT_SANKEY_INPUT_MATRIX_ROWS,
    _MAX_PROMPT_SANKEY_NODES,
    _MAX_PROMPT_SOURCE_TEXT_CHARS,
    _MAX_PROMPT_TUMOR_STATES,
    _MAX_PROMPT_TUMOR_INPUT_CONFIRMATORY_TESTS,
    _MAX_PROMPT_TUMOR_INPUT_GRAPH_EDGES,
    _MAX_PROMPT_TUMOR_INPUT_GRAPH_NODES,
    _MAX_PROMPT_TUMOR_INPUT_MATRIX_ROWS,
    _MAX_PROMPT_TUMOR_INPUT_SANKEY_LINKS,
    _MAX_PROMPT_TUMOR_INPUT_SANKEY_NODES,
    _MAX_PROMPT_TUMOR_INPUT_TEXT_CHARS,
    _MAX_PROMPT_TUMOR_INPUT_TOOL_EVIDENCE_ITEMS,
    _MAX_PROMPT_TUMOR_INPUT_TOOL_OUTPUTS,
    _MAX_PROMPT_TRANSITIONS,
    compact_claims_for_prompt,
    compact_claim_evidence_inputs_for_prompt,
    compact_clinical_artifact_bundle_for_prompt,
    compact_clinical_narrative_bundle_for_prompt,
    compact_evidence_context_for_molecular_phenotype_prompt,
    compact_evidence_context_for_prompt,
    compact_evidence_context_for_mechanism_sankey_prompt,
    compact_confirmatory_for_prompt,
    compact_graph_for_prompt,
    compact_matrix_for_prompt,
    compact_matrix_for_sankey_prompt,
    compact_phenotype_for_prompt,
    compact_phenotype_for_sankey_prompt,
    compact_sankey_for_prompt,
    compact_tumor_behavior_inputs_for_prompt,
    compact_tumor_behavior_for_prompt,
    truncate_text,
)
from translume_schemas.claims import ClaimEvidenceOutput
from translume_schemas.confirmatory import ConfirmatoryTest, ConfirmatoryTestingOutput
from translume_schemas.decision_brief import (
    ActionableBiologyItem,
    BiomarkerWatchItem,
    CurrentTumorState,
    EvidenceLimitation,
    EvidenceSentence,
    NextTestRecommendation,
    OncologistDecisionBrief,
    RankedTreatmentOption,
    ResistanceForecastItem,
    RetestingTrigger,
    TherapyEscapeSankeyPath,
    TranslationalAssessmentOutput,
    TranslationalQuestionAssessment,
    TreatmentPressureMapRow,
)
from translume_schemas.evidence import EvidenceContextBundle
from translume_schemas.export import ClinicalArtifactBundle
from translume_schemas.extraction import MolecularFinding, ReportExtractionOutput
from translume_schemas.graph import GraphEdge, GraphEvidenceArtifact, GraphNode, GraphSubgraphEvidence
from translume_schemas.matrix import MolecularFitRow, TherapyEvidenceMatrixOutput
from translume_schemas.medea import MedeaReasoningArtifact
from translume_schemas.phenotype import BiologicalAxis, MolecularPhenotypeOutput
from translume_schemas.sankey import (
    MechanismSankeyOutput,
    SankeyLink,
    SankeyNode,
)
from translume_schemas.tools import ToolRunArtifact
from translume_schemas.tumor_behavior import (
    TransitionHypothesis,
    TumorBehaviorModelOutput,
    TumorStateEvidence,
)


def test_compact_evidence_context_preserves_grounding_and_caps_payload() -> None:
    context = _large_context()

    compact = compact_evidence_context_for_prompt(context)

    finding = compact["extraction"]["molecular_findings"][0]
    graph = compact["graph_evidence"]
    medea = compact["medea_reasoning"]
    tool = compact["tool_outputs"][0]

    assert finding["finding_id"] == "finding_flt3"
    assert finding["source_chunk_id"] == "chunk_1"
    assert "[truncated" in finding["source_text"]
    assert len(finding["source_text"]) > _MAX_PROMPT_SOURCE_TEXT_CHARS
    assert len(graph["nodes"]) <= _MAX_PROMPT_GRAPH_NODES
    assert len(graph["edges"]) <= _MAX_PROMPT_GRAPH_EDGES
    assert graph["nodes"][0]["node_id"] == "node_flt3"
    assert graph["retrieval_modes"] == ["general_context", "resistance_path"]
    assert graph["subgraphs"][0]["retrieval_mode"] == "general_context"
    assert graph["subgraphs"][1]["retrieval_mode"] == "resistance_path"
    assert graph["truncation"]["original_nodes"] > graph["truncation"]["kept_nodes"]
    assert "not be interpreted as absent" in graph["truncation"]["notice"]
    assert "provenance" not in graph["nodes"][0]
    assert len(tool["evidence_items"][0]["context"]) > _MAX_PROMPT_MISC_TEXT_CHARS
    assert "[truncated" in tool["evidence_items"][0]["context"]
    assert medea["artifact_id"] == "artifact_medea"
    assert len(medea["supported_hypotheses"]) == _MAX_PROMPT_HYPOTHESES
    assert len(json.dumps(compact)) < 30000


def test_compact_graph_is_deterministic_and_does_not_mutate_inputs() -> None:
    context = _large_context()
    graph = context.graph_evidence.model_dump(mode="json")
    original = deepcopy(graph)

    first = compact_graph_for_prompt(graph, ["FLT3"])
    second = compact_graph_for_prompt(graph, ["FLT3"])

    assert first == second
    assert graph == original
    kept_node_ids = {node["node_id"] for node in first["nodes"]}
    for edge in first["edges"]:
        assert (
            edge["source_node_id"] in kept_node_ids
            or edge["target_node_id"] in kept_node_ids
        )


def test_truncate_text_rejects_invalid_limits() -> None:
    try:
        truncate_text("abc", 0)
    except ValueError as error:
        assert "max_chars" in str(error)
    else:
        raise AssertionError("truncate_text should reject non-positive limits")


def test_generated_artifact_compactors_cap_payloads_and_keep_ids() -> None:
    matrix = _large_matrix()
    sankey = _large_sankey()
    tumor_behavior = _large_tumor_behavior()
    matrix_original = matrix.model_dump(mode="json")
    sankey_original = sankey.model_dump(mode="json")
    tumor_original = tumor_behavior.model_dump(mode="json")

    compact_matrix = compact_matrix_for_prompt(matrix)
    compact_sankey = compact_sankey_for_prompt(sankey)
    compact_tumor = compact_tumor_behavior_for_prompt(tumor_behavior)

    assert len(compact_matrix["rows"]) == _MAX_PROMPT_MATRIX_ROWS
    assert compact_matrix["rows"][0]["clinical_use"] == "insufficient_evidence"
    assert "[truncated" in compact_matrix["rows"][0]["why_from_omics"]
    assert len(compact_sankey["nodes"]) == _MAX_PROMPT_SANKEY_NODES
    assert len(compact_sankey["links"]) == _MAX_PROMPT_SANKEY_LINKS
    assert compact_sankey["links"][0]["source_artifact_ids"] == ["artifact_context"]
    assert len(compact_tumor["state_evidence"]) == _MAX_PROMPT_TUMOR_STATES
    assert (
        len(compact_tumor["transition_hypotheses"])
        == _MAX_PROMPT_TRANSITIONS
    )
    assert compact_tumor["state_evidence"][0]["supporting_findings"] == [
        "finding_flt3"
    ]
    assert "[truncated" in compact_tumor["transition_hypotheses"][0]["rationale"]
    assert matrix.model_dump(mode="json") == matrix_original
    assert sankey.model_dump(mode="json") == sankey_original
    assert tumor_behavior.model_dump(mode="json") == tumor_original


def test_mechanism_sankey_prompt_payload_uses_tighter_caps() -> None:
    context = _large_context()
    phenotype = _large_phenotype()
    matrix = _large_matrix()
    payload = {
        "evidence_context": compact_evidence_context_for_mechanism_sankey_prompt(
            context
        ),
        "molecular_phenotype": compact_phenotype_for_sankey_prompt(phenotype),
        "molecular_fit_matrix": compact_matrix_for_sankey_prompt(matrix),
    }

    evidence_context = payload["evidence_context"]
    phenotype_payload = payload["molecular_phenotype"]
    matrix_payload = payload["molecular_fit_matrix"]

    assert evidence_context["artifact_id"] == "artifact_context"
    assert evidence_context["extraction"]["molecular_findings"][0]["finding_id"] == (
        "finding_flt3"
    )
    assert evidence_context["graph_evidence"]["nodes"][0]["node_id"] == "node_flt3"
    assert len(evidence_context["graph_evidence"]["nodes"]) == (
        _MAX_PROMPT_SANKEY_INPUT_GRAPH_NODES
    )
    assert len(evidence_context["graph_evidence"]["edges"]) == (
        _MAX_PROMPT_SANKEY_INPUT_GRAPH_EDGES
    )
    assert len(phenotype_payload["axes"]) == _MAX_PROMPT_SANKEY_INPUT_AXES
    assert len(matrix_payload["rows"]) == _MAX_PROMPT_SANKEY_INPUT_MATRIX_ROWS
    assert len(json.dumps(payload)) < 12000


def test_molecular_phenotype_prompt_payload_uses_tighter_caps() -> None:
    context = _large_context()
    original = context.model_dump(mode="json")

    general = compact_evidence_context_for_prompt(context)
    compact = compact_evidence_context_for_molecular_phenotype_prompt(context)

    finding = compact["extraction"]["molecular_findings"][0]
    graph = compact["graph_evidence"]
    tool = compact["tool_outputs"][0]
    medea = compact["medea_reasoning"]

    assert compact["artifact_id"] == "artifact_context"
    assert finding["finding_id"] == "finding_flt3"
    assert finding["source_chunk_id"] == "chunk_1"
    assert "[truncated" in finding["source_text"]
    assert len(finding["source_text"]) > _MAX_PROMPT_PHENOTYPE_TEXT_CHARS
    assert len(compact["extraction"]["molecular_findings"]) <= (
        _MAX_PROMPT_PHENOTYPE_FINDINGS
    )
    assert graph["artifact_id"] == "artifact_graph"
    assert graph["nodes"][0]["node_id"] == "node_flt3"
    assert len(graph["nodes"]) <= _MAX_PROMPT_PHENOTYPE_GRAPH_NODES
    assert len(graph["edges"]) <= _MAX_PROMPT_PHENOTYPE_GRAPH_EDGES
    assert graph["retrieval_modes"] == ["general_context", "resistance_path"]
    assert graph["subgraphs"][0]["retrieval_mode"] == "general_context"
    assert "not be interpreted as absent" in graph["truncation"]["notice"]
    assert len(compact["tool_outputs"]) <= _MAX_PROMPT_PHENOTYPE_TOOL_OUTPUTS
    assert tool["artifact_id"] == "artifact_tool"
    assert tool["workflow"] == "literature_validation"
    assert len(tool["summary"]) > _MAX_PROMPT_PHENOTYPE_SUMMARY_CHARS
    assert len(tool["evidence_items"]) == (
        _MAX_PROMPT_PHENOTYPE_TOOL_EVIDENCE_ITEMS
    )
    assert "[truncated" in tool["evidence_items"][0]["context"]
    assert medea["artifact_id"] == "artifact_medea"
    assert len(medea["supported_hypotheses"]) == (
        _MAX_PROMPT_PHENOTYPE_HYPOTHESES
    )
    assert "[truncated" in medea["summary"]
    assert len(json.dumps(compact)) < len(json.dumps(general))
    assert len(json.dumps(compact)) < 15000
    assert context.model_dump(mode="json") == original


def test_claim_evidence_prompt_payload_uses_tighter_caps() -> None:
    context = _large_context()
    phenotype = _large_phenotype()
    matrix = _large_matrix()
    sankey = _large_sankey()
    confirmatory = _large_confirmatory()
    tumor_behavior = _large_tumor_behavior()
    originals = {
        "context": context.model_dump(mode="json"),
        "phenotype": phenotype.model_dump(mode="json"),
        "matrix": matrix.model_dump(mode="json"),
        "sankey": sankey.model_dump(mode="json"),
        "confirmatory": confirmatory.model_dump(mode="json"),
        "tumor_behavior": tumor_behavior.model_dump(mode="json"),
    }

    general_payload = {
        "evidence_context": compact_evidence_context_for_prompt(context),
        "molecular_phenotype": compact_phenotype_for_prompt(phenotype),
        "molecular_fit_matrix": compact_matrix_for_prompt(matrix),
        "mechanism_sankey": compact_sankey_for_prompt(sankey),
        "confirmatory_testing": compact_confirmatory_for_prompt(confirmatory),
        "tumor_behavior_model": compact_tumor_behavior_for_prompt(
            tumor_behavior
        ),
    }
    compact = compact_claim_evidence_inputs_for_prompt(
        context=context,
        phenotype=phenotype,
        matrix=matrix,
        sankey=sankey,
        confirmatory=confirmatory,
        tumor_behavior=tumor_behavior,
    )

    evidence_context = compact["evidence_context"]
    graph = evidence_context["graph_evidence"]
    tool = evidence_context["tool_outputs"][0]
    medea = evidence_context["medea_reasoning"]
    finding = evidence_context["extraction"]["molecular_findings"][0]

    assert evidence_context["artifact_id"] == "artifact_context"
    assert finding["finding_id"] == "finding_flt3"
    assert finding["source_chunk_id"] == "chunk_1"
    assert "[truncated" in finding["source_text"]
    assert len(finding["source_text"]) > _MAX_PROMPT_CLAIM_INPUT_TEXT_CHARS
    assert graph["artifact_id"] == "artifact_graph"
    assert graph["nodes"][0]["node_id"] == "node_flt3"
    assert len(graph["nodes"]) <= _MAX_PROMPT_CLAIM_INPUT_GRAPH_NODES
    assert len(graph["edges"]) <= _MAX_PROMPT_CLAIM_INPUT_GRAPH_EDGES
    assert len(evidence_context["tool_outputs"]) <= (
        _MAX_PROMPT_CLAIM_INPUT_TOOL_OUTPUTS
    )
    assert tool["artifact_id"] == "artifact_tool"
    assert len(tool["evidence_items"]) == (
        _MAX_PROMPT_CLAIM_INPUT_TOOL_EVIDENCE_ITEMS
    )
    assert "[truncated" in tool["evidence_items"][0]["context"]
    assert medea["artifact_id"] == "artifact_medea"
    assert "[truncated" in medea["summary"]
    assert compact["molecular_phenotype"]["artifact_id"] == "artifact_phenotype"
    assert compact["molecular_fit_matrix"]["artifact_id"] == "artifact_matrix"
    assert len(compact["molecular_fit_matrix"]["rows"]) == (
        _MAX_PROMPT_CLAIM_INPUT_MATRIX_ROWS
    )
    assert compact["mechanism_sankey"]["artifact_id"] == "artifact_sankey"
    assert len(compact["mechanism_sankey"]["nodes"]) == (
        _MAX_PROMPT_CLAIM_INPUT_SANKEY_NODES
    )
    assert len(compact["mechanism_sankey"]["links"]) <= (
        _MAX_PROMPT_CLAIM_INPUT_SANKEY_LINKS
    )
    assert compact["confirmatory_testing"]["artifact_id"] == (
        "artifact_confirmatory"
    )
    assert len(compact["confirmatory_testing"]["tests"]) == (
        _MAX_PROMPT_CLAIM_INPUT_CONFIRMATORY_TESTS
    )
    assert compact["tumor_behavior_model"]["artifact_id"] == (
        "artifact_tumor_behavior"
    )
    assert len(compact["tumor_behavior_model"]["state_evidence"]) == (
        _MAX_PROMPT_CLAIM_INPUT_TUMOR_STATES
    )
    assert len(compact["tumor_behavior_model"]["transition_hypotheses"]) == (
        _MAX_PROMPT_CLAIM_INPUT_TRANSITIONS
    )
    assert len(json.dumps(compact)) < len(json.dumps(general_payload))
    assert len(json.dumps(compact)) < 25000
    assert context.model_dump(mode="json") == originals["context"]
    assert phenotype.model_dump(mode="json") == originals["phenotype"]
    assert matrix.model_dump(mode="json") == originals["matrix"]
    assert sankey.model_dump(mode="json") == originals["sankey"]
    assert confirmatory.model_dump(mode="json") == originals["confirmatory"]
    assert tumor_behavior.model_dump(mode="json") == originals["tumor_behavior"]


def test_tumor_behavior_prompt_payload_uses_tighter_caps() -> None:
    context = _large_context()
    phenotype = _large_phenotype()
    matrix = _large_matrix()
    sankey = _large_sankey()
    confirmatory = _large_confirmatory()
    originals = {
        "context": context.model_dump(mode="json"),
        "phenotype": phenotype.model_dump(mode="json"),
        "matrix": matrix.model_dump(mode="json"),
        "sankey": sankey.model_dump(mode="json"),
        "confirmatory": confirmatory.model_dump(mode="json"),
    }

    general_payload = {
        "evidence_context": compact_evidence_context_for_prompt(context),
        "molecular_phenotype": compact_phenotype_for_prompt(phenotype),
        "molecular_fit_matrix": compact_matrix_for_prompt(matrix),
        "mechanism_sankey": compact_sankey_for_prompt(sankey),
        "confirmatory_testing": compact_confirmatory_for_prompt(confirmatory),
    }
    compact = compact_tumor_behavior_inputs_for_prompt(
        context=context,
        phenotype=phenotype,
        matrix=matrix,
        sankey=sankey,
        confirmatory=confirmatory,
    )

    evidence_context = compact["evidence_context"]
    graph = evidence_context["graph_evidence"]
    tool = evidence_context["tool_outputs"][0]
    medea = evidence_context["medea_reasoning"]
    finding = evidence_context["extraction"]["molecular_findings"][0]

    assert evidence_context["artifact_id"] == "artifact_context"
    assert finding["finding_id"] == "finding_flt3"
    assert finding["source_chunk_id"] == "chunk_1"
    assert "[truncated" in finding["source_text"]
    assert len(finding["source_text"]) > _MAX_PROMPT_TUMOR_INPUT_TEXT_CHARS
    assert graph["artifact_id"] == "artifact_graph"
    assert graph["nodes"][0]["node_id"] == "node_flt3"
    assert len(graph["nodes"]) <= _MAX_PROMPT_TUMOR_INPUT_GRAPH_NODES
    assert len(graph["edges"]) <= _MAX_PROMPT_TUMOR_INPUT_GRAPH_EDGES
    assert len(evidence_context["tool_outputs"]) <= (
        _MAX_PROMPT_TUMOR_INPUT_TOOL_OUTPUTS
    )
    assert tool["artifact_id"] == "artifact_tool"
    assert len(tool["evidence_items"]) == (
        _MAX_PROMPT_TUMOR_INPUT_TOOL_EVIDENCE_ITEMS
    )
    assert "[truncated" in tool["evidence_items"][0]["context"]
    assert medea["artifact_id"] == "artifact_medea"
    assert "[truncated" in medea["summary"]
    assert compact["molecular_phenotype"]["artifact_id"] == "artifact_phenotype"
    assert compact["molecular_fit_matrix"]["artifact_id"] == "artifact_matrix"
    assert len(compact["molecular_fit_matrix"]["rows"]) == (
        _MAX_PROMPT_TUMOR_INPUT_MATRIX_ROWS
    )
    assert compact["mechanism_sankey"]["artifact_id"] == "artifact_sankey"
    assert len(compact["mechanism_sankey"]["nodes"]) == (
        _MAX_PROMPT_TUMOR_INPUT_SANKEY_NODES
    )
    assert len(compact["mechanism_sankey"]["links"]) <= (
        _MAX_PROMPT_TUMOR_INPUT_SANKEY_LINKS
    )
    assert compact["confirmatory_testing"]["artifact_id"] == (
        "artifact_confirmatory"
    )
    assert len(compact["confirmatory_testing"]["tests"]) == (
        _MAX_PROMPT_TUMOR_INPUT_CONFIRMATORY_TESTS
    )
    assert len(json.dumps(compact)) < len(json.dumps(general_payload))
    assert len(json.dumps(compact)) < 25000
    assert context.model_dump(mode="json") == originals["context"]
    assert phenotype.model_dump(mode="json") == originals["phenotype"]
    assert matrix.model_dump(mode="json") == originals["matrix"]
    assert sankey.model_dump(mode="json") == originals["sankey"]
    assert confirmatory.model_dump(mode="json") == originals["confirmatory"]


def test_clinical_bundle_compactor_caps_generated_artifacts_and_claims() -> None:
    bundle = _large_clinical_bundle()
    original = bundle.model_dump(mode="json")

    compact = compact_clinical_artifact_bundle_for_prompt(bundle)

    assert compact["source_artifact_ids"]
    assert compact["source_chunk_ids"] == ["chunk_1"]
    assert len(compact["phenotype"]["axes"]) == _MAX_PROMPT_AXES
    assert len(compact["matrix"]["rows"]) == _MAX_PROMPT_MATRIX_ROWS
    assert len(compact["sankey"]["nodes"]) == _MAX_PROMPT_SANKEY_NODES
    assert len(compact["confirmatory"]["tests"]) == _MAX_PROMPT_CONFIRMATORY_TESTS
    assert len(compact["tumor_behavior"]["state_evidence"]) == _MAX_PROMPT_TUMOR_STATES
    assert len(compact["claims"]) == _MAX_PROMPT_CLAIMS
    assert compact["claims"][0]["claim_id"] == "claim_0"
    assert compact["claims"][0]["source_artifact_ids"] == ["artifact_context"]
    assert "[truncated" in compact["claims"][0]["claim"]
    assert bundle.model_dump(mode="json") == original


def test_clinical_narrative_bundle_uses_tighter_caps() -> None:
    bundle = _large_clinical_bundle()
    original = bundle.model_dump(mode="json")

    general = compact_clinical_artifact_bundle_for_prompt(bundle)
    compact = compact_clinical_narrative_bundle_for_prompt(bundle)

    assert compact["source_artifact_ids"]
    assert compact["source_chunk_ids"] == ["chunk_1"]
    assert compact["extraction"]["molecular_findings"][0]["finding_id"] == (
        "finding_flt3"
    )
    assert "[truncated" in compact["extraction"]["molecular_findings"][0][
        "source_text"
    ]
    assert len(compact["matrix"]["rows"]) == _MAX_PROMPT_NARRATIVE_MATRIX_ROWS
    assert len(compact["sankey"]["nodes"]) == (
        _MAX_PROMPT_NARRATIVE_SANKEY_NODES
    )
    assert len(compact["sankey"]["links"]) <= (
        _MAX_PROMPT_NARRATIVE_SANKEY_LINKS
    )
    assert len(compact["confirmatory"]["tests"]) == (
        _MAX_PROMPT_NARRATIVE_CONFIRMATORY_TESTS
    )
    assert len(compact["tumor_behavior"]["state_evidence"]) == (
        _MAX_PROMPT_NARRATIVE_TUMOR_STATES
    )
    assert compact["decision_brief"]["artifact_id"] == "artifact_decision_brief"
    assert len(compact["decision_brief"]["ranked_treatment_options"]) == (
        _MAX_PROMPT_NARRATIVE_DECISION_ROWS
    )
    assert "[truncated" in compact["decision_brief"][
        "clinical_decision_summary"
    ]
    assert len(compact["claims"]) == _MAX_PROMPT_NARRATIVE_CLAIMS
    assert compact["claims"][0]["claim_id"] == "claim_0"
    assert len(compact["claims"][0]["claim"]) > (
        _MAX_PROMPT_NARRATIVE_TEXT_CHARS
    )
    assert len(json.dumps(compact)) < len(json.dumps(general))
    assert len(json.dumps(compact)) < 30000
    assert bundle.model_dump(mode="json") == original


def test_compact_claims_preserves_order_and_bounds_text() -> None:
    claims = _large_claims()

    compact = compact_claims_for_prompt(claims)

    assert [claim["claim_id"] for claim in compact[:3]] == [
        "claim_0",
        "claim_1",
        "claim_2",
    ]
    assert len(compact) == _MAX_PROMPT_CLAIMS
    assert len(compact[0]["claim"]) > _MAX_PROMPT_GENERATED_TEXT_CHARS
    assert "[truncated" in compact[0]["limitations"]


def _large_context() -> EvidenceContextBundle:
    extraction = ReportExtractionOutput(
        artifact_id="artifact_extraction",
        report_type="NGS",
        disease="acute myeloid leukemia",
        specimen="bone marrow",
        tumor_percentage="80%",
        source_file_id="source_file_1",
        molecular_findings=[
            MolecularFinding(
                finding_id="finding_flt3",
                gene="FLT3",
                alteration="internal tandem duplication",
                alteration_type="insertion",
                source_page=2,
                source_text="FLT3 internal tandem duplication. " * 120,
                source_chunk_id="chunk_1",
                confidence=0.91,
            )
        ],
    )
    graph = GraphEvidenceArtifact(
        artifact_id="artifact_graph",
        source_entity_ids=["entity_flt3"],
        nodes=[
            GraphNode(
                node_id="node_flt3",
                label="FLT3",
                kind="gene",
                source="optimuskg",
            ),
            *[
                GraphNode(
                    node_id=f"node_neighbor_{index}",
                    label=f"FLT3 pathway neighbor {index}",
                    kind="pathway",
                    source="optimuskg",
                )
                for index in range(30)
            ],
            *[
                GraphNode(
                    node_id=f"node_unrelated_{index}",
                    label=f"unrelated context {index}",
                    kind="concept",
                    source="optimuskg",
                )
                for index in range(30)
            ],
        ],
        edges=[
            *[
                GraphEdge(
                    edge_id=f"edge_flt3_neighbor_{index}",
                    source_node_id="node_flt3",
                    target_node_id=f"node_neighbor_{index}",
                    relation_type="related_to",
                    source="optimuskg",
                )
                for index in range(30)
            ],
            *[
                GraphEdge(
                    edge_id=f"edge_unrelated_{index}",
                    source_node_id=f"node_unrelated_{index}",
                    target_node_id=f"node_unrelated_{index + 1}",
                    relation_type="co_mentions",
                    source="optimuskg",
                )
                for index in range(29)
            ],
        ],
        retrieval_modes=["general_context", "resistance_path"],
        subgraphs=[
            GraphSubgraphEvidence(
                retrieval_mode="general_context",
                query_terms=["FLT3"],
                node_ids=["node_flt3", "node_neighbor_0"],
                edge_ids=["edge_flt3_neighbor_0"],
            ),
            GraphSubgraphEvidence(
                retrieval_mode="resistance_path",
                query_terms=["FLT3", "escape"],
                node_ids=["node_flt3", "node_neighbor_1"],
                edge_ids=["edge_flt3_neighbor_1"],
            ),
        ],
    )
    tool = ToolRunArtifact(
        artifact_id="artifact_tool",
        workflow="literature_validation",
        input_entity_ids=["entity_flt3"],
        summary="FLT3 review context. " * 200,
        evidence_items=[
            {"entity": "FLT3", "context": f"evidence item {index} " * 200}
            for index in range(20)
        ],
    )
    medea = MedeaReasoningArtifact(
        artifact_id="artifact_medea",
        reasoning_mode="bounded_review_support",
        summary="FLT3 bounded reasoning context. " * 200,
        supported_hypotheses=[f"supported {index}" for index in range(20)],
        weakened_hypotheses=[f"weakened {index}" for index in range(20)],
    )
    return EvidenceContextBundle(
        artifact_id="artifact_context",
        extraction=extraction,
        graph_evidence=graph,
        tool_outputs=[tool],
        medea_reasoning=medea,
    )


def _large_clinical_bundle() -> ClinicalArtifactBundle:
    context = _large_context()
    return ClinicalArtifactBundle(
        case_id="case_1",
        session_id="session_1",
        extraction=context.extraction,
        evidence_context=context,
        phenotype=_large_phenotype(),
        matrix=_large_matrix(),
        sankey=_large_sankey(),
        confirmatory=_large_confirmatory(),
        tumor_behavior=_large_tumor_behavior(),
        decision_brief=_large_decision_brief(),
        claims=_large_claims(),
    )


def _large_phenotype() -> MolecularPhenotypeOutput:
    return MolecularPhenotypeOutput(
        artifact_id="artifact_phenotype",
        axes=[
            BiologicalAxis(
                axis_id=f"axis_{index}",
                label=f"FLT3 axis {index}",
                supporting_finding_ids=["finding_flt3"],
                evidence_class="model_derived_hypothesis",
                uncertainty="Requires human review. " * 120,
                validation_needed=True,
            )
            for index in range(30)
        ],
        limitations=["Do not infer unsupported certainty. " * 80],
    )


def _large_matrix() -> TherapyEvidenceMatrixOutput:
    return TherapyEvidenceMatrixOutput(
        artifact_id="artifact_matrix",
        rows=[
            MolecularFitRow(
                rank=index + 1,
                molecular_fit=f"review fit {index}",
                fit_label="needs_review",
                why_from_omics="FLT3 context requires review. " * 120,
                evidence_basis="Source-backed report and MIMS evidence. " * 120,
                limitations="Evidence limitations require clinician review. " * 120,
                required_validation="Clinician validation required. " * 120,
                clinical_use="insufficient_evidence",
                therapy_class="review context",
                matched_biomarkers=["FLT3"],
                resistance_risks=["Pathway adaptation requires review."],
                required_before_use_tests=["Clinician validation required."],
                confidence="needs_review",
                evidence_level="source-backed hypothesis requiring review",
            )
            for index in range(40)
        ],
    )


def _large_sankey() -> MechanismSankeyOutput:
    return MechanismSankeyOutput(
        artifact_id="artifact_sankey",
        nodes=[
            SankeyNode(
                node_id=f"node_{index}",
                label=f"mechanism node {index}",
                kind="finding" if index == 0 else "mechanism",
                evidence_class="model_derived_hypothesis",
            )
            for index in range(80)
        ],
        links=[
            SankeyLink(
                source_node_id=f"node_{index % 30}",
                target_node_id=f"node_{(index + 1) % 30}",
                value=1.0,
                claim_class="model_derived_hypothesis",
                validation_required=True,
                source_artifact_ids=["artifact_context"],
            )
            for index in range(100)
        ],
    )


def _large_confirmatory() -> ConfirmatoryTestingOutput:
    return ConfirmatoryTestingOutput(
        artifact_id="artifact_confirmatory",
        tests=[
            ConfirmatoryTest(
                test_id=f"test_{index}",
                question="Should this source-backed axis be confirmed? " * 100,
                why_it_matters="It changes confidence in review only. " * 100,
                positive_interpretation="Supports continued review. " * 100,
                negative_interpretation="Weakens the review hypothesis. " * 100,
                priority="high",
                evidence_gap="Confirmatory evidence is missing. " * 100,
                source_claim_ids=["claim_0"],
            )
            for index in range(40)
        ],
        must_not_assume=["Do not assume clinical actionability. " * 80],
    )


def _large_tumor_behavior() -> TumorBehaviorModelOutput:
    return TumorBehaviorModelOutput(
        artifact_id="artifact_tumor_behavior",
        state_evidence=[
            TumorStateEvidence(
                state_label="proliferative",
                supporting_findings=["finding_flt3"],
                graph_support=["edge_flt3_neighbor_0"],
                tool_support=["artifact_tool"],
                medea_support=["artifact_medea"],
                evidence_class="model_derived_hypothesis",
                uncertainty="Requires bounded human review. " * 120,
                validation_needed=True,
            )
            for _index in range(30)
        ],
        transition_hypotheses=[
            TransitionHypothesis(
                from_state="proliferative",
                to_state="stress_adapted_survival",
                rationale="FLT3 and graph context support review only. " * 120,
                supporting_artifacts=["artifact_context"],
                confidence_label="needs_review",
                validation_status="needs_review",
                hypothesis_generating=True,
            )
            for _index in range(30)
        ],
        limitations=["No probabilities or treatment recommendations. " * 80],
    )


def _large_decision_brief() -> OncologistDecisionBrief:
    return OncologistDecisionBrief(
        artifact_id="artifact_decision_brief",
        clinical_decision_summary="Reviewable FLT3 context. " * 200,
        current_tumor_state=CurrentTumorState(
            dominant_drivers=["FLT3 internal tandem duplication. " * 80],
            active_pathways=["FLT3 signaling pathway context. " * 80],
            co_drivers=["co-driver context. " * 80],
            actionable_alterations=["FLT3 source-backed alteration. " * 80],
            resistance_or_uncertain_alterations=[
                "resistance uncertainty. " * 80
            ],
            immune_and_repair_context=["immune repair context. " * 80],
            missing_data=["longitudinal sample missing. " * 80],
            source_artifact_ids=["artifact_context"],
        ),
        actionable_biology=[
            ActionableBiologyItem(
                biology="FLT3 pathway biology. " * 80,
                alteration_or_marker="FLT3 internal tandem duplication",
                actionability="insufficient_evidence",
                evidence_level="source-backed hypothesis requiring review",
                rationale="Report and graph evidence support review. " * 80,
                uncertainty="Clinical use requires validation. " * 80,
                source_artifact_ids=["artifact_context"],
            )
            for _index in range(20)
        ],
        ranked_treatment_options=[
            RankedTreatmentOption(
                rank=index + 1,
                therapy_name_or_class="FLT3 review category. " * 80,
                clinical_use="insufficient_evidence",
                therapy_class="review context. " * 80,
                matched_biomarkers=["FLT3"],
                why_it_fits="The uploaded report includes FLT3 context. " * 80,
                evidence_level="source-backed hypothesis requiring review",
                resistance_risks=["pathway adaptation requires review. " * 40],
                required_before_use_tests=[
                    "Clinician validation required. " * 40
                ],
                limitations=["No final therapy selection is made. " * 40],
                source_artifact_ids=["artifact_context"],
            )
            for index in range(20)
        ],
        treatment_pressure_map=[
            TreatmentPressureMapRow(
                therapy_name_or_class="FLT3 review category. " * 80,
                target_or_pathway="FLT3 pathway. " * 80,
                why_it_fits="Source-backed context only. " * 80,
                selective_pressure="Pressure context requires review. " * 80,
                likely_escape_routes=["bypass signaling. " * 40],
                biomarkers_to_watch=["FLT3", "pathway marker. " * 40],
                evidence_basis=["artifact_context"],
                source_artifact_ids=["artifact_context"],
            )
            for _index in range(20)
        ],
        resistance_forecast=[
            ResistanceForecastItem(
                escape_route="bypass_signaling",
                description="Monitor for bypass signaling. " * 80,
                associated_treatment_pressure="FLT3 context. " * 80,
                supporting_evidence=["artifact_context"],
                biomarkers_to_monitor=["FLT3"],
                source_artifact_ids=["artifact_context"],
            )
            for _index in range(20)
        ],
        biomarker_watch_list=[
            BiomarkerWatchItem(
                biomarker="FLT3",
                alteration_type="insertion",
                why_watch="Potential bypass context. " * 80,
                associated_treatment_pressure="FLT3 context. " * 80,
                preferred_test="tissue_NGS",
                trigger="progression or therapy switch. " * 80,
                priority="high",
                source_artifact_ids=["artifact_context"],
            )
            for _index in range(20)
        ],
        retesting_triggers=[
            RetestingTrigger(
                clinical_event="radiographic progression. " * 80,
                recommended_test="tissue_NGS",
                rationale="Progression can reveal resistance. " * 80,
                what_result_changes="New resistance signal. " * 80,
                urgency="high",
                source_artifact_ids=["artifact_context"],
            )
            for _index in range(20)
        ],
        next_test_recommendations=[
            NextTestRecommendation(
                test_type="tissue_NGS",
                timing="at progression or before next systemic therapy. " * 80,
                rationale="Tissue can evaluate CNV and transformation. " * 80,
                biomarkers_or_questions=["FLT3", "new fusions"],
                result_that_would_change_management=(
                    "New resistance signal. " * 80
                ),
                limitations=["ctDNA can be considered if tissue unavailable."],
                source_artifact_ids=["artifact_context"],
                priority="high",
            )
            for _index in range(20)
        ],
        translational_assessment=TranslationalAssessmentOutput(
            artifact_id="artifact_translational_assessment",
            target_relevance=_large_question("target_relevance"),
            biomarker_evidence=_large_question("biomarker_evidence"),
            resistance_mechanisms=_large_question("resistance_mechanisms"),
            patient_population_alignment=_large_question(
                "patient_population_alignment"
            ),
            evidence_resolution=_large_question("evidence_resolution"),
        ),
        therapy_escape_sankey_paths=[
            TherapyEscapeSankeyPath(
                therapy_display_name="Actual agent unresolved. " * 80,
                therapy_source="unresolved",
                molecular_target_or_pathway="FLT3 pathway. " * 80,
                target_driver_status="source-backed review. " * 80,
                predicted_behavior_state="stress_adapted_survival",
                escape_pathway="bypass signaling. " * 80,
                monitoring_timing="at progression. " * 80,
                source_artifact_ids=["artifact_context"],
                confidence="needs_review",
            )
            for _index in range(20)
        ],
        evidence_sentence_map=[
            EvidenceSentence(
                evidence_id=f"evidence_{index}",
                evidence_label="Report finding",
                statement="FLT3 source-backed context. " * 80,
                source_type="report",
                quote="FLT3 internal tandem duplication",
                source_artifact_ids=["artifact_context"],
                source_chunk_ids=["chunk_1"],
            )
            for index in range(20)
        ],
        evidence_limitations=[
            EvidenceLimitation(
                limitation="No longitudinal sample was available. " * 80,
                impact="Resistance paths remain watch items. " * 80,
                needed_resolution="Repeat profiling at progression. " * 80,
                source_artifact_ids=["artifact_context"],
            )
            for _index in range(20)
        ],
        source_artifact_ids=["artifact_context"],
        source_chunk_ids=["chunk_1"],
    )


def _large_question(key: str) -> TranslationalQuestionAssessment:
    return TranslationalQuestionAssessment(
        question_key=key,
        question="Clinical translational question. " * 80,
        answer="Answer requires review and validation. " * 80,
        status="needs_validation",
        evidence_strength="weak",
        supporting_evidence=["source-backed context. " * 80],
        unresolved_evidence=["unresolved validation detail. " * 80],
        validation_next=["Clinician review required. " * 80],
        source_artifact_ids=["artifact_context"],
    )


def _large_claims() -> list[ClaimEvidenceOutput]:
    return [
        ClaimEvidenceOutput(
            claim_id=f"claim_{index}",
            claim="The source-backed molecular context supports review. " * 120,
            claim_class="model_derived_hypothesis",
            source_artifact_ids=["artifact_context"],
            evidence_source="report_graph_tool_medea_context",
            relevance="Links source evidence to review packet interpretation. " * 120,
            limitations="Requires human validation and is not treatment-directing. " * 120,
            validation_status="needs_review",
        )
        for index in range(50)
    ]
