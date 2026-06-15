from __future__ import annotations

from datetime import datetime
from typing import Literal

from translume_schemas.base import TranslumeBaseModel


ValidationStatus = Literal["validated", "rejected", "needs_review"]


class ValidationDecision(TranslumeBaseModel):
    """Human review decision for one evidence claim.

    Attributes:
        decision_id: Stable decision identifier.
        claim_id: Claim being reviewed.
        status: Review status selected by the reviewer.
        reviewer_id: Optional reviewer identifier supplied by the UI/API.
        reviewer_note: Optional human note explaining the decision.
        created_at: Decision timestamp supplied by the boundary layer.
    """

    decision_id: str
    claim_id: str
    status: ValidationStatus
    reviewer_id: str | None = None
    reviewer_note: str | None = None
    created_at: datetime
