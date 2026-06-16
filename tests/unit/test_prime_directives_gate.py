from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from translume_core.prime_directives import (
    PrimeDirectiveViolation,
    assert_prime_directives,
    merge_environment_file,
    prime_directives_report_to_dict,
    render_prime_directives_report,
    should_enforce_prime_directives,
    validate_prime_directives,
)


ROOT = Path(__file__).resolve().parents[2]


REQUIRED_ENV = {
    "TRANSLUME_ENV": "production",
    "TRANSLUME_REQUIRE_MIMS": "true",
    "TRANSLUME_REQUIRE_DOCLING": "true",
    "TRANSLUME_REQUIRE_OPENSEARCH": "true",
    "TRANSLUME_REQUIRE_POSTGRES": "true",
    "BLOCK_REMOTE_MODEL_PROVIDERS": "true",
    "VLLM_BASE_URL": "http://vllm-clinical:8000/v1",
    "VLLM_MODEL": "real/model-id",
    "DOCLING_SERVICE_URL": "http://docling-service:8090",
    "OPTIMUSKG_SERVICE_URL": "http://optimuskg-service:8091",
    "TOOLUNIVERSE_SERVICE_URL": "http://tooluniverse-service:8092",
    "MEDEA_SERVICE_URL": "http://medea-service:8093",
    "OPENSEARCH_URL": "http://opensearch:9200",
    "POSTGRES_DSN": "postgresql://translume:translume@postgres:5432/translume",
    "TRANSLUME_TOOL_WORKFLOWS": "target_context",
}


def _git_available() -> bool:
    try:
        subprocess.run(["git", "--version"], check=True, capture_output=True)
        return True
    except (OSError, subprocess.CalledProcessError):
        return False


def _init_git_repo(path: Path, remote: str) -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=path, check=True)
    (path / "README.md").write_text("vendor", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "remote", "add", "origin", remote], cwd=path, check=True)


def _write_vendor_config(root: Path) -> None:
    config = root / "third_party" / "vendor_repos.json"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(
        json.dumps(
            {
                "repositories": [
                    {
                        "name": "Medea",
                        "url": "https://github.com/mims-harvard/Medea.git",
                        "target": "third_party/upstream/Medea",
                    },
                    {
                        "name": "OptimusKG",
                        "url": "https://github.com/mims-harvard/OptimusKG.git",
                        "target": "third_party/upstream/OptimusKG",
                    },
                    {
                        "name": "ToolUniverse",
                        "url": "https://github.com/mims-harvard/ToolUniverse.git",
                        "target": "third_party/upstream/ToolUniverse",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )


def _write_ui_dockerfile(root: Path, content: str | None = None) -> None:
    docker = root / "docker"
    docker.mkdir(parents=True, exist_ok=True)
    (docker / "ui.Dockerfile").write_text(
        content or 'FROM python:3.12\nCMD ["python", "-m", "translume_ui.app"]\n',
        encoding="utf-8",
    )


def _prepare_root(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
    (root / "pyproject.toml").write_text("[project]\nname='x'\nversion='0'\n", encoding="utf-8")
    _write_vendor_config(root)
    _write_ui_dockerfile(root)
    return root


def _prepare_git_vendors(root: Path) -> None:
    remotes = {
        "Medea": "https://github.com/mims-harvard/Medea.git",
        "OptimusKG": "https://github.com/mims-harvard/OptimusKG.git",
        "ToolUniverse": "https://github.com/mims-harvard/ToolUniverse.git",
    }
    for name, remote in remotes.items():
        _init_git_repo(root / "third_party" / "upstream" / name, remote)


def test_gate_is_inactive_for_local_mode_without_force(tmp_path: Path) -> None:
    root = _prepare_root(tmp_path)
    report = validate_prime_directives(environment={"TRANSLUME_ENV": "local"}, root=root)
    assert report.ok is True
    assert report.active is False


def test_gate_activates_for_production_mode(tmp_path: Path) -> None:
    root = _prepare_root(tmp_path)
    assert should_enforce_prime_directives({"TRANSLUME_ENV": "production"}) is True
    report = validate_prime_directives(environment={"TRANSLUME_ENV": "production"}, root=root)
    assert report.ok is False
    assert report.active is True
    assert any(f.rule_id.startswith("required_true:") for f in report.findings)


@pytest.mark.skipif(not _git_available(), reason="git is required for this test")
def test_gate_passes_with_real_git_vendors_and_required_config(tmp_path: Path) -> None:
    root = _prepare_root(tmp_path)
    _prepare_git_vendors(root)
    report = validate_prime_directives(environment=REQUIRED_ENV, root=root, force=True)
    assert report.ok is True
    payload = prime_directives_report_to_dict(report)
    assert payload["ok"] is True
    assert "PRIME_DIRECTIVES gate: OK" in render_prime_directives_report(report)


def test_gate_fails_zip_extracted_vendors(tmp_path: Path) -> None:
    root = _prepare_root(tmp_path)
    for name in ("Medea", "OptimusKG", "ToolUniverse"):
        target = root / "third_party" / "upstream" / name
        target.mkdir(parents=True)
        (target / "README.md").write_text("zip", encoding="utf-8")
    report = validate_prime_directives(environment=REQUIRED_ENV, root=root, force=True)
    assert report.ok is False
    assert any(f.rule_id == "mims_vendors:updateable_git_clones" for f in report.findings)


@pytest.mark.skipif(not _git_available(), reason="git is required for this test")
def test_gate_blocks_remote_provider_credentials(tmp_path: Path) -> None:
    root = _prepare_root(tmp_path)
    _prepare_git_vendors(root)
    environment = {**REQUIRED_ENV, "OPENAI_API_KEY": "real-secret"}
    report = validate_prime_directives(environment=environment, root=root, force=True)
    assert report.ok is False
    assert any(f.rule_id == "remote_provider_blocked:OPENAI_API_KEY" for f in report.findings)


@pytest.mark.skipif(not _git_available(), reason="git is required for this test")
def test_gate_rejects_bad_ui_dockerfile(tmp_path: Path) -> None:
    root = _prepare_root(tmp_path)
    _prepare_git_vendors(root)
    _write_ui_dockerfile(root, "FROM python:3.12\nCMD uvicorn translume_ui.app:app\n")
    report = validate_prime_directives(environment=REQUIRED_ENV, root=root, force=True)
    assert report.ok is False
    assert any(f.rule_id == "ui_dockerfile:no_uvicorn_asgi_shim" for f in report.findings)


def test_assert_prime_directives_raises_with_rendered_report(tmp_path: Path) -> None:
    root = _prepare_root(tmp_path)
    with pytest.raises(PrimeDirectiveViolation) as error_info:
        assert_prime_directives(
            environment={"TRANSLUME_ENV": "production"},
            root=root,
        )
    assert "PRIME_DIRECTIVES gate: FAILED" in str(error_info.value)


def test_merge_environment_file_prefers_process_environment(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("A=file\nB=file\n", encoding="utf-8")
    merged = merge_environment_file(env_file=env_file, process_environment={"B": "process"})
    assert merged["A"] == "file"
    assert merged["B"] == "process"
