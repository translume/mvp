from __future__ import annotations

from translume_schemas.base import TranslumeBaseModel


class ClaimEvidenceOutput(TranslumeBaseModel):
    claim_id: str
    claim: str
    claim_class: str
    source_artifact_ids: list[str]
    evidence_source: str
    relevance: str
    limitations: str
    validation_status: str = "needs_review"
