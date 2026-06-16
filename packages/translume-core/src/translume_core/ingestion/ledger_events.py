from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from translume_schemas.ledger import LedgerEvent
from translume_schemas.session import CaseSession, StoredFile


def record_upload_ledger_event(
    session: CaseSession,
    stored_file: StoredFile,
    created_at: datetime,
) -> LedgerEvent:
    """Create a ledger event for a report upload.

    Acceptance criteria:
        1. Event references case_id, session_id, and source_file_id.
        2. Event is deterministic aside from generated event_id.
        3. Event is serializable to JSON.
        4. Function does not write to Postgres.

    Args:
        session: Active case session.
        stored_file: Stored uploaded file metadata.
        created_at: Event timestamp.

    Returns:
        Upload ledger event.
    """
    return LedgerEvent(
        event_id=f"event_{uuid4().hex}",
        event_type="report_uploaded",
        case_id=session.case_id,
        session_id=session.session_id,
        source_file_id=stored_file.source_file_id,
        created_at=created_at,
        details={
            "filename": stored_file.filename,
            "sha256": stored_file.sha256,
            "size_bytes": str(stored_file.size_bytes),
            "storage_path": str(stored_file.path),
        },
    )
