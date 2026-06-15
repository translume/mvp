from __future__ import annotations

from datetime import datetime

from translume_schemas.base import TranslumeBaseModel


class ArtifactProvenance(TranslumeBaseModel):
    artifact_id: str
    artifact_type: str
    schema_name: str
    model_name: str | None = None
    prompt_hash: str | None = None
    schema_hash: str | None = None
    source_file_id: str | None = None
    source_artifact_ids: list[str]
    created_at: datetime
    validation_status: str = "needs_review"
