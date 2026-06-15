from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from translume_schemas.ledger import LedgerEvent


def persistence_ledger_event(
    *,
    event_type: str,
    case_id: str,
    session_id: str,
    source_file_id: str,
    created_at: datetime,
    counts_by_target: dict[str, int],
) -> LedgerEvent:
    """Create a ledger event for durable persistence work.

    Acceptance criteria:
        1. Event references case/session/source file.
        2. Counts are converted to string details for schema compatibility.
        3. Function performs no I/O.
        4. Function does not mutate caller-owned mappings.
    """
    return LedgerEvent(
        event_id=f"event_{uuid4().hex}",
        event_type=event_type,
        case_id=case_id,
        session_id=session_id,
        source_file_id=source_file_id,
        created_at=created_at,
        details={key: str(value) for key, value in counts_by_target.items()},
    )
