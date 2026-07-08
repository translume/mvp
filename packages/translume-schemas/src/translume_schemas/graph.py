from __future__ import annotations

from typing import Literal

from translume_schemas.base import TranslumeBaseModel


GraphRetrievalMode = Literal[
    "general_context",
    "therapy_pressure",
    "resistance_path",
    "drug_target_biomarker",
    "biomarker_monitoring",
]


class GraphNode(TranslumeBaseModel):
    node_id: str
    label: str
    kind: str
    source: str
    provenance: dict[str, str] = {}


class GraphEdge(TranslumeBaseModel):
    edge_id: str
    source_node_id: str
    target_node_id: str
    relation_type: str
    source: str
    provenance: dict[str, str] = {}


class GraphSubgraphEvidence(TranslumeBaseModel):
    """Targeted graph slice for a decision-brief evidence task."""

    retrieval_mode: GraphRetrievalMode
    query_terms: list[str]
    node_ids: list[str]
    edge_ids: list[str]
    warnings: list[str] = []


class GraphEvidenceArtifact(TranslumeBaseModel):
    artifact_id: str
    source_entity_ids: list[str]
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    missing_entities: list[str] = []
    warnings: list[str] = []
    retrieval_modes: list[GraphRetrievalMode] = []
    subgraphs: list[GraphSubgraphEvidence] = []
