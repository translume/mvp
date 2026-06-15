#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

PATTERNS = [
    "OPENAI_API_KEY",
    "OPENROUTER_API_KEY",
    "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "AZURE_OPENAI",
    "NVIDIA_API_KEY",
    "api_key",
    "base_url",
    "openai",
    "openrouter",
    "anthropic",
    "gemini",
    "requests.post",
    "httpx.post",
]
ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "third_party" / "vendor_repos.json"
OUT = ROOT / "docs" / "third_party_catalog" / "model_api_call_audit.json"


def configured_repos() -> list[dict[str, str]]:
    payload = json.loads(CONFIG.read_text(encoding="utf-8"))
    return [dict(item) for item in payload["repositories"]]


def scan_file(path: Path, repo: str) -> list[dict[str, object]]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    findings = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        for pattern in PATTERNS:
            if pattern.casefold() in line.casefold():
                findings.append(
                    {
                        "repo": repo,
                        "file": str(path.relative_to(ROOT)),
                        "line": line_no,
                        "pattern": pattern,
                    }
                )
    return findings


def main() -> int:
    findings = []
    for repo in configured_repos():
        repo_path = ROOT / repo["target"]
        if not repo_path.exists() or not any(repo_path.iterdir()):
            findings.append({"repo": repo["name"], "missing": True})
            continue
        for path in repo_path.rglob("*.py"):
            if ".git" in path.parts:
                continue
            findings.extend(scan_file(path, repo["name"]))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"findings": findings}, indent=2), encoding="utf-8")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
