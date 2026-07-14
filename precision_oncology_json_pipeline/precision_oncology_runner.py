"""HTTP boundary for the standalone precision-oncology command pipeline."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel


_IDENTIFIER_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}")
_ARTIFACT_ROOT = Path(os.getenv("PIPELINE_ARTIFACT_ROOT", "/app/outputs"))

app = FastAPI(title="Precision Oncology Pipeline Runner")


class PrecisionRunRequest(BaseModel):
    """Request a pipeline execution using one persisted review packet."""

    session_id: str
    review_packet: dict[str, Any]


class PrecisionRunResponse(BaseModel):
    """Describe verified artifacts from one completed precision pipeline run."""

    session_id: str
    run_id: str
    run_directory: str
    trial_prescreens_path: str


@app.get("/health")
def health() -> dict[str, str]:
    """Return runner readiness without executing a model call."""
    return {"status": "ok", "service": "precision-oncology-pipeline"}


@app.post("/runs", response_model=PrecisionRunResponse)
def run_precision_pipeline(
    request: PrecisionRunRequest,
) -> PrecisionRunResponse:
    """Run the precision pipeline and return trial-prescreen output.

    Acceptance criteria:
        1. Validation: Session IDs cannot escape the configured artifact root.
        2. Isolation: Writes only below the session-specific artifact directory.
        3. Execution: Invokes the existing CLI without shell interpolation.
        4. Verification: Returns only an existing trial-prescreens JSON file.
    """
    session_id = _validated_identifier(request.session_id, "session_id")
    session_root = _ARTIFACT_ROOT / session_id
    input_path = session_root / "translume_review_packet.json"
    output_root = session_root / "precision_oncology_outputs"
    _write_json(input_path, request.review_packet)

    command = [
        sys.executable,
        "/app/precision_oncology_pipeline.py",
        "--input",
        str(input_path),
        "--output-dir",
        str(output_root),
        "--model",
        os.getenv("OPENAI_MODEL", "gpt-5.6-luna"),
        "--reasoning-effort",
        os.getenv("OPENAI_REASONING_EFFORT", "medium"),
    ]
    result = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise HTTPException(
            status_code=422,
            detail=_command_error("precision-oncology pipeline", result),
        )

    run_directory = _run_directory_from_stdout(result.stdout, output_root)
    trial_prescreens = run_directory / "state_after_trial_prescreens.json"
    if not trial_prescreens.is_file():
        raise HTTPException(
            status_code=422,
            detail=(
                "Precision-oncology pipeline did not produce trial prescreens."
            ),
        )
    return PrecisionRunResponse(
        session_id=session_id,
        run_id=run_directory.name,
        run_directory=_relative_path(run_directory),
        trial_prescreens_path=_relative_path(trial_prescreens),
    )


def _validated_identifier(value: str, label: str) -> str:
    normalized = value.strip()
    if not _IDENTIFIER_PATTERN.fullmatch(normalized):
        raise HTTPException(status_code=422, detail=f"Invalid {label}.")
    return normalized


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    temporary.replace(path)


def _run_directory_from_stdout(stdout: str, output_root: Path) -> Path:
    candidates = [
        line.removeprefix("run_dir=").strip()
        for line in stdout.splitlines()
        if line.startswith("run_dir=")
    ]
    if len(candidates) != 1:
        raise HTTPException(
            status_code=422,
            detail="Pipeline did not report one run directory.",
        )
    run_directory = Path(candidates[0]).resolve()
    output_root = output_root.resolve()
    if output_root not in run_directory.parents or not run_directory.is_dir():
        raise HTTPException(
            status_code=422,
            detail="Pipeline reported an invalid run directory.",
        )
    return run_directory


def _relative_path(path: Path) -> str:
    return str(path.resolve().relative_to(_ARTIFACT_ROOT.resolve()))


def _command_error(label: str, result: subprocess.CompletedProcess[str]) -> str:
    detail = result.stderr.strip() or result.stdout.strip() or "no output"
    return f"{label} failed with exit code {result.returncode}: {detail[:2000]}"
