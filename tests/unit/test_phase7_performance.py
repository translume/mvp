from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path

import pytest

from translume_core.compiler.decision_brief import (
    DecisionBriefLatencyBudgets,
    generate_current_tumor_state_stage_with_model,
)
from translume_core.performance import (
    AsyncInMemoryCache,
    LatencyBudgetExceededError,
    run_with_latency_budget,
    stable_cache_key,
)
from translume_core.workflow import (
    TranslumeWorkflowConfig,
    TranslumeWorkflowProviders,
    _get_graph_evidence,
    _get_tool_outputs,
)
from translume_schemas.entities import NormalizedEntity, NormalizedEntitySet
from translume_schemas.evidence import EvidenceContextBundle
from translume_schemas.extraction import MolecularFinding, ReportExtractionOutput
from translume_schemas.graph import GraphEdge, GraphEvidenceArtifact, GraphNode
from translume_schemas.medea import MedeaReasoningArtifact
from translume_schemas.tools import ToolRunArtifact


@pytest.mark.asyncio
async def test_async_cache_coalesces_concurrent_provider_calls() -> None:
    cache = AsyncInMemoryCache()
    calls = 0

    async def factory() -> dict[str, list[str]]:
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.01)
        return {"values": ["EGFR"]}

    first, second = await asyncio.gather(
        cache.get_or_set("same-key", factory, ttl_seconds=60),
        cache.get_or_set("same-key", factory, ttl_seconds=60),
    )
    first["values"].append("mutated")
    third = await cache.get_or_set("same-key", factory, ttl_seconds=60)

    assert calls == 1
    assert second == {"values": ["EGFR"]}
    assert third == {"values": ["EGFR"]}
    assert cache.stats().hits >= 2
    assert cache.stats().stores == 1


@pytest.mark.asyncio
async def test_latency_budget_raises_without_returning_late_result() -> None:
    async def slow_stage() -> str:
        await asyncio.sleep(0.05)
        return "late"

    with pytest.raises(LatencyBudgetExceededError, match="slow_stage"):
        await run_with_latency_budget(
            stage_name="slow_stage",
            timeout_seconds=0.001,
            awaitable=slow_stage(),
        )


@pytest.mark.asyncio
async def test_graph_provider_lookup_is_cached(tmp_path: Path) -> None:
    provider = CountingGraphProvider()
    cache = AsyncInMemoryCache()
    config = TranslumeWorkflowConfig(
        storage_root=tmp_path,
        require_mims=True,
        enable_provider_cache=True,
        graph_cache_ttl_seconds=60,
    )
    providers = TranslumeWorkflowProviders(
        graph_provider=provider,
        performance_cache=cache,
    )
    entities = _entities()

    first = await _get_graph_evidence(entities, providers, config)
    second = await _get_graph_evidence(entities, providers, config)

    assert provider.calls == 1
    assert first == second
    assert first is not second
    assert cache.stats().hits == 1


@pytest.mark.asyncio
async def test_graph_provider_cache_can_be_disabled(tmp_path: Path) -> None:
    provider = CountingGraphProvider()
    config = TranslumeWorkflowConfig(
        storage_root=tmp_path,
        require_mims=True,
        enable_provider_cache=False,
    )
    providers = TranslumeWorkflowProviders(graph_provider=provider)
    entities = _entities()

    await _get_graph_evidence(entities, providers, config)
    await _get_graph_evidence(entities, providers, config)

    assert provider.calls == 2


@pytest.mark.asyncio
async def test_tooluniverse_lookup_is_cached(tmp_path: Path) -> None:
    provider = CountingToolProvider()
    cache = AsyncInMemoryCache()
    config = TranslumeWorkflowConfig(
        storage_root=tmp_path,
        require_mims=True,
        enable_provider_cache=True,
        tool_cache_ttl_seconds=60,
        tool_workflows=("therapy_context",),
    )
    providers = TranslumeWorkflowProviders(
        tool_provider=provider,
        performance_cache=cache,
    )
    entities = _entities()
    graph = GraphEvidenceArtifact(
        artifact_id="artifact_graph",
        source_entity_ids=["entity_egfr"],
        nodes=[],
        edges=[],
    )

    first = await _get_tool_outputs(entities, graph, providers, config)
    second = await _get_tool_outputs(entities, graph, providers, config)

    assert provider.calls == 1
    assert first == second
    assert first is not second
    assert cache.stats().hits == 1


@pytest.mark.asyncio
async def test_decision_brief_stage_latency_budget_wraps_model_call(
    tmp_path: Path,
) -> None:
    _write_current_state_prompts(tmp_path)
    provider = SlowStructuredModelProvider()

    with pytest.raises(LatencyBudgetExceededError, match="current_tumor_state"):
        await generate_current_tumor_state_stage_with_model(
            context=_context(),
            model_provider=provider,
            model_name="local-test-model",
            prompts_root=tmp_path,
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            latency_budgets=DecisionBriefLatencyBudgets(
                stage_timeout_seconds={"current_tumor_state": 0.001},
            ),
        )

    assert provider.calls == 1


def test_stable_cache_key_is_order_insensitive_for_mapping_values() -> None:
    assert stable_cache_key("x", {"a": 1, "b": 2}) == stable_cache_key(
        "x",
        {"b": 2, "a": 1},
    )


class CountingGraphProvider:
    def __init__(self) -> None:
        self.calls = 0

    async def retrieve_context(
        self,
        entities: NormalizedEntitySet,
        *,
        retrieval_modes: tuple[str, ...],
    ) -> GraphEvidenceArtifact:
        self.calls += 1
        return GraphEvidenceArtifact(
            artifact_id="artifact_graph",
            source_entity_ids=[entity.entity_id for entity in entities.entities],
            nodes=[
                GraphNode(
                    node_id="GENE:EGFR",
                    label="EGFR",
                    kind="gene",
                    source="fixture",
                )
            ],
            edges=[
                GraphEdge(
                    edge_id="edge_egfr_mapk",
                    source_node_id="GENE:EGFR",
                    target_node_id="PATHWAY:MAPK",
                    relation_type="signals_through",
                    source="fixture",
                )
            ],
            retrieval_modes=list(retrieval_modes),
        )


class CountingToolProvider:
    def __init__(self) -> None:
        self.calls = 0

    async def run_workflows(
        self,
        *,
        workflows: list[str],
        entities: NormalizedEntitySet,
        graph: GraphEvidenceArtifact,
    ) -> list[ToolRunArtifact]:
        self.calls += 1
        return [
            ToolRunArtifact(
                artifact_id="artifact_tool_therapy",
                workflow=workflows[0],
                input_entity_ids=[entity.entity_id for entity in entities.entities],
                summary=f"therapy context for {graph.artifact_id}",
                evidence_items=[{"source": "fixture", "statement": "EGFR context"}],
            )
        ]


class SlowStructuredModelProvider:
    def __init__(self) -> None:
        self.calls = 0

    async def structured_completion(self, **_kwargs: object) -> dict[str, object]:
        self.calls += 1
        await asyncio.sleep(0.05)
        return {}


def _entities() -> NormalizedEntitySet:
    return NormalizedEntitySet(
        artifact_id="artifact_entities",
        case_id="case_1",
        session_id="session_1",
        entities=[
            NormalizedEntity(
                entity_id="entity_egfr",
                entity_type="gene",
                original_text="EGFR",
                normalized_label="EGFR",
                source_artifact_id="artifact_report",
            )
        ],
    )


def _context() -> EvidenceContextBundle:
    extraction = ReportExtractionOutput(
        artifact_id="artifact_report",
        report_type="NGS",
        disease="lung adenocarcinoma",
        specimen="tissue",
        source_file_id="source_file_1",
        molecular_findings=[
            MolecularFinding(
                finding_id="finding_egfr",
                gene="EGFR",
                alteration="L858R",
                alteration_type="variant",
                source_chunk_id="chunk_1",
                confidence=0.91,
            )
        ],
    )
    return EvidenceContextBundle(
        artifact_id="artifact_context",
        extraction=extraction,
        graph_evidence=GraphEvidenceArtifact(
            artifact_id="artifact_graph",
            source_entity_ids=["entity_egfr"],
            nodes=[],
            edges=[],
        ),
        tool_outputs=[],
        medea_reasoning=MedeaReasoningArtifact(
            artifact_id="artifact_medea",
            reasoning_mode="fixture",
            summary="",
            supported_hypotheses=[],
            weakened_hypotheses=[],
        ),
    )


def _write_current_state_prompts(path: Path) -> None:
    path.joinpath("current_tumor_state_system.md").write_text(
        "Return JSON only.",
        encoding="utf-8",
    )
    path.joinpath("current_tumor_state_user.md").write_text(
        "The artifact_id must be exactly:\n{planned_artifact_id}\n\n{payload_json}",
        encoding="utf-8",
    )
