from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from translume_adapters.errors import ProviderUnavailableError
from translume_adapters.graph_providers.optimuskg_graph_provider import OptimusKGGraphProvider
from translume_adapters.model_providers.blocked_remote_provider import BlockedRemoteModelProvider
from translume_adapters.reasoning_providers.medea_reasoning_provider import MedeaReasoningProvider
from translume_adapters.tool_providers.tooluniverse_provider import ToolUniverseProvider
from translume_schemas.entities import NormalizedEntity, NormalizedEntitySet
from translume_schemas.evidence import EvidenceContextBundle
from translume_schemas.extraction import ReportExtractionOutput
from translume_schemas.graph import GraphEvidenceArtifact
from translume_schemas.medea import MedeaReasoningArtifact


def _write_fake_optimuskg_repo(tmp_path: Path):
    """Create a tiny real OptimusKG-shaped package with parquet graph data."""
    import json
    pl = pytest.importorskip("polars")

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


def _entities() -> NormalizedEntitySet:
    return NormalizedEntitySet(
        artifact_id="artifact_entities",
        case_id="case",
        session_id="sess",
        entities=[
            NormalizedEntity(
                entity_id="e1",
                entity_type="gene",
                original_text="CHEK2",
                normalized_label="CHEK2",
                source_artifact_id="a",
            )
        ],
    )


@pytest.mark.asyncio
async def test_blocked_remote_provider_fails() -> None:
    with pytest.raises(RuntimeError, match="blocked"):
        await BlockedRemoteModelProvider().structured_completion()


@pytest.mark.asyncio
async def test_optimuskg_provider_requires_real_repo(tmp_path) -> None:
    with pytest.raises(ProviderUnavailableError):
        await OptimusKGGraphProvider(tmp_path / "missing_repo").retrieve_context(_entities())


@pytest.mark.asyncio
async def test_optimuskg_provider_uses_real_package_parquet_path(tmp_path, monkeypatch) -> None:
    monkeypatch.delitem(sys.modules, "optimuskg", raising=False)
    repo, cache_dir = _write_fake_optimuskg_repo(tmp_path)
    graph = await OptimusKGGraphProvider(
        repo,
        cache_dir=cache_dir,
        max_edges=10,
    ).retrieve_context(_entities())
    assert graph.edges[0].relation_type == "participates_in"
    assert graph.nodes[0].source == "optimuskg_parquet"
    assert graph.nodes[0].provenance["runtime"] == "optimuskg_python_client_get_file_polars_parquet"


@pytest.mark.asyncio
async def test_optimuskg_provider_rejects_csv_substitute(tmp_path) -> None:
    edge_file = tmp_path / "edges.csv"
    edge_file.write_text("subject,relation_type,object\nCHEK2,related_to,DDR\n", encoding="utf-8")
    with pytest.raises(ProviderUnavailableError, match="OptimusKG repository"):
        await OptimusKGGraphProvider(edge_file).retrieve_context(_entities())


def _write_fake_tooluniverse_repo(tmp_path):
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
        "        return {\"summary\": \"real fake-package ToolUniverse tool executed\", \"call\": function_call_json}\n",
        encoding="utf-8",
    )
    return repo


def _write_tooluniverse_workflow_config(tmp_path, required=None):
    workflows = required or [
        "literature_validation",
        "pathway_context",
        "target_context",
        "variant_context",
        "trial_context_review",
    ]
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


@pytest.mark.asyncio
async def test_tooluniverse_provider_executes_real_configured_runtime(tmp_path, monkeypatch) -> None:
    monkeypatch.delitem(__import__("sys").modules, "tooluniverse", raising=False)
    repo = _write_fake_tooluniverse_repo(tmp_path)
    config_path = _write_tooluniverse_workflow_config(tmp_path)
    entities = _entities()
    graph = GraphEvidenceArtifact(artifact_id="g", source_entity_ids=[], nodes=[], edges=[])
    provider = ToolUniverseProvider(repo, config_path)
    outputs = await provider.run_workflows(
        workflows=["literature_validation"],
        entities=entities,
        graph=graph,
    )
    assert outputs[0].workflow == "literature_validation"
    assert outputs[0].evidence_items[0]["tool_name"] == "PubMed_search_articles"
    with pytest.raises(Exception, match="not configured"):
        await provider.run_workflows(workflows=["unsafe"], entities=entities, graph=graph)


@pytest.mark.asyncio
async def test_medea_provider_reads_bounded_reasoning_artifact(tmp_path) -> None:
    reasoning = tmp_path / "reasoning.json"
    reasoning.write_text(
        json.dumps(
            {
                "reasoning_mode": "bounded_review_support",
                "summary": "Local Medea reasoning requires review.",
                "supported_hypotheses": ["hypothesis support"],
                "weakened_hypotheses": [],
            }
        ),
        encoding="utf-8",
    )
    extraction = ReportExtractionOutput(
        artifact_id="e",
        report_type="NGS",
        molecular_findings=[],
        source_file_id="f",
    )
    graph = GraphEvidenceArtifact(artifact_id="g", source_entity_ids=[], nodes=[], edges=[])
    medea = MedeaReasoningArtifact(
        artifact_id="m0",
        reasoning_mode="bounded",
        summary="",
        supported_hypotheses=[],
        weakened_hypotheses=[],
    )
    context = EvidenceContextBundle(
        artifact_id="ctx",
        extraction=extraction,
        graph_evidence=graph,
        tool_outputs=[],
        medea_reasoning=medea,
    )
    result = await MedeaReasoningProvider(reasoning).reason_over_context(context)
    assert result.summary == "Local Medea reasoning requires review."
    assert result.requires_human_review is True
