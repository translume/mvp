"""Unit tests for the local Reactome GraphDB ToolUniverse override."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from translume_adapters.tool_providers.reactome_graphdb import (
    ReactomeContentSearchOverride,
    ReactomeGraphDBConfig,
    ReactomePathwayMatch,
    ReactomeSearchRequest,
    merge_and_rank_matches,
    normalize_reactome_search_request,
    to_tooluniverse_reactome_result,
    validate_reactome_graphdb_config,
)
from translume_adapters.tool_providers.tooluniverse_runtime import (
    ToolUniverseWorkflowError,
    result_to_evidence_items,
    run_workflow_step,
    validate_local_tool_overrides,
    vendor_tool_names,
)


FIXTURE = (
    Path(__file__).parents[1]
    / "fixtures"
    / "tooluniverse"
    / "reactome_content_search_success.json"
)


@dataclass(frozen=True)
class FakeReactomeBackend:
    """Immutable no-I/O backend used by pure override tests."""

    text: tuple[ReactomePathwayMatch, ...] = ()
    genes: tuple[ReactomePathwayMatch, ...] = ()

    def search_text(self, **_: object) -> tuple[ReactomePathwayMatch, ...]:
        return self.text

    def search_genes(self, **_: object) -> tuple[ReactomePathwayMatch, ...]:
        return self.genes

    def health_report(self) -> dict[str, object]:
        return {
            "status": "healthy",
            "reactome_graphdb_available": True,
            "reactome_graphdb_database": "graph.db",
            "reactome_graphdb_configured_release": "97",
            "reactome_graphdb_actual_release": "97",
            "reactome_graphdb_release_matches": True,
            "reactome_pathway_count": 1,
            "error": None,
        }

    def close(self) -> None:
        return None


class RecordingOverride:
    """Record exact-name dispatch without invoking ToolUniverse."""

    tool_name = "ReactomeContent_search"

    def __init__(self) -> None:
        self.calls = 0

    def run(self, **_: object) -> dict[str, object]:
        self.calls += 1
        return {"status": "success", "data": {"results": []}}

    def health_report(self) -> dict[str, object]:
        return {"status": "healthy"}

    def close(self) -> None:
        return None


class FailingVendorEngine:
    """Prove a locally overridden name never reaches the vendor runner."""

    def run_one_function(self, *_: object, **__: object) -> object:
        raise AssertionError("vendor runner was called for local Reactome")


def _config(**updates: object) -> ReactomeGraphDBConfig:
    values = {
        "uri": "bolt://reactome-graphdb:7687",
        "database": "graph.db",
        "auth_mode": "basic",
        "username": "neo4j",
        "password": "secret-value",
        "release": "97",
    }
    values.update(updates)
    return ReactomeGraphDBConfig(**values)


def _request() -> ReactomeSearchRequest:
    return ReactomeSearchRequest(
        query="TP53",
        species="Homo sapiens",
        types=("Pathway",),
        cluster=True,
        genes=("TP53",),
        pathway_terms=("TP53",),
        max_results=30,
    )


def test_upstream_contract_fixture_and_flattening_are_frozen() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert payload["status"] == "success"
    assert set(payload["data"]) == {
        "query",
        "species",
        "types_searched",
        "total_results",
        "results",
    }
    assert set(payload["data"]["results"][0]) == {
        "type",
        "stId",
        "name",
        "species",
        "compartments",
        "is_disease",
    }
    items = result_to_evidence_items(
        "pathway_context",
        0,
        {"tool_name": "ReactomeContent_search"},
        payload,
    )
    assert items[0]["tool_name"] == "ReactomeContent_search"
    assert json.loads(items[0]["data"])["results"]
    assert json.loads(items[0]["metadata"])["query"] == "TP53"


@pytest.mark.parametrize(
    "uri",
    (
        "https://reactome.org/ContentService",
        "bolt://reactome.org:7687",
    ),
)
def test_config_rejects_http_or_remote_reactome_uri(uri: str) -> None:
    with pytest.raises(ValueError, match="REACTOME_NEO4J_URI"):
        validate_reactome_graphdb_config(_config(uri=uri))


def test_config_rejects_missing_basic_credentials_and_hides_password() -> None:
    config = _config(password=None)
    with pytest.raises(ValueError, match="REACTOME_NEO4J_PASSWORD"):
        validate_reactome_graphdb_config(config)
    assert "secret-value" not in repr(_config())


def test_request_uses_only_structured_genes_and_caps_context() -> None:
    request = normalize_reactome_search_request(
        arguments={
            "query": "TP53 sarcoma copy_number_loss",
            "species": "Homo sapiens",
            "types": ["Pathway"],
            "cluster": "true",
        },
        context={
            "pathway_genes": ["TP53", "EGFR", "MTAP"],
            "pathway_terms": ["TP53", "sarcoma", "cell cycle"],
            "copy_number_loss": ["copy_number_loss"],
        },
        config=_config(max_query_terms=2),
    )
    assert request.genes == ("TP53", "EGFR")
    assert "copy_number_loss" not in request.genes
    assert request.pathway_terms == ("TP53", "sarcoma")


def test_request_falls_back_to_bounded_direct_query_terms() -> None:
    request = normalize_reactome_search_request(
        arguments={"query": "PI3K AKT signaling"},
        context={},
        config=_config(max_query_terms=2),
    )
    assert request.pathway_terms == (
        "PI3K AKT signaling",
        "PI3K",
    )


def test_merge_deduplicates_case_insensitive_stable_ids_and_ranks_exact() -> None:
    broad = ReactomePathwayMatch(
        stable_id="R-HSA-1",
        name="Broad pathway",
        species="Homo sapiens",
        is_disease=False,
        matched_genes=("TP53",),
    )
    exact = ReactomePathwayMatch(
        stable_id="R-HSA-2",
        name="Exact pathway",
        species="Homo sapiens",
        is_disease=False,
        matched_terms=("R-HSA-2",),
    )
    duplicate = ReactomePathwayMatch(
        stable_id="r-hsa-1",
        name="Broad pathway",
        species="Homo sapiens",
        is_disease=False,
        matched_terms=("TP53",),
    )
    request = _request().__class__(
        **{**_request().__dict__, "query": "R-HSA-2"}
    )
    matches = merge_and_rank_matches(
        request=request,
        text_matches=(exact, duplicate),
        gene_matches=(broad,),
    )
    assert [item.stable_id for item in matches] == ["R-HSA-2", "r-hsa-1"]
    assert len(matches) == 2


def test_tooluniverse_response_matches_public_contract_and_local_metadata() -> None:
    result = to_tooluniverse_reactome_result(
        request=_request(),
        matches=(
            ReactomePathwayMatch(
                stable_id="R-HSA-000000",
                name="Example pathway",
                species="Homo sapiens",
                is_disease=False,
            ),
        ),
        config=_config(),
    )
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert set(result["data"]) == set(fixture["data"])
    assert set(result["data"]["results"][0]) == set(
        fixture["data"]["results"][0]
    )
    assert result["metadata"]["remote_api_used"] is False
    assert result["metadata"]["configured_release"] == "97"


def test_zero_matches_are_a_successful_tooluniverse_result() -> None:
    override = ReactomeContentSearchOverride(
        config=_config(),
        backend=FakeReactomeBackend(),
    )
    result = override.run(
        arguments={"query": "TP53", "types": "Pathway"},
        context={"pathway_genes": ["TP53"]},
        use_cache=True,
        validate=True,
    )
    assert result["status"] == "success"
    assert result["data"]["total_results"] == 0
    assert result["data"]["results"] == []


def test_runtime_dispatches_exact_reactome_name_locally() -> None:
    override = RecordingOverride()
    result = run_workflow_step(
        workflow="pathway_context",
        step_index=0,
        step={
            "tool_name": "ReactomeContent_search",
            "arguments": {"query": "$pathway_query"},
        },
        engine=FailingVendorEngine(),
        context={"pathway_query": "TP53"},
        local_tool_overrides={override.tool_name: override},
    )
    assert override.calls == 1
    assert result["status"] == "success"


def test_vendor_names_exclude_only_exact_local_override() -> None:
    names = vendor_tool_names(
        (
            "ReactomeContent_search",
            "PathwayCommons_search",
            "kegg_search_pathway",
        ),
        frozenset({"ReactomeContent_search"}),
    )
    assert names == ("PathwayCommons_search", "kegg_search_pathway")


def test_override_key_must_match_handler_tool_name() -> None:
    with pytest.raises(ToolUniverseWorkflowError, match="does not match"):
        validate_local_tool_overrides({"ReactomeTypo": RecordingOverride()})
