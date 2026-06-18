from __future__ import annotations

import pytest

from scripts.check_ui_health import (
    UIHealthCheckError,
    UIHealthResponse,
    ui_url_from_environment,
    validate_ui_health_response,
)


def test_ui_url_from_environment_defaults_and_validates() -> None:
    """UI health check should use the real local Gradio URL by default."""
    assert ui_url_from_environment({}) == "http://localhost:7860"
    assert ui_url_from_environment({"TRANSLUME_UI_URL": "http://host:7860/"}) == (
        "http://host:7860"
    )
    with pytest.raises(UIHealthCheckError):
        ui_url_from_environment({"TRANSLUME_UI_URL": ""})


def test_validate_ui_health_response_accepts_real_html_response() -> None:
    """Health validation should accept a non-empty HTTP 2xx HTML response."""
    validate_ui_health_response(
        UIHealthResponse(
            status_code=200,
            content_type="text/html; charset=utf-8",
            body="<html>Translume</html>",
        )
    )


def test_validate_ui_health_response_rejects_bad_responses() -> None:
    """Health validation should fail for bad or empty UI responses."""
    with pytest.raises(UIHealthCheckError):
        validate_ui_health_response(
            UIHealthResponse(status_code=500, content_type="text/html", body="error")
        )
    with pytest.raises(UIHealthCheckError):
        validate_ui_health_response(
            UIHealthResponse(status_code=200, content_type="text/html", body="")
        )
    with pytest.raises(UIHealthCheckError):
        validate_ui_health_response(
            UIHealthResponse(
                status_code=200,
                content_type="application/json",
                body='{"status":"ok"}',
            )
        )
