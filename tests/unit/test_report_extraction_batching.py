from __future__ import annotations

import pytest

from translume_core.compiler.structured_model_artifacts import (
    _plan_report_extraction_prompt_batches,
)
from translume_schemas.document import DocumentChunk, RetrievedDocumentChunk


def test_report_extraction_batches_cover_all_chunks_in_page_order() -> None:
    """Report-extraction batches should retain every source chunk exactly once.

    Acceptance criteria:
        1. Every input chunk appears in exactly one batch.
        2. No batch exceeds the supplied chunk budget.
        3. Batch order follows source page order deterministically.
    """
    chunks = [_retrieved_chunk(index) for index in (5, 1, 4, 2, 3, 6)]

    batches = _plan_report_extraction_prompt_batches(
        chunks,
        batch_max_chunks=2,
    )

    assert [[item.chunk.page_start for item in batch] for batch in batches] == [
        [1, 2],
        [3, 4],
        [5, 6],
    ]
    assert [
        item.chunk.chunk_id for batch in batches for item in batch
    ] == [f"chunk_{index}" for index in range(1, 7)]


def test_report_extraction_batching_rejects_nonpositive_budget() -> None:
    """A nonpositive extraction chunk budget should be rejected explicitly.

    Acceptance criteria:
        1. Invalid batch budgets raise ValueError.
        2. Input chunks are not mutated.
    """
    chunks = [_retrieved_chunk(1)]

    with pytest.raises(ValueError, match="batch_max_chunks must be positive"):
        _plan_report_extraction_prompt_batches(chunks, batch_max_chunks=0)


def _retrieved_chunk(page: int) -> RetrievedDocumentChunk:
    chunk = DocumentChunk(
        chunk_id=f"chunk_{page}",
        case_id="case_1",
        session_id="session_1",
        source_file_id="source_1",
        report_type="NGS",
        page_start=page,
        page_end=page,
        section="results",
        chunk_type="text",
        source_text=f"Finding on page {page}.",
        source_block_ids=[f"block_{page}"],
        needs_human_review=True,
    )
    return RetrievedDocumentChunk(
        chunk=chunk,
        score=float(page),
        retrieval_method="lexical",
    )
