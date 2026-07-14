from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException

import precision_oncology_runner


def test_run_directory_requires_a_child_of_output_root(tmp_path: Path) -> None:
    """Runner should reject command output outside its configured output root."""
    output_root = tmp_path / "outputs"
    output_root.mkdir()
    run_directory = output_root / "run-1"
    run_directory.mkdir()

    resolved = precision_oncology_runner._run_directory_from_stdout(
        f"run_dir={run_directory}\n",
        output_root,
    )

    assert resolved == run_directory.resolve()
    with pytest.raises(HTTPException):
        precision_oncology_runner._run_directory_from_stdout(
            f"run_dir={tmp_path}\n",
            output_root,
        )
