from __future__ import annotations

from translume_schemas.base import TranslumeBaseModel


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


class GraphEvidenceArtifact(TranslumeBaseModel):
    artifact_id: str
    source_entity_ids: list[str]
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    missing_entities: list[str] = []
    warnings: list[str] = []
