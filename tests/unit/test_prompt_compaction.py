from __future__ import annotations

from copy import deepcopy

from translume_core.compiler.structured_model_artifacts import (
    _MAX_PROMPT_GRAPH_EDGES,
    _MAX_PROMPT_GRAPH_NODES,
    _MAX_PROMPT_HYPOTHESES,
    _MAX_PROMPT_SOURCE_TEXT_CHARS,
    compact_evidence_context_for_prompt,
    compact_graph_for_prompt,
    truncate_text,
)
from translume_schemas.evidence import EvidenceContextBundle
from translume_schemas.extraction import MolecularFinding, ReportExtractionOutput
from translume_schemas.graph import GraphEdge, GraphEvidenceArtifact, GraphNode
from translume_schemas.medea import MedeaReasoningArtifact
from translume_schemas.tools import ToolRunArtifact


def test_compact_evidence_context_preserves_grounding_and_caps_payload() -> None:
    context = _large_context()

    compact = compact_evidence_context_for_prompt(context)

    finding = compact["extraction"]["molecular_findings"][0]
    graph = compact["graph_evidence"]
    medea = compact["medea_reasoning"]

    assert finding["finding_id"] == "finding_flt3"
    assert finding["source_chunk_id"] == "chunk_1"
    assert "[truncated" in finding["source_text"]
    assert len(finding["source_text"]) > _MAX_PROMPT_SOURCE_TEXT_CHARS
    assert len(graph["nodes"]) <= _MAX_PROMPT_GRAPH_NODES
    assert len(graph["edges"]) <= _MAX_PROMPT_GRAPH_EDGES
    assert graph["nodes"][0]["node_id"] == "node_flt3"
    assert graph["truncation"]["original_nodes"] > graph["truncation"]["kept_nodes"]
    assert "not be interpreted as absent" in graph["truncation"]["notice"]
    assert medea["artifact_id"] == "artifact_medea"
    assert len(medea["supported_hypotheses"]) == _MAX_PROMPT_HYPOTHESES


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
    )
    tool = ToolRunArtifact(
        artifact_id="artifact_tool",
        workflow="literature_validation",
        input_entity_ids=["entity_flt3"],
        summary="FLT3 review context. " * 200,
        evidence_items=[
            {"entity": "FLT3", "context": f"evidence item {index}"}
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
