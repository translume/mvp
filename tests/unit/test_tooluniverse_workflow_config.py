from __future__ import annotations

import json
from pathlib import Path

import pytest

from translume_adapters.tool_providers.tooluniverse_runtime import (
    REQUIRED_MVP_WORKFLOWS,
    ToolUniverseWorkflowError,
    load_workflow_catalog,
    workflow_tool_names,
)


CONFIG_PATH = Path("configs/local/tooluniverse_workflows.json")


def test_default_tooluniverse_config_covers_required_mvp_workflows() -> None:
    catalog = load_workflow_catalog(CONFIG_PATH)
    assert set(catalog.required_workflows) == set(REQUIRED_MVP_WORKFLOWS)
    assert set(REQUIRED_MVP_WORKFLOWS) <= set(catalog.workflows)
    tool_names = workflow_tool_names(catalog, catalog.required_workflows)
    assert "PubMed_search_articles" in tool_names
    assert "EuropePMC_search_articles" in tool_names
    assert "kegg_search_pathway" in tool_names
    assert "OpenTargets_search_category_counts_by_query_string" in tool_names
    assert "ClinVar_search_variants" in tool_names
    assert "search_clinical_trials" in tool_names


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
