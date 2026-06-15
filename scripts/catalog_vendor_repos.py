#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "third_party" / "vendor_repos.json"
OUT = ROOT / "docs" / "third_party_catalog" / "project_tree_index.json"


def configured_repos() -> list[dict[str, str]]:
    payload = json.loads(CONFIG.read_text(encoding="utf-8"))
    return [dict(item) for item in payload["repositories"]]


def main() -> int:
    records = []
    for repo in configured_repos():
        repo_path = ROOT / repo["target"]
        if not repo_path.exists() or not any(repo_path.iterdir()):
            records.append({"repo": repo["name"], "missing": True, "paths": []})
            continue
        paths = [
            str(path.relative_to(repo_path))
            for path in repo_path.rglob("*")
            if path.is_file() and ".git" not in path.parts
        ]
        records.append({"repo": repo["name"], "missing": False, "paths": sorted(paths)})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"repos": records}, indent=2), encoding="utf-8")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
