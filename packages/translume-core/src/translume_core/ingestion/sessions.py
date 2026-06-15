from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from translume_schemas.session import CaseSession

_ALLOWED_REPORT_TYPES = {"NGS", "WGS", "FISH", "IHC", "RESEARCH_PDF", "XT", "XR", "RNA"}
_ALLOWED_SAFETY_MODES = {"research_support_only"}


def create_case_session(
    report_type: str,
    safety_mode: str,
    created_at: datetime,
    *,
    case_id: str | None = None,
    session_id: str | None = None,
) -> CaseSession:
    """Create an immutable case session before clinical interpretation.

    Acceptance criteria:
        1. Determinism: Explicit IDs and timestamp produce the same object.
        2. Validation: Unsupported report type raises `ValueError`.
        3. Safety: Unsupported safety mode raises `ValueError`.
        4. Traceability: Output includes case_id and session_id.
        5. No mutation: Does not mutate caller-owned values.

    Args:
        report_type: Report type selected by the user.
        safety_mode: Safety mode for the session.
        created_at: Creation timestamp from boundary layer.
        case_id: Optional externally supplied case ID.
        session_id: Optional externally supplied session ID.

    Returns:
        New `CaseSession`.

    Raises:
        ValueError: If report type or safety mode is unsupported.
    """
    normalized_type = report_type.strip().upper().replace(" ", "_")
    if normalized_type not in _ALLOWED_REPORT_TYPES:
        raise ValueError(f"unsupported report_type: {report_type!r}")
    if safety_mode not in _ALLOWED_SAFETY_MODES:
        raise ValueError(f"unsupported safety_mode: {safety_mode!r}")
    return CaseSession(
        case_id=case_id or f"case_{uuid4().hex}",
        session_id=session_id or f"session_{uuid4().hex}",
        report_type=normalized_type,
        safety_mode=safety_mode,
        created_at=created_at,
    )
