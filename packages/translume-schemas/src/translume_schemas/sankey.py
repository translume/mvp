from __future__ import annotations

from translume_schemas.base import TranslumeBaseModel


class SankeyNode(TranslumeBaseModel):
    node_id: str
    label: str
    kind: str
    evidence_class: str


class SankeyLink(TranslumeBaseModel):
    source_node_id: str
    target_node_id: str
    value: float
    claim_class: str
    validation_required: bool
    source_artifact_ids: list[str]


class MechanismSankeyOutput(TranslumeBaseModel):
    artifact_id: str
    nodes: list[SankeyNode]
    links: list[SankeyLink]
