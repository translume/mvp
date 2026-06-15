from __future__ import annotations

from translume_schemas.base import TranslumeBaseModel


class ToolRunArtifact(TranslumeBaseModel):
    artifact_id: str
    workflow: str
    input_entity_ids: list[str]
    summary: str
    evidence_items: list[dict[str, str]]
    warnings: list[str] = []
    requires_human_review: bool = True
