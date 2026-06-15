from __future__ import annotations

from datetime import datetime
from pathlib import Path

from translume_schemas.base import TranslumeBaseModel


class CaseSession(TranslumeBaseModel):
    case_id: str
    session_id: str
    report_type: str
    safety_mode: str
    created_at: datetime


class StoredFile(TranslumeBaseModel):
    case_id: str
    session_id: str
    source_file_id: str
    filename: str
    path: Path
    size_bytes: int
    sha256: str
