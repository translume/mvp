from __future__ import annotations

import json
from pathlib import Path

import pytest

from translume_adapters.tool_providers.tooluniverse_runtime import (
    MAX_GRAPH_QUERY_TERMS,
    MAX_TOOL_QUERY_TERMS,
    REQUIRED_MVP_WORKFLOWS,
    ToolUniverseWorkflowError,
    load_workflow_catalog,
    template_context,
    workflow_tool_names,
)
from translume_schemas.entities import NormalizedEntity, NormalizedEntitySet
from translume_schemas.graph import GraphEdge, GraphEvidenceArtifact, GraphNode, GraphSubgraphEvidence


CONFIG_PATH = Path("configs/local/tooluniverse_workflows.json")


def test_default_tooluniverse_config_covers_required_mvp_workflows() -> None:
    catalog = load_workflow_catalog(CONFIG_PATH)
    assert set(catalog.required_workflows) == set(REQUIRED_MVP_WORKFLOWS)
    assert set(REQUIRED_MVP_WORKFLOWS) <= set(catalog.workflows)
    pathway_steps = catalog.workflows["pathway_context"]["steps"]
    pathway_commons_step = next(
        step
        for step in pathway_steps
        if step["tool_name"] == "PathwayCommons_search"
    )
    tool_names = workflow_tool_names(catalog, catalog.required_workflows)
    assert "PubMed_search_articles" in tool_names
    assert "EuropePMC_search_articles" in tool_names
    assert "kegg_search_pathway" in tool_names
    assert "OpenTargets_search_category_counts_by_query_string" in tool_names
    assert "ClinVar_search_variants" in tool_names
    assert "search_clinical_trials" in tool_names
    assert pathway_commons_step["arguments"]["type"] == "Pathway"
    assert (
        catalog.workflows["therapy_context"]["steps"][0]["arguments"]["queryString"]
        == "$drug_target_biomarker_query"
    )
    assert (
        catalog.workflows["resistance_mechanism_context"]["steps"][0]["arguments"]["query"]
        == "$resistance_path_query"
    )
    assert (
        catalog.workflows["biomarker_retesting_context"]["steps"][0]["arguments"]["query"]
        == "$biomarker_monitoring_query"
    )


def test_tooluniverse_template_context_bounds_external_queries() -> None:
    entities = NormalizedEntitySet(
        artifact_id="artifact_entities",
        case_id="case",
        session_id="session",
        entities=[
            NormalizedEntity(
                entity_id="entity_disease",
                entity_type="disease",
                original_text="AML",
                normalized_label="acute myeloid leukemia",
                source_artifact_id="artifact_report",
            ),
            NormalizedEntity(
                entity_id="entity_gene",
                entity_type="gene",
                original_text="FLT3",
                normalized_label="FLT3",
                source_artifact_id="artifact_report",
            ),
            NormalizedEntity(
                entity_id="entity_variant",
                entity_type="variant",
                original_text="ITD",
                normalized_label="internal tandem duplication",
                source_artifact_id="artifact_report",
            ),
        ],
    )
    graph = GraphEvidenceArtifact(
        artifact_id="artifact_graph",
        source_entity_ids=["entity_gene"],
        nodes=[
            GraphNode(
                node_id=f"node_{index}",
                label=f"expanded graph term {index}",
                kind="pathway",
                source="optimuskg",
            )
            for index in range(30)
        ],
        edges=[
            GraphEdge(
                edge_id="edge_1",
                source_node_id="node_1",
                target_node_id="node_2",
                relation_type="participates_in",
                source="optimuskg",
            )
        ],
    )

    context = template_context(entities, graph)

    assert len(context["graph_nodes"]) == 30
    assert context["first_gene"] == "FLT3"
    assert context["first_disease"] == "acute myeloid leukemia"
    assert "acute myeloid leukemia" in context["literature_query"]
    assert f"expanded graph term {MAX_GRAPH_QUERY_TERMS - 1}" in context["literature_query"]
    assert f"expanded graph term {MAX_GRAPH_QUERY_TERMS}" not in context["literature_query"]
    assert "expanded graph term 29" not in context["literature_query"]
    assert MAX_TOOL_QUERY_TERMS == 8


def test_tooluniverse_config_rejects_missing_required_workflow(tmp_path: Path) -> None:
    path = tmp_path / "tooluniverse_workflows.json"
    path.write_text(
        json.dumps(
            {
                "required_workflows": list(REQUIRED_MVP_WORKFLOWS),
                "workflows": {
                    "literature_validation": {
                        "steps": [
                            {"tool_name": "PubMed_search_articles", "arguments": {"query": "$literature_query"}}
                        ]
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ToolUniverseWorkflowError, match="missing required workflows"):
        load_workflow_catalog(path)


def test_tooluniverse_config_rejects_empty_steps(tmp_path: Path) -> None:
    path = tmp_path / "tooluniverse_workflows.json"
    path.write_text(
        json.dumps(
            {
                "required_workflows": ["literature_validation"],
                "workflows": {"literature_validation": {"steps": []}},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ToolUniverseWorkflowError, match="no executable steps"):
        load_workflow_catalog(path)


def test_tooluniverse_template_context_exposes_targeted_graph_queries() -> None:
    entities = NormalizedEntitySet(
        artifact_id="artifact_entities",
        case_id="case",
        session_id="session",
        entities=[
            NormalizedEntity(
                entity_id="entity_disease",
                entity_type="disease",
                original_text="lung cancer",
                normalized_label="lung cancer",
                source_artifact_id="artifact_report",
            ),
            NormalizedEntity(
                entity_id="entity_gene",
                entity_type="gene",
                original_text="EGFR",
                normalized_label="EGFR",
                source_artifact_id="artifact_report",
            ),
        ],
    )
    graph = GraphEvidenceArtifact(
        artifact_id="artifact_graph",
        source_entity_ids=["entity_gene"],
        nodes=[
            GraphNode(
                node_id="node_egfr",
                label="EGFR",
                kind="gene",
                source="optimuskg",
            ),
            GraphNode(
                node_id="node_met",
                label="MET amplification bypass",
                kind="resistance",
                source="optimuskg",
            ),
        ],
        edges=[
            GraphEdge(
                edge_id="edge_resistance",
                source_node_id="node_egfr",
                target_node_id="node_met",
                relation_type="resistance_bypass_path",
                source="optimuskg",
            ),
            GraphEdge(
                edge_id="edge_biomarker",
                source_node_id="node_egfr",
                target_node_id="node_met",
                relation_type="biomarker_monitoring_path",
                source="optimuskg",
            ),
        ],
        retrieval_modes=[
            "general_context",
            "resistance_path",
            "biomarker_monitoring",
        ],
        subgraphs=[
            GraphSubgraphEvidence(
                retrieval_mode="resistance_path",
                query_terms=["EGFR", "MET amplification bypass"],
                node_ids=["node_egfr", "node_met"],
                edge_ids=["edge_resistance"],
            ),
            GraphSubgraphEvidence(
                retrieval_mode="biomarker_monitoring",
                query_terms=["EGFR", "ctDNA"],
                node_ids=["node_egfr", "node_met"],
                edge_ids=["edge_biomarker"],
            ),
        ],
    )

    context = template_context(entities, graph)

    assert context["graph_retrieval_modes"] == [
        "general_context",
        "resistance_path",
        "biomarker_monitoring",
    ]
    assert "MET amplification bypass" in context["resistance_path_query"]
    assert "resistance_bypass_path" in context["resistance_path_query"]
    assert "ctDNA" in context["biomarker_monitoring_query"]
    assert "biomarker_monitoring_path" in context["biomarker_monitoring_query"]
