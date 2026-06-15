from __future__ import annotations

from datetime import datetime

from translume_schemas.base import TranslumeBaseModel


class LedgerEvent(TranslumeBaseModel):
    event_id: str
    event_type: str
    case_id: str
    session_id: str
    artifact_id: str | None = None
    source_file_id: str | None = None
    created_at: datetime
    details: dict[str, str] = {}
