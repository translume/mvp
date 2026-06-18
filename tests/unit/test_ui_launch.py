from __future__ import annotations

from pathlib import Path

import pytest

from translume_ui.app import (
    DEFAULT_API_BASE_URL,
    TranslumeUIConfigError,
    api_base_url_from_environment,
    ui_server_config_from_environment,
)


ROOT = Path(__file__).resolve().parents[2]


def test_api_base_url_uses_docker_api_port_by_default() -> None:
    """The UI should target the real API service port by default."""
    assert api_base_url_from_environment({}) == DEFAULT_API_BASE_URL
    assert DEFAULT_API_BASE_URL == "http://translume-api:8080"


def test_api_base_url_validation_rejects_empty_and_non_http_values() -> None:
    """Invalid API URLs must fail before Gradio launches."""
    with pytest.raises(TranslumeUIConfigError):
        api_base_url_from_environment({"TRANSLUME_API_BASE_URL": ""})
    with pytest.raises(TranslumeUIConfigError):
        api_base_url_from_environment({"TRANSLUME_API_BASE_URL": "translume-api"})


def test_ui_server_config_uses_docker_safe_defaults() -> None:
    """Gradio should bind all interfaces on port 7860 by default."""
    config = ui_server_config_from_environment({})
    assert config.host == "0.0.0.0"
    assert config.port == 7860


def test_ui_server_config_validation() -> None:
    """Invalid Gradio host or port should fail explicitly."""
    with pytest.raises(TranslumeUIConfigError):
        ui_server_config_from_environment({"TRANSLUME_UI_HOST": ""})
    with pytest.raises(TranslumeUIConfigError):
        ui_server_config_from_environment({"TRANSLUME_UI_PORT": "not-an-int"})
    with pytest.raises(TranslumeUIConfigError):
        ui_server_config_from_environment({"TRANSLUME_UI_PORT": "0"})


def test_ui_dockerfile_runs_gradio_module_directly() -> None:
    """UI Dockerfile must not try to run Gradio as an ASGI app."""
    dockerfile = (ROOT / "docker" / "ui.Dockerfile").read_text(encoding="utf-8")
    assert 'CMD ["python", "-m", "translume_ui.app"]' in dockerfile
    assert "uvicorn translume_ui.app:app" not in dockerfile


def test_compose_sets_internal_api_url_and_ui_healthcheck() -> None:
    """Docker Compose should wire Gradio to FastAPI inside the network."""
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "TRANSLUME_API_BASE_URL=http://translume-api:8080" in compose
    assert "http://localhost:7860" in compose
    assert "condition: service_healthy" in compose
