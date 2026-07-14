from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException

import dynamic_pathway_runner


def test_require_markdown_rejects_missing_and_empty_artifacts(tmp_path: Path) -> None:
    """Runner should return only existing non-empty Markdown artifacts."""
    missing = tmp_path / "missing.md"
    with pytest.raises(HTTPException):
        dynamic_pathway_runner._require_markdown(missing, "Missing")

    empty = tmp_path / "empty.md"
    empty.write_text("\n", encoding="utf-8")
    with pytest.raises(HTTPException):
        dynamic_pathway_runner._require_markdown(empty, "Empty")

    completed = tmp_path / "completed.md"
    completed.write_text("# Completed\n", encoding="utf-8")
    assert dynamic_pathway_runner._require_markdown(completed, "Completed") == "# Completed"
