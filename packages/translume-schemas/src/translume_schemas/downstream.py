from __future__ import annotations

from translume_schemas.base import TranslumeBaseModel


class DownstreamAnalysisRequest(TranslumeBaseModel):
    """Request one precision-oncology and pathway-analysis workflow.

    Acceptance criteria:
        1. Validation: Diagnosis is non-empty after whitespace normalization.
        2. Immutability: The request cannot be mutated after validation.
    """

    diagnosis: str


class PrecisionPipelineRun(TranslumeBaseModel):
    """Represent the verified precision-oncology pipeline output location."""

    session_id: str
    run_id: str
    run_directory: str
    trial_prescreens_path: str


class DownstreamAnalysisResult(TranslumeBaseModel):
    """Represent verified Markdown artifacts produced for one review packet."""

    session_id: str
    diagnosis: str
    precision_run: PrecisionPipelineRun
    pathway_analysis_markdown: str
    research_memo_markdown: str
    tumor_board_summary_markdown: str
    pathway_analysis_path: str
    research_memo_path: str
    tumor_board_summary_path: str
