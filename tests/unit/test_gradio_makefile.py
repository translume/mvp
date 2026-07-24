"""Tests for the root Gradio Docker Compose workflow."""

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_gradio_targets_start_downstream_runner_services() -> None:
    """The Gradio targets should start UI, API, and both runners.

    Acceptance criteria:
        1. Determinism: The target definitions are checked as static text.
        2. Coverage: Both startup and rebuild targets name all services.
        3. Scope: No Docker daemon is required for this unit test.
    """
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    required_services = (
        "precision-oncology-pipeline",
        "dynamic-pathway-analyzer",
        "translume-api",
        "translume-ui",
    )

    for target_name in ("gradio-up", "gradio-rebuild"):
        target_start = makefile.index(f"{target_name}:")
        target_end = makefile.find("\n\n", target_start)
        target_body = makefile[target_start:target_end]

        for service_name in required_services:
            assert service_name in target_body


def test_compose_scopes_remote_key_to_downstream_runners() -> None:
    """The API should not receive the downstream remote-provider credential.

    Acceptance criteria:
        1. Service safety: Non-runner services override remote key values.
        2. Runner wiring: Both downstream runners receive the dedicated key.
        3. Scope: The test validates Compose source without a Docker daemon.
    """
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    precision_start = compose.index("\n  precision-oncology-pipeline:")
    dynamic_start = compose.index("\n  dynamic-pathway-analyzer:")
    precision_section = compose[precision_start:dynamic_start]
    dynamic_section = compose[dynamic_start:]

    non_runner_services = (
        "docling-service",
        "optimuskg-service",
        "tooluniverse-service",
        "medea-service",
        "translume-api",
        "translume-ui",
        "translume-worker",
    )
    for service_name in non_runner_services:
        marker = f"\n  {service_name}:"
        service_start = compose.index(marker)
        following_services = re.search(
            r"\n  [a-z][a-z0-9-]*:",
            compose[service_start + 1:],
        )
        service_end = (
            service_start + 1 + following_services.start()
            if following_services is not None
            else len(compose)
        )
        service_section = compose[service_start:service_end]

        assert 'OPENAI_API_KEY: ""' in service_section
        assert 'DOWNSTREAM_OPENAI_API_KEY: ""' in service_section

    assert "OPENAI_API_KEY: ${DOWNSTREAM_OPENAI_API_KEY:-}" in precision_section
    assert "OPENAI_API_KEY: ${DOWNSTREAM_OPENAI_API_KEY:-}" in dynamic_section
