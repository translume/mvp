from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from translume_core.vendor.repositories import (
    VendorRepoSpec,
    VendorRepositoryError,
    bootstrap_vendor_repo_from_zip,
    inspect_vendor_repo,
    inspect_vendor_repos,
    load_vendor_repo_specs,
    normalize_git_url,
    require_updateable_vendor_repos,
    vendor_status_to_dict,
)
from scripts.full_stack_preflight import PreflightError, validate_vendor_repositories


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


def test_load_vendor_repo_specs_rejects_targets_outside_root(tmp_path: Path) -> None:
    config = tmp_path / "vendor.json"
    config.write_text(
        json.dumps(
            {
                "repositories": [
                    {
                        "name": "Bad",
                        "url": "https://example.test/bad.git",
                        "target": "../bad",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(VendorRepositoryError):
        load_vendor_repo_specs(config, tmp_path)


def test_inspect_vendor_repo_fails_zip_extracted_directory(tmp_path: Path) -> None:
    target = tmp_path / "third_party" / "upstream" / "Medea"
    target.mkdir(parents=True)
    (target / "README.md").write_text("zip extracted", encoding="utf-8")
    spec = VendorRepoSpec(
        name="Medea",
        url="https://github.com/mims-harvard/Medea.git",
        target=target,
    )
    state = inspect_vendor_repo(spec)
    assert state.exists is True
    assert state.is_git_repository is False
    assert state.updateable is False
    assert "target exists but is not a Git repository" in state.problems
    with pytest.raises(VendorRepositoryError):
        require_updateable_vendor_repos((spec,))


@pytest.mark.skipif(not _git_available(), reason="git is required for this test")
def test_inspect_vendor_repo_accepts_clean_git_clone(tmp_path: Path) -> None:
    remote = "https://github.com/mims-harvard/Medea.git"
    target = tmp_path / "third_party" / "upstream" / "Medea"
    _init_git_repo(target, remote)
    spec = VendorRepoSpec(name="Medea", url=remote, target=target)
    state = inspect_vendor_repo(spec)
    assert state.is_git_repository is True
    assert state.updateable is True
    assert state.commit is not None
    assert state.branch is not None


@pytest.mark.skipif(not _git_available(), reason="git is required for this test")
def test_inspect_vendor_repo_detects_dirty_tree(tmp_path: Path) -> None:
    remote = "https://github.com/mims-harvard/ToolUniverse.git"
    target = tmp_path / "third_party" / "upstream" / "ToolUniverse"
    _init_git_repo(target, remote)
    (target / "dirty.txt").write_text("untracked", encoding="utf-8")
    spec = VendorRepoSpec(name="ToolUniverse", url=remote, target=target)
    state = inspect_vendor_repo(spec)
    assert state.updateable is False
    assert "working tree has uncommitted or untracked changes" in state.problems


def test_vendor_status_to_dict_is_json_serializable(tmp_path: Path) -> None:
    spec = VendorRepoSpec(
        name="OptimusKG",
        url="https://github.com/mims-harvard/OptimusKG.git",
        target=tmp_path / "missing",
    )
    report = inspect_vendor_repos((spec,))
    payload = vendor_status_to_dict(report)
    assert payload["ok"] is False
    json.dumps(payload)


def test_zip_bootstrap_does_not_satisfy_vendor_status(tmp_path: Path) -> None:
    import zipfile

    zip_path = tmp_path / "Medea.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("Medea-main/README.md", "offline")
    spec = VendorRepoSpec(
        name="Medea",
        url="https://github.com/mims-harvard/Medea.git",
        target=tmp_path / "third_party" / "upstream" / "Medea",
    )
    state = bootstrap_vendor_repo_from_zip(spec, zip_path, force=False)
    assert state.exists is True
    assert state.is_git_repository is False
    assert state.updateable is False


def test_preflight_vendor_validation_requires_git_clones(tmp_path: Path) -> None:
    config = tmp_path / "third_party" / "vendor_repos.json"
    config.parent.mkdir(parents=True)
    config.write_text(
        json.dumps(
            {
                "repositories": [
                    {
                        "name": "Medea",
                        "url": "https://github.com/mims-harvard/Medea.git",
                        "target": "third_party/upstream/Medea",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "third_party" / "upstream" / "Medea").mkdir(parents=True)
    with pytest.raises(PreflightError):
        validate_vendor_repositories(tmp_path)


def test_normalize_git_url_handles_https_and_ssh() -> None:
    assert normalize_git_url("https://github.com/mims-harvard/Medea.git") == (
        "https://github.com/mims-harvard/medea"
    )
    assert normalize_git_url("git@github.com:mims-harvard/Medea.git") == (
        "https://github.com/mims-harvard/medea"
    )
