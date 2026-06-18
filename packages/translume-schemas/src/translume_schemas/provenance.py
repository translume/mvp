from __future__ import annotations

from datetime import datetime

from pydantic import Field

from translume_schemas.base import TranslumeBaseModel


class ArtifactProvenance(TranslumeBaseModel):
    """Audit metadata for a generated or externally-derived artifact."""

    artifact_id: str
    artifact_type: str
    schema_name: str
    model_name: str | None = None
    prompt_hash: str | None = None
    schema_hash: str | None = None
    source_file_id: str | None = None
    source_chunk_ids: list[str] = Field(default_factory=list)
    source_artifact_ids: list[str]
    created_at: datetime
    validation_status: str = "needs_review"
    generation_status: str = "generated"
