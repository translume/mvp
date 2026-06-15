from __future__ import annotations

from translume_schemas.base import TranslumeBaseModel


class MedeaReasoningArtifact(TranslumeBaseModel):
    artifact_id: str
    reasoning_mode: str
    summary: str
    supported_hypotheses: list[str]
    weakened_hypotheses: list[str]
    warnings: list[str] = []
    requires_human_review: bool = True
