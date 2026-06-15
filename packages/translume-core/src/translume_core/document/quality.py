from __future__ import annotations

from translume_schemas.document import DocumentExtractionOutput, ExtractionQualityReport


def score_extraction_quality(
    extraction: DocumentExtractionOutput,
    *,
    sparse_page_threshold: int = 20,
    min_quality_score: float = 0.75,
) -> ExtractionQualityReport:
    """Score document extraction quality.

    Acceptance criteria:
        1. Empty extraction produces needs_human_review=true.
        2. Sparse extraction produces a warning.
        3. Quality score is deterministic from input and thresholds.
        4. Thresholds are explicit arguments, not hidden state.
        5. Function is pure.

    Args:
        extraction: Extracted document output.
        sparse_page_threshold: Minimum non-whitespace chars for a useful page.
        min_quality_score: Score below which human review is required.

    Returns:
        Extraction quality report.
    """
    pages = extraction.pages
    warnings = list(extraction.warnings)
    if not pages:
        return ExtractionQualityReport(
            source_file_id=extraction.source_file_id,
            quality_score=0.0,
            pages_with_text=0,
            pages_with_warnings=0,
            table_count=0,
            warnings=[*warnings, "no pages extracted"],
            needs_human_review=True,
        )
    pages_with_text = sum(1 for page in pages if page.text.strip())
    sparse_pages = [
        page.page_number for page in pages if len(page.text.strip()) < sparse_page_threshold
    ]
    if sparse_pages:
        warnings.append(f"sparse pages: {','.join(str(p) for p in sparse_pages)}")
    pages_with_warnings = sum(1 for page in pages if page.warnings)
    table_count = sum(len(page.tables) for page in pages)
    text_score = pages_with_text / len(pages)
    warning_penalty = min(0.5, (pages_with_warnings + len(sparse_pages)) / (2 * len(pages)))
    quality_score = max(0.0, min(1.0, text_score - warning_penalty))
    return ExtractionQualityReport(
        source_file_id=extraction.source_file_id,
        quality_score=quality_score,
        pages_with_text=pages_with_text,
        pages_with_warnings=pages_with_warnings,
        table_count=table_count,
        warnings=warnings,
        needs_human_review=quality_score < min_quality_score,
    )


def select_best_document_extraction(
    candidates: list[DocumentExtractionOutput],
    quality_reports: list[ExtractionQualityReport],
) -> DocumentExtractionOutput:
    """Select the best extraction result.

    Acceptance criteria:
        1. Candidate/report lengths must match.
        2. Empty candidates raise `ValueError`.
        3. Highest quality score wins.
        4. Ties prefer Docling/Granite Docling extraction.
        5. Function is deterministic.

    Args:
        candidates: Extraction candidates.
        quality_reports: Quality reports corresponding to candidates.

    Returns:
        Best extraction candidate.

    Raises:
        ValueError: If candidate inputs are invalid.
    """
    if not candidates:
        raise ValueError("no extraction candidates supplied")
    if len(candidates) != len(quality_reports):
        raise ValueError("candidates and quality_reports length mismatch")
    ranked = sorted(
        zip(candidates, quality_reports, strict=True),
        key=lambda item: (
            item[1].quality_score,
            item[0].extraction_method in {"docling", "granite_docling"},
        ),
        reverse=True,
    )
    return ranked[0][0]
