#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
import subprocess
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "third_party" / "vendor_repos.json"
MANIFEST_DIR = ROOT / "third_party" / "manifests"


@dataclass(frozen=True)
class VendorRepo:
    name: str
    url: str
    target: Path


def load_vendor_repos(path: Path) -> list[VendorRepo]:
    """Load vendor repo specs from JSON.

    Acceptance criteria:
        1. Missing config raises FileNotFoundError.
        2. Every repository has name, url, and target.
        3. Target paths are resolved under the project root.
    """
    payload = json.loads(path.read_text(encoding="utf-8"))
    repos = payload.get("repositories")
    if not isinstance(repos, list):
        raise ValueError("vendor_repos.json missing repositories list")
    return [
        VendorRepo(
            name=str(item["name"]),
            url=str(item["url"]),
            target=ROOT / str(item["target"]),
        )
        for item in repos
    ]


def ensure_repo(repo: VendorRepo) -> dict[str, Any]:
    """Clone or pull a vendor repository.

    Acceptance criteria:
        1. Existing git repositories are updated with `git pull --ff-only`.
        2. Missing repositories are cloned from configured URL.
        3. Non-git non-empty targets raise RuntimeError.
        4. Returns commit metadata after update.
    """
    repo.target.parent.mkdir(parents=True, exist_ok=True)
    if repo.target.exists() and (repo.target / ".git").exists():
        subprocess.run(["git", "-C", str(repo.target), "pull", "--ff-only"], check=True)
    elif repo.target.exists() and any(repo.target.iterdir()):
        raise RuntimeError(f"target exists but is not a git repository: {repo.target}")
    else:
        if repo.target.exists():
            repo.target.rmdir()
        subprocess.run(["git", "clone", repo.url, str(repo.target)], check=True)
    commit = subprocess.check_output(
        ["git", "-C", str(repo.target), "rev-parse", "HEAD"],
        text=True,
    ).strip()
    return {"name": repo.name, "url": repo.url, "target": str(repo.target), "commit": commit}


def install_repo_from_zip(repo: VendorRepo, zip_path: Path) -> dict[str, Any]:
    """Install a vendor repository from a user-provided zip archive.

    Acceptance criteria:
        1. Existing target directory is replaced only for the selected repo.
        2. Archive content is copied as-is except for stripping one root folder.
        3. Result records source zip and file count.
    """
    if not zip_path.exists():
        raise FileNotFoundError(str(zip_path))
    if repo.target.exists():
        shutil.rmtree(repo.target)
    repo.target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as archive:
        names = [name for name in archive.namelist() if not name.endswith("/")]
        common_root = _common_archive_root(names)
        for name in names:
            output_name = name[len(common_root):].lstrip("/") if common_root else name
            if not output_name:
                continue
            destination = repo.target / output_name
            destination.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(name) as source, destination.open("wb") as target:
                shutil.copyfileobj(source, target)
    return {
        "name": repo.name,
        "target": str(repo.target),
        "source_zip": str(zip_path),
        "file_count": len(list(repo.target.rglob("*"))),
    }


def _common_archive_root(names: list[str]) -> str:
    roots = {name.split("/", 1)[0] for name in names if "/" in name}
    return next(iter(roots)) if len(roots) == 1 else ""


def write_manifest(record: dict[str, Any]) -> None:
    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    path = MANIFEST_DIR / f"{record['name'].casefold()}.lock.json"
    path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(f"wrote {path}")


def main() -> int:
    repos = load_vendor_repos(CONFIG)
    zip_root = ROOT / "third_party" / "zips"
    for repo in repos:
        zip_path = zip_root / f"{repo.name}.zip"
        if zip_path.exists():
            record = install_repo_from_zip(repo, zip_path)
        else:
            record = ensure_repo(repo)
        write_manifest(record)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
