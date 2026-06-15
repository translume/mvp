from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from uuid import NAMESPACE_URL, uuid5

from translume_schemas.claims import ClaimEvidenceOutput
from translume_schemas.export import ReviewPacketExport
from translume_schemas.ledger import LedgerEvent
from translume_schemas.validation import ValidationDecision, ValidationStatus


class ClaimValidationError(ValueError):
    """Raised when a validation decision cannot be applied."""


def validation_cards_from_packet(packet: ReviewPacketExport) -> list[ClaimEvidenceOutput]:
    """Return claim cards available for human validation.

    Acceptance criteria:
        1. Returns exactly the claim cards in the packet bundle.
        2. Preserves claim order.
        3. Performs no I/O.
        4. Does not mutate the packet.

    Args:
        packet: Review packet containing claim evidence cards.

    Returns:
        Claim evidence cards that can be reviewed by a human.
    """
    return list(packet.bundle.claims)


def build_validation_decision(
    *,
    claim_id: str,
    status: ValidationStatus,
    created_at: datetime,
    reviewer_id: str | None = None,
    reviewer_note: str | None = None,
    decision_id: str | None = None,
) -> ValidationDecision:
    """Build a human validation decision for one claim.

    Acceptance criteria:
        1. Empty claim IDs raise `ClaimValidationError`.
        2. Status is constrained by `ValidationStatus` schema validation.
        3. Blank reviewer IDs and notes are normalized to `None`.
        4. Decision IDs are stable for the same claim/status/reviewer/timestamp
           unless an explicit decision ID is supplied.
        5. Performs no I/O and does not mutate caller-owned values.

    Args:
        claim_id: Claim being reviewed.
        status: Review status selected by the human reviewer.
        created_at: Explicit decision timestamp.
        reviewer_id: Optional reviewer identifier.
        reviewer_note: Optional reviewer note.
        decision_id: Optional externally supplied decision identifier.

    Returns:
        Validation decision model.

    Raises:
        ClaimValidationError: If `claim_id` is empty.
    """
    normalized_claim_id = claim_id.strip()
    if not normalized_claim_id:
        raise ClaimValidationError("claim_id is required")
    normalized_reviewer_id = _none_if_blank(reviewer_id)
    normalized_note = _none_if_blank(reviewer_note)
    stable_decision_id = decision_id or _stable_id(
        "decision",
        (
            normalized_claim_id,
            status,
            normalized_reviewer_id or "",
            created_at.isoformat(),
        ),
    )
    return ValidationDecision(
        decision_id=stable_decision_id,
        claim_id=normalized_claim_id,
        status=status,
        reviewer_id=normalized_reviewer_id,
        reviewer_note=normalized_note,
        created_at=created_at,
    )


def apply_validation_decision_to_packet(
    packet: ReviewPacketExport,
    decision: ValidationDecision,
    *,
    created_at: datetime,
) -> ReviewPacketExport:
    """Return a new packet with one validation decision applied.

    Acceptance criteria:
        1. `decision.claim_id` must exist in packet claims.
        2. Matching claim `validation_status` is updated to the decision status.
        3. Validation decision is appended to bundle validation decisions.
        4. A claim-validation ledger event is appended.
        5. Original packet and original claim objects are not mutated.
        6. Updated packet remains JSON-serializable.

    Args:
        packet: Existing review packet.
        decision: Human validation decision to apply.
        created_at: Explicit ledger event timestamp.

    Returns:
        Updated review packet.

    Raises:
        ClaimValidationError: If the target claim does not exist.
    """
    _require_claim(packet.bundle.claims, decision.claim_id)
    updated_claims = [
        claim.model_copy(update={"validation_status": decision.status})
        if claim.claim_id == decision.claim_id
        else claim
        for claim in packet.bundle.claims
    ]
    event = claim_validation_ledger_event(packet, decision, created_at=created_at)
    updated_bundle = packet.bundle.model_copy(
        update={
            "claims": updated_claims,
            "validation_decisions": [
                *packet.bundle.validation_decisions,
                decision,
            ],
            "ledger_events": [*packet.bundle.ledger_events, event],
        }
    )
    return packet.model_copy(update={"bundle": updated_bundle})


def claim_validation_ledger_event(
    packet: ReviewPacketExport,
    decision: ValidationDecision,
    *,
    created_at: datetime,
) -> LedgerEvent:
    """Create a ledger event for a claim validation decision.

    Acceptance criteria:
        1. Event references case ID, session ID, source file ID, claim ID, and
           decision ID.
        2. Event type is specific to claim validation.
        3. Event is deterministic for the same packet, decision, and timestamp.
        4. Performs no database or filesystem I/O.

    Args:
        packet: Review packet being updated.
        decision: Human validation decision being recorded.
        created_at: Explicit event timestamp.

    Returns:
        Ledger event for the validation decision.
    """
    return LedgerEvent(
        event_id=_stable_id(
            "event",
            (
                packet.case_id,
                packet.session_id,
                packet.source_file_id,
                decision.decision_id,
                created_at.isoformat(),
            ),
        ),
        event_type="claim_validation_decision_recorded",
        case_id=packet.case_id,
        session_id=packet.session_id,
        artifact_id=decision.claim_id,
        source_file_id=packet.source_file_id,
        created_at=created_at,
        details={
            "claim_id": decision.claim_id,
            "decision_id": decision.decision_id,
            "status": decision.status,
            "reviewer_id": decision.reviewer_id or "",
        },
    )


def _require_claim(
    claims: Sequence[ClaimEvidenceOutput],
    claim_id: str,
) -> ClaimEvidenceOutput:
    for claim in claims:
        if claim.claim_id == claim_id:
            return claim
    raise ClaimValidationError(f"claim_id not found: {claim_id}")


def _stable_id(prefix: str, parts: Sequence[str]) -> str:
    seed = ":".join(parts)
    return f"{prefix}_{uuid5(NAMESPACE_URL, seed).hex}"


def _none_if_blank(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None
