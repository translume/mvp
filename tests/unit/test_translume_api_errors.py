from __future__ import annotations

from translume_api.main import _http_error_detail


class _BlankError(RuntimeError):
    def __str__(self) -> str:
        return ""


def test_http_error_detail_preserves_explicit_message() -> None:
    assert _http_error_detail(RuntimeError("named failure")) == "named failure"


def test_http_error_detail_uses_type_for_blank_message() -> None:
    assert _http_error_detail(_BlankError()) == "_BlankError: no error message"
