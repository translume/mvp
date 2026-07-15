"""HTTP boundary for the standalone precision-oncology command pipeline."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

_IDENTIFIER_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}")
_ARTIFACT_ROOT = Path(os.getenv("PIPELINE_ARTIFACT_ROOT", "/app/outputs"))
_PIPELINE_FAILED_MARKER = "Pipeline failed:"
_SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"(?i)\b(Bearer)\s+\S+"),
    re.compile(r"(?i)\b(api[_-]?key)\s*[=:]\s*\S+"),
)
_STAGE_ORDER = (
    "canonical_input",
    "hypotheses",
    "research_plan",
    "sources",
    "source_extractions",
    "source_fit_assessments",
    "trial_prescreens",
    "hypothesis_syntheses",
    "report_draft",
    "cross_source_synthesis",
    "validations",
)

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


@dataclass(frozen=True)
class PipelineFailureDiagnostic:
    """Bounded, non-sensitive diagnostic for one failed pipeline subprocess."""

    exit_code: int
    inferred_stage: str | None
    error: str
    pydantic_warnings_summarized: bool


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
        diagnostic = _pipeline_failure_diagnostic(result, output_root)
        _persist_failure_diagnostic(diagnostic, session_root, output_root)
        raise HTTPException(
            status_code=422,
            detail=_command_error("precision-oncology pipeline", diagnostic),
        )

    run_directory = _run_directory_from_stdout(result.stdout, output_root)
    trial_prescreens = run_directory / "state_after_trial_prescreens.json"
    if not trial_prescreens.is_file():
        raise HTTPException(
            status_code=422,
            detail=("Precision-oncology pipeline did not produce trial prescreens."),
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


def _pipeline_failure_diagnostic(
    result: subprocess.CompletedProcess[str],
    output_root: Path,
) -> PipelineFailureDiagnostic:
    """Extract the final actionable subprocess error without leaking payloads.

    Acceptance criteria:
        1. Prefers the final `Pipeline failed:` message over preceding warnings.
        2. Falls back to bounded stderr, then stdout, then `no output`.
        3. Redacts common API credential shapes.
        4. Infers the next pipeline stage from the latest checkpoint file.
        5. Does not mutate the completed process or filesystem.
    """
    stderr = result.stderr.strip()
    stdout = result.stdout.strip()
    failed_lines = [
        line.strip() for line in stderr.splitlines() if _PIPELINE_FAILED_MARKER in line
    ]
    raw_error = failed_lines[-1] if failed_lines else stderr or stdout or "no output"
    return PipelineFailureDiagnostic(
        exit_code=result.returncode,
        inferred_stage=_infer_failed_stage(output_root),
        error=_bounded_redacted_text(raw_error, max_chars=2000),
        pydantic_warnings_summarized=(
            "Pydantic serializer warnings" in stderr
            or "PydanticSerializationUnexpectedValue" in stderr
        ),
    )


def _command_error(label: str, diagnostic: PipelineFailureDiagnostic) -> str:
    stage = diagnostic.inferred_stage or "unknown"
    warning_note = (
        " Pydantic serializer warnings were omitted."
        if diagnostic.pydantic_warnings_summarized
        else ""
    )
    return (
        f"{label} failed with exit code {diagnostic.exit_code} "
        f"during stage {stage}: {diagnostic.error}{warning_note}"
    )


def _bounded_redacted_text(value: str, *, max_chars: int) -> str:
    """Return whitespace-normalized, secret-redacted text bounded from the tail."""
    redacted = value
    for pattern in _SECRET_PATTERNS:
        redacted = pattern.sub(
            lambda match: (
                f"{match.group(1)} [REDACTED]" if match.lastindex else "[REDACTED]"
            ),
            redacted,
        )
    normalized = " ".join(redacted.split())
    if len(normalized) <= max_chars:
        return normalized
    return f"...{normalized[-(max_chars - 3) :]}"


def _infer_failed_stage(output_root: Path) -> str | None:
    run_directory = _latest_run_directory(output_root)
    if run_directory is None:
        return None
    completed = {
        path.stem.removeprefix("state_after_")
        for path in run_directory.glob("state_after_*.json")
        if path.is_file()
    }
    for index, stage in enumerate(_STAGE_ORDER[:-1]):
        if stage in completed and _STAGE_ORDER[index + 1] not in completed:
            return _STAGE_ORDER[index + 1]
    return None


def _latest_run_directory(output_root: Path) -> Path | None:
    if not output_root.is_dir():
        return None
    candidates = [
        path
        for path in output_root.glob("run_*")
        if path.is_dir() and path.parent.resolve() == output_root.resolve()
    ]
    return max(candidates, key=lambda path: path.stat().st_mtime, default=None)


def _persist_failure_diagnostic(
    diagnostic: PipelineFailureDiagnostic,
    session_root: Path,
    output_root: Path,
) -> None:
    """Atomically persist a bounded diagnostic within the authorized session."""
    run_directory = _latest_run_directory(output_root)
    destination = (run_directory or session_root) / "pipeline_failure.json"
    _write_json(destination, asdict(diagnostic))
