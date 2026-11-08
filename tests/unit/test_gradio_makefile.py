"""Validate the CPU-only Compose contract without claiming a Docker run."""

from pathlib import Path
import tomllib

import yaml


ROOT = Path(__file__).resolve().parents[2]


def _services():
    return yaml.safe_load((ROOT / "docker-compose.yml").read_text())["services"]


def test_default_compose_includes_complete_report_workflow():
    services = _services()
    for name in ("translume-ui", "translume-api", "precision-oncology-pipeline", "dynamic-pathway-analyzer"):
        assert name in services
        assert not services[name].get("profiles")
    assert services["translume-api"]["depends_on"]["data-init"]["condition"] == "service_completed_successfully"
    assert "docker compose up --build -d" in (ROOT / "Makefile").read_text()


def test_credentials_reach_only_inference_services():
    services = _services()
    inference = {"translume-api", "docling-service", "medea-service", "precision-oncology-pipeline", "dynamic-pathway-analyzer", "verify"}
    for name, service in services.items():
        environment = service.get("environment", {})
        if name in inference:
            assert "${OPENAI_API_KEY:?" in environment["OPENAI_API_KEY"]
            assert environment["OPENAI_BASE_URL"] == "https://api.openai.com/v1"
            assert environment["OPENAI_REASONING_MODE"] == "pro"
        else:
            assert "OPENAI_API_KEY" not in environment
        assert "env_file" not in service


def test_compose_and_dependencies_cannot_start_local_inference():
    services = _services()
    for name, service in services.items():
        assert not name.startswith("vllm")
        assert "gpus" not in service
        assert "runtime" not in service
    packages = {package["name"] for package in tomllib.loads((ROOT / "uv.lock").read_text())["package"]}
    banned = {"torch", "transformers", "sentence-transformers", "flagembedding", "docling", "ollama", "vllm"}
    assert packages.isdisjoint(banned)
    assert not any(name.startswith(("nvidia-", "cuda-")) for name in packages)


def test_only_the_browser_ui_and_api_are_exposed_to_loopback():
    services = _services()
    for name, service in services.items():
        for port in service.get("ports", []):
            assert name in {"translume-ui", "translume-api"}
            assert port.startswith("127.0.0.1:")
