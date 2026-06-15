from __future__ import annotations

from uuid import uuid5, NAMESPACE_URL

from translume_core.document.sections import classify_document_block
from translume_schemas.document import DetectedSection, DocumentChunk, DocumentExtractionOutput
from translume_schemas.session import CaseSession, StoredFile


def _section_for_block_index(
    sections: list[DetectedSection],
    block_index: int,
) -> DetectedSection | None:
    for section in sections:
        if section.block_start <= block_index <= section.block_end:
            return section
    return None


def build_document_chunks(
    extraction: DocumentExtractionOutput,
    sections: list[DetectedSection],
    session: CaseSession,
    stored_file: StoredFile,
) -> list[DocumentChunk]:
    """Build source-backed chunks from extracted document blocks.

    Acceptance criteria:
        1. Every chunk has case_id, session_id, and source_file_id.
        2. Every chunk has page range, section, source text, and chunk type.
        3. Every chunk has source block IDs.
        4. Chunk order is stable.
        5. Low-quality extraction propagates needs_human_review.
        6. No clinical claims are generated.

    Args:
        extraction: Source document extraction.
        sections: Detected section ranges.
        session: Active case session.
        stored_file: Stored source file.

    Returns:
        Document chunks.
    """
    flat_blocks = [block for page in extraction.pages for block in page.blocks]
    chunks: list[DocumentChunk] = []
    for index, block in enumerate(flat_blocks):
        section = _section_for_block_index(sections, index)
        section_label = section.label if section is not None else "unknown_section"
        chunk_type = classify_document_block(block, section)
        chunk_id = f"chunk_{uuid5(NAMESPACE_URL, f'{stored_file.source_file_id}:{block.block_id}').hex[:16]}"
        chunks.append(
            DocumentChunk(
                chunk_id=chunk_id,
                case_id=session.case_id,
                session_id=session.session_id,
                source_file_id=stored_file.source_file_id,
                report_type=session.report_type,
                page_start=block.page_number,
                page_end=block.page_number,
                section=section_label,
                chunk_type=chunk_type,
                source_text=block.text,
                source_block_ids=[block.block_id],
                bbox=block.bbox,
                needs_human_review=extraction.needs_human_review,
            )
        )
    return chunks


def merge_small_adjacent_chunks(
    chunks: list[DocumentChunk],
    max_chars: int,
) -> list[DocumentChunk]:
    """Merge small adjacent chunks from the same section and chunk type.

    Acceptance criteria:
        1. Only adjacent chunks from same section/type may merge.
        2. Merged source text preserves original order.
        3. Merged source block IDs preserve all original IDs.
        4. Merged chunk length does not exceed max_chars.
        5. Function does not merge different clinical sections.
        6. Function is deterministic and pure.

    Args:
        chunks: Ordered chunks.
        max_chars: Maximum merged source text length.

    Returns:
        Merged chunk list.
    """
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
    merged: list[DocumentChunk] = []
    for chunk in chunks:
        if not merged:
            merged.append(chunk)
            continue
        previous = merged[-1]
        candidate_text = f"{previous.source_text}\n{chunk.source_text}"
        can_merge = (
            previous.section == chunk.section
            and previous.chunk_type == chunk.chunk_type
            and len(candidate_text) <= max_chars
        )
        if not can_merge:
            merged.append(chunk)
            continue
        merged[-1] = previous.model_copy(
            update={
                "page_end": chunk.page_end,
                "source_text": candidate_text,
                "source_block_ids": [*previous.source_block_ids, *chunk.source_block_ids],
                "needs_human_review": previous.needs_human_review or chunk.needs_human_review,
            }
        )
    return merged
