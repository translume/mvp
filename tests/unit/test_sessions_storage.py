from __future__ import annotations

from datetime import datetime, timezone

import pytest

from translume_core.ingestion.sessions import create_case_session


def test_create_case_session_with_explicit_ids_is_deterministic() -> None:
    created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    session = create_case_session(
        "ngs",
        "research_support_only",
        created_at,
        case_id="case_a",
        session_id="session_a",
    )
    assert session.case_id == "case_a"
    assert session.session_id == "session_a"
    assert session.report_type == "NGS"


def test_create_case_session_rejects_unknown_report_type() -> None:
    with pytest.raises(ValueError, match="unsupported report_type"):
        create_case_session("unknown", "research_support_only", datetime.now(timezone.utc))
