from __future__ import annotations

from translume_schemas.base import TranslumeBaseModel


class NormalizedEntity(TranslumeBaseModel):
    entity_id: str
    entity_type: str
    original_text: str
    normalized_label: str
    source_finding_id: str | None = None
    source_artifact_id: str
    needs_human_review: bool = False


class NormalizedEntitySet(TranslumeBaseModel):
    artifact_id: str
    case_id: str
    session_id: str
    entities: list[NormalizedEntity]
