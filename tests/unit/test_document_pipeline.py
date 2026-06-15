from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from translume_core.document.chunks import build_document_chunks, merge_small_adjacent_chunks
from translume_core.document.quality import score_extraction_quality, select_best_document_extraction
from translume_core.document.sections import detect_section_headers
from translume_core.ingestion.sessions import create_case_session
from translume_schemas.document import DocumentBlock, DocumentExtractionOutput, DocumentPage
from translume_schemas.session import StoredFile


def _extraction(method: str = "docling") -> DocumentExtractionOutput:
    blocks = [
        DocumentBlock(block_id="b1", page_number=1, block_type="heading", text="GENOMIC VARIANTS", order_index=0),
        DocumentBlock(block_id="b2", page_number=1, block_type="text", text="CHEK2 LOF 85.6%", order_index=1),
        DocumentBlock(block_id="b3", page_number=1, block_type="heading", text="ASSAY DESCRIPTION", order_index=2),
        DocumentBlock(block_id="b4", page_number=1, block_type="text", text="No normal sample was received.", order_index=3),
    ]
    return DocumentExtractionOutput(
        source_file_id="file_a",
        extraction_method=method,
        pages=[DocumentPage(page_number=1, text="\n".join(b.text for b in blocks), blocks=blocks, tables=[])],
    )


def test_quality_and_selection_prefers_docling_on_tie() -> None:
    docling = _extraction("docling")
    pymupdf = _extraction("pymupdf")
    q1 = score_extraction_quality(docling)
    q2 = score_extraction_quality(pymupdf)
    assert select_best_document_extraction([pymupdf, docling], [q2, q1]).extraction_method == "docling"


def test_section_detection_and_chunk_building() -> None:
    extraction = _extraction()
    sections = detect_section_headers(extraction)
    session = create_case_session("NGS", "research_support_only", datetime.now(timezone.utc), case_id="case_a", session_id="sess_a")
    stored = StoredFile(case_id="case_a", session_id="sess_a", source_file_id="file_a", filename="a.pdf", path=Path("/tmp/a.pdf"), size_bytes=1, sha256="abc")
    chunks = build_document_chunks(extraction, sections, session, stored)
    assert chunks[1].section == "genomic_variants"
    assert chunks[1].chunk_type == "molecular_finding"


def test_merge_small_adjacent_chunks_same_section_only() -> None:
    extraction = _extraction()
    sections = detect_section_headers(extraction)
    session = create_case_session("NGS", "research_support_only", datetime.now(timezone.utc), case_id="case_a", session_id="sess_a")
    stored = StoredFile(case_id="case_a", session_id="sess_a", source_file_id="file_a", filename="a.pdf", path=Path("/tmp/a.pdf"), size_bytes=1, sha256="abc")
    chunks = build_document_chunks(extraction, sections, session, stored)
    merged = merge_small_adjacent_chunks(chunks, max_chars=200)
    assert len(merged) < len(chunks)
    assert any(chunk.section == "assay_description" for chunk in merged)
