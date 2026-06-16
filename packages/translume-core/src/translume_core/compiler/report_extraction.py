from __future__ import annotations

from collections.abc import Sequence

from translume_schemas.document import DocumentChunk
from translume_schemas.extraction import ReportExtractionOutput


class LegacyReportExtractionDisabledError(RuntimeError):
    """Raised when legacy deterministic report extraction is requested.

    Acceptance criteria:
        1. Prevents deterministic clinical extraction from entering the product
           path.
        2. Directs callers to the local vLLM structured-output extraction path.
        3. Fails loudly instead of returning source-shaped but model-free
           findings.
    """


def generate_report_extraction_from_chunks(
    chunks: Sequence[DocumentChunk],
    *,
    report_type: str,
    source_file_id: str,
) -> ReportExtractionOutput:
    """Fail because report extraction must be local-vLLM structured output.

    This function previously contained deterministic clinical/document rules.
    Under PRIME_DIRECTIVES, production ReportExtractionOutput must be generated
    by the local structured-output model provider from retrieved OpenSearch
    chunks and then source-aligned back to those chunks. Deterministic helpers
    may validate or align source text, but they must not create clinical
    findings.

    Acceptance criteria:
        1. Never returns a ReportExtractionOutput.
        2. Does not inspect report text or infer findings.
        3. Fails loudly with migration guidance.
        4. Keeps old imports from silently reintroducing a non-model path.
    """
    raise LegacyReportExtractionDisabledError(
        "Deterministic report extraction is disabled. Use "
        "generate_report_extraction_with_model from "
        "translume_core.compiler.structured_model_artifacts."
    )
