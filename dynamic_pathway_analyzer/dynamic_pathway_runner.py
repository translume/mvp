"""HTTP boundary for the standalone dynamic pathway-analysis commands."""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

_IDENTIFIER_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}")
_ARTIFACT_ROOT = Path(os.getenv("PIPELINE_ARTIFACT_ROOT", "/app/outputs"))

app = FastAPI(title="Dynamic Pathway Analyzer Runner")


class DynamicRunRequest(BaseModel):
    """Request both dynamic pathway-analysis stages for one precision run."""

    session_id: str
    precision_run_id: str
    diagnosis: str


class DynamicRunResponse(BaseModel):
    """Return the three verified Markdown artifacts for one analysis."""

    session_id: str
    diagnosis: str
    pathway_analysis_markdown: str
    research_memo_markdown: str
    tumor_board_summary_markdown: str
    pathway_analysis_path: str
    research_memo_path: str
    tumor_board_summary_path: str


@app.get("/health")
def health() -> dict[str, str]:
    """Return runner readiness without executing a model call."""
    if not os.getenv("OPENAI_API_KEY", "").strip():
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY is required.")
    if os.getenv("OPENAI_REASONING_MODE", "pro") != "pro":
        raise HTTPException(status_code=503, detail="OpenAI Pro mode is required.")
    if (
        os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        != "https://api.openai.com/v1"
    ):
        raise HTTPException(
            status_code=503, detail="Official OpenAI endpoint required."
        )
    return {
        "status": "ok",
        "service": "dynamic-pathway-analyzer",
        "provider": "openai",
        "reasoning_mode": "pro",
    }


@app.post("/runs", response_model=DynamicRunResponse)
def run_dynamic_pathway_analysis(
    request: DynamicRunRequest,
) -> DynamicRunResponse:
    """Run both analyzer stages and return verified Markdown output.

    Acceptance criteria:
        1. Validation: IDs and diagnosis are non-empty and path-safe.
        2. Isolation: Outputs remain below the session-specific artifact root.
        3. Execution: Both existing CLIs run without shell interpolation.
        4. Verification: All returned Markdown files exist and are non-empty.
    """
    session_id = _validated_identifier(request.session_id, "session_id")
    run_id = _validated_identifier(request.precision_run_id, "precision_run_id")
    diagnosis = request.diagnosis.strip()
    if not diagnosis:
        raise HTTPException(status_code=422, detail="Diagnosis is required.")
    deadline = time.monotonic() + _run_timeout()

    session_root = _ARTIFACT_ROOT / session_id
    input_path = (
        session_root
        / "precision_oncology_outputs"
        / run_id
        / "state_after_trial_prescreens.json"
    )
    if not input_path.is_file():
        raise HTTPException(
            status_code=422,
            detail="Trial-prescreens input is missing.",
        )
    pathway_root = session_root / "pathway_output_comprehensive" / run_id
    tumor_root = session_root / "tumor_board_output" / run_id
    _run_command(
        "dynamic pathway analysis",
        [
            sys.executable,
            "/app/dynamic_pathway_analyzer.py",
            str(input_path),
            "--diagnosis",
            diagnosis,
            "--output-dir",
            str(pathway_root),
            "--model",
            _reasoning_model(),
            "--normalizer-model",
            os.getenv("OPENAI_NORMALIZER_MODEL", _reasoning_model()),
            "--reasoning-mode",
            os.getenv("OPENAI_REASONING_MODE", "pro"),
            "--reasoning-effort",
            os.getenv("OPENAI_REASONING_EFFORT", "xhigh"),
            "--request-timeout",
            os.getenv("OPENAI_REQUEST_TIMEOUT_SECONDS", "900"),
        ],
        timeout_seconds=_remaining_seconds(deadline),
    )
    stem = input_path.stem
    pathway_path = pathway_root / f"{stem}.pathway_analysis.md"
    research_path = pathway_root / f"{stem}.research_memo.md"
    _require_markdown(pathway_path, "Pathway analysis")
    _require_markdown(research_path, "Research memo")
    _run_command(
        "tumor-board causal synthesis",
        [
            sys.executable,
            "/app/tumor_board_causal_synthesis.py",
            "--pathway-analysis",
            str(pathway_path),
            "--research-memo",
            str(research_path),
            "--diagnosis",
            diagnosis,
            "--output-dir",
            str(tumor_root),
            "--model",
            _reasoning_model(),
            "--reasoning-mode",
            os.getenv("OPENAI_REASONING_MODE", "pro"),
            "--reasoning-effort",
            os.getenv("OPENAI_REASONING_EFFORT", "xhigh"),
            "--request-timeout",
            os.getenv("OPENAI_REQUEST_TIMEOUT_SECONDS", "900"),
        ],
        timeout_seconds=_remaining_seconds(deadline),
    )
    summary_path = tumor_root / "onco_board_summary.md"
    return DynamicRunResponse(
        session_id=session_id,
        diagnosis=diagnosis,
        pathway_analysis_markdown=_require_markdown(
            pathway_path,
            "Pathway analysis",
        ),
        research_memo_markdown=_require_markdown(
            research_path,
            "Research memo",
        ),
        tumor_board_summary_markdown=_require_markdown(
            summary_path,
            "Tumor-board summary",
        ),
        pathway_analysis_path=_relative_path(pathway_path),
        research_memo_path=_relative_path(research_path),
        tumor_board_summary_path=_relative_path(summary_path),
    )


def _validated_identifier(value: str, label: str) -> str:
    normalized = value.strip()
    if not _IDENTIFIER_PATTERN.fullmatch(normalized):
        raise HTTPException(status_code=422, detail=f"Invalid {label}.")
    return normalized


def _run_command(
    label: str,
    command: list[str],
    *,
    timeout_seconds: float | None = None,
) -> None:
    """Execute a bounded command and return only secret-redacted diagnostics."""
    timeout = _run_timeout() if timeout_seconds is None else timeout_seconds
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as error:
        raise HTTPException(
            status_code=504,
            detail=f"{label} exceeded {timeout:g} seconds.",
        ) from error
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "no output"
        detail = re.sub(r"\bsk-[A-Za-z0-9_-]{8,}\b", "[REDACTED]", detail)
        detail = re.sub(r"(?i)\bBearer\s+\S+", "Bearer [REDACTED]", detail)
        detail = re.sub(
            r"(?i)\b(api[_-]?key)\s*[=:]\s*\S+",
            r"\1=[REDACTED]",
            detail,
        )
        raise HTTPException(
            status_code=422,
            detail=(
                f"{label} failed with exit code {result.returncode}: {detail[-2000:]}"
            ),
        )


def _reasoning_model() -> str:
    """Resolve the same model role used by the main application."""
    return os.getenv("OPENAI_REASONING_MODEL", os.getenv("OPENAI_MODEL", "gpt-6-astra"))


def _run_timeout() -> float:
    """Return the finite deadline shared by both subprocesses."""
    try:
        value = float(os.getenv("DYNAMIC_PATHWAY_RUN_TIMEOUT_SECONDS", "7200"))
    except ValueError as error:
        raise HTTPException(
            status_code=503,
            detail="Invalid analyzer run timeout.",
        ) from error
    if not 1 <= value <= 86400:
        raise HTTPException(status_code=503, detail="Invalid analyzer run timeout.")
    return value


def _remaining_seconds(deadline: float) -> float:
    """Fail before starting another subprocess if the analysis deadline expired."""
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise HTTPException(
            status_code=504, detail="Dynamic analysis deadline exceeded."
        )
    return remaining


def _require_markdown(path: Path, label: str) -> str:
    if not path.is_file():
        raise HTTPException(
            status_code=422,
            detail=f"{label} output is missing.",
        )
    content = path.read_text(encoding="utf-8").strip()
    if not content:
        raise HTTPException(status_code=422, detail=f"{label} output is empty.")
    return content


def _relative_path(path: Path) -> str:
    return str(path.resolve().relative_to(_ARTIFACT_ROOT.resolve()))
