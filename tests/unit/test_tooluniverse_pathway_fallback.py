from __future__ import annotations

import pytest

from translume_adapters.tool_providers.tooluniverse_runtime import (
    ToolUniverseWorkflowCatalog,
    ToolUniverseWorkflowError,
    run_workflow,
)
from translume_schemas.entities import NormalizedEntity, NormalizedEntitySet
from translume_schemas.graph import GraphEvidenceArtifact


class PathwayEngine:
    """Test engine that models configured pathway-source responses."""

    def __init__(self, responses: dict[str, object]) -> None:
        self._responses = responses

    def run_one_function(
        self,
        function_call: dict[str, object],
        **_: object,
    ) -> object:
        return self._responses[str(function_call["name"])]


def test_pathway_workflow_records_reactome_403_and_uses_fallback() -> None:
    """A Reactome block should not prevent a real fallback source from running.

    Acceptance criteria:
        1. Reactome 403 becomes unavailable-source evidence.
        2. A successful PathwayCommons result is preserved.
        3. The artifact requires human review and carries an availability warning.
    """
    artifact = run_workflow(
        workflow="pathway_context",
        catalog=_pathway_catalog(),
        engine=PathwayEngine(
            {
                "ReactomeContent_search": {
                    "status": "error",
                    "error": "Reactome Content Service HTTP error: 403",
                },
                "PathwayCommons_search": {"summary": "PathwayCommons result"},
                "kegg_search_pathway": {"summary": "KEGG result"},
            }
        ),
        entities=_entities(),
        graph=_graph(),
    )

    unavailable = next(
        item
        for item in artifact.evidence_items
        if item["status"] == "unavailable_external_source"
    )
    assert unavailable["source"] == "ReactomeContent_search"
    assert unavailable["http_status"] == "403"
    assert "PathwayCommons result" in artifact.summary
    assert artifact.warnings == ["external_source_unavailable:ReactomeContent_search:403"]


def test_pathway_workflow_fails_when_all_sources_are_unavailable() -> None:
    """Pathway workflow should fail when no configured source produces evidence.

    Acceptance criteria:
        1. Every unavailable source is attempted.
        2. No partial evidence artifact is returned.
        3. The failure states the minimum-success requirement.
    """
    engine = PathwayEngine(
        {
            "ReactomeContent_search": {"status": "error", "error": "HTTP error: 403"},
            "PathwayCommons_search": {"status": "error", "error": "HTTP error: 503"},
            "kegg_search_pathway": {"status": "error", "error": "HTTP error: 503"},
        }
    )

    with pytest.raises(ToolUniverseWorkflowError, match="at least 1 successful"):
        run_workflow(
            workflow="pathway_context",
            catalog=_pathway_catalog(),
            engine=engine,
            entities=_entities(),
            graph=_graph(),
        )


def _pathway_catalog() -> ToolUniverseWorkflowCatalog:
    steps = [
        {
            "tool_name": tool_name,
            "required_context": ["pathway_query"],
            "failure_policy": "record_unavailable",
            "arguments": {"query": "$pathway_query"},
        }
        for tool_name in (
            "ReactomeContent_search",
            "PathwayCommons_search",
            "kegg_search_pathway",
        )
    ]
    return ToolUniverseWorkflowCatalog(
        required_workflows=("pathway_context",),
        workflows={
            "pathway_context": {
                "minimum_successful_steps": 1,
                "required_context": ["pathway_query"],
                "steps": steps,
            }
        },
    )


def _entities() -> NormalizedEntitySet:
    return NormalizedEntitySet(
        artifact_id="artifact_entities",
        case_id="case_1",
        session_id="session_1",
        entities=[
            NormalizedEntity(
                entity_id="entity_gene",
                entity_type="gene",
                original_text="TP53",
                normalized_label="TP53",
                source_artifact_id="artifact_report",
            )
        ],
    )


def _graph() -> GraphEvidenceArtifact:
    return GraphEvidenceArtifact(
        artifact_id="artifact_graph",
        source_entity_ids=["entity_gene"],
        nodes=[],
        edges=[],
    )
