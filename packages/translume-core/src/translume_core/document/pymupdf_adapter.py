from __future__ import annotations

from uuid import NAMESPACE_URL, uuid5

import fitz

from translume_schemas.document import (
    BoundingBox,
    DocumentBlock,
    DocumentExtractionOutput,
    DocumentPage,
)
from translume_schemas.session import StoredFile


def extract_document_with_pymupdf(stored_file: StoredFile) -> DocumentExtractionOutput:
    """Extract a PDF into page and block records using PyMuPDF.

    Acceptance criteria:
        1. Each page has page_number and text.
        2. Empty PDFs raise `ValueError`.
        3. Pages with no text are included with warning flags.
        4. Extraction method is recorded as `pymupdf`.
        5. Does not perform clinical interpretation.
        6. Output can be passed into section-aware chunking.

    Args:
        stored_file: Stored PDF metadata.

    Returns:
        Structured document extraction output.

    Raises:
        ValueError: If the PDF cannot be opened or has zero pages.
    """
    try:
        document = fitz.open(stored_file.path)
    except Exception as error:  # pragma: no cover - PyMuPDF-specific detail.
        raise ValueError(f"unable to open PDF: {stored_file.path}") from error
    if document.page_count == 0:
        raise ValueError("PDF has no pages")
    pages: list[DocumentPage] = []
    warnings: list[str] = []
    for page_index in range(document.page_count):
        page = document.load_page(page_index)
        blocks = _page_blocks(stored_file.source_file_id, page_index + 1, page)
        text = "\n".join(block.text for block in blocks if block.text.strip())
        page_warnings = [] if text.strip() else ["page_has_no_extractable_text"]
        warnings.extend(f"page_{page_index + 1}:{warning}" for warning in page_warnings)
        pages.append(
            DocumentPage(
                page_number=page_index + 1,
                text=text,
                blocks=blocks,
                tables=[],
                warnings=page_warnings,
            )
        )
    document.close()
    needs_review = bool(warnings)
    return DocumentExtractionOutput(
        source_file_id=stored_file.source_file_id,
        extraction_method="pymupdf",
        pages=pages,
        warnings=warnings,
        quality_score=None,
        needs_human_review=needs_review,
    )


def _page_blocks(
    source_file_id: str,
    page_number: int,
    page: fitz.Page,
) -> list[DocumentBlock]:
    """Return deterministic text blocks for a PyMuPDF page.

    Acceptance criteria:
        1. Blocks preserve page order.
        2. Empty blocks are discarded.
        3. Bbox coordinates are preserved when provided by PyMuPDF.
        4. No clinical interpretation is performed.

    Args:
        source_file_id: Source file identifier.
        page_number: One-indexed page number.
        page: PyMuPDF page object.

    Returns:
        Ordered document blocks.
    """
    raw_blocks = page.get_text("blocks")
    sorted_blocks = sorted(raw_blocks, key=lambda item: (item[1], item[0], item[5]))
    blocks: list[DocumentBlock] = []
    for order_index, block in enumerate(sorted_blocks):
        x1, y1, x2, y2, text, *_ = block
        normalized_text = " ".join(str(text).split())
        if not normalized_text:
            continue
        block_id = f"block_{uuid5(NAMESPACE_URL, f'{source_file_id}:{page_number}:{order_index}:{normalized_text[:80]}').hex[:16]}"
        blocks.append(
            DocumentBlock(
                block_id=block_id,
                page_number=page_number,
                block_type="text",
                text=normalized_text,
                order_index=order_index,
                bbox=BoundingBox(x1=float(x1), y1=float(y1), x2=float(x2), y2=float(y2)),
                confidence=None,
            )
        )
    return blocks
