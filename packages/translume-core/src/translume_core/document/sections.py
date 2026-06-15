from __future__ import annotations

import re
from uuid import NAMESPACE_URL, uuid5

from translume_schemas.document import DetectedSection, DocumentBlock, DocumentExtractionOutput


def detect_section_headers(extraction: DocumentExtractionOutput) -> list[DetectedSection]:
    """Detect report sections from layout-aware document blocks.

    Acceptance criteria:
        1. Detects headings from Docling block types when available.
        2. Detects likely headings from text shape when layout labels are not
           available.
        3. Returns page and block ranges for each detected section.
        4. Overlapping ranges are resolved deterministically by block order.
        5. Unknown headings are preserved as normalized section labels instead
           of being discarded.
        6. Function is pure and performs no clinical inference.

    Args:
        extraction: Document extraction output.

    Returns:
        Detected report sections.
    """
    flat_blocks = [block for page in extraction.pages for block in page.blocks]
    starts = [
        (index, _section_slug(block.text), block)
        for index, block in enumerate(flat_blocks)
        if _is_section_header(block)
    ]
    sections: list[DetectedSection] = []
    for pos, (start_index, slug, block) in enumerate(starts):
        end_index = starts[pos + 1][0] - 1 if pos + 1 < len(starts) else len(flat_blocks) - 1
        end_block = flat_blocks[end_index]
        section_id = f"section_{uuid5(NAMESPACE_URL, f'{extraction.source_file_id}:{start_index}:{slug}').hex[:16]}"
        sections.append(
            DetectedSection(
                section_id=section_id,
                label=slug,
                page_start=block.page_number,
                page_end=end_block.page_number,
                block_start=start_index,
                block_end=end_index,
            )
        )
    return sections


def classify_document_block(
    block: DocumentBlock,
    current_section: DetectedSection | None,
) -> str:
    """Classify a document block into a retrieval chunk type.

    Acceptance criteria:
        1. Same block and section return the same chunk type.
        2. Classification uses section/text structure, not clinical inference.
        3. Ambiguous blocks are marked unknown.
        4. Function does not call a model or external dependency.
        5. Function is pure.

    Args:
        block: Document block to classify.
        current_section: Detected section containing the block.

    Returns:
        Chunk type label.
    """
    if current_section is None:
        return "unknown"
    section_text = current_section.label.replace("_", " ")
    return _chunk_type_from_text(f"{section_text} {block.block_type} {block.text}")


def _is_section_header(block: DocumentBlock) -> bool:
    block_type = block.block_type.casefold()
    if block_type in {"heading", "section_header", "title"}:
        return bool(_section_slug(block.text))
    text = block.text.strip()
    if not text:
        return False
    if len(text) > 96:
        return False
    if any(char.isdigit() for char in text) and not text.endswith(":"):
        return False
    letters = [char for char in text if char.isalpha()]
    if not letters:
        return False
    uppercase_ratio = sum(1 for char in letters if char.isupper()) / len(letters)
    has_heading_shape = uppercase_ratio >= 0.75 and len(text.split()) <= 8
    return has_heading_shape or text.endswith(":")


def _section_slug(text: str) -> str:
    tokens = re.findall(r"[A-Za-z0-9]+", text.casefold())
    if not tokens:
        return "unknown_section"
    return "_".join(tokens[:8])


def _chunk_type_from_text(text: str) -> str:
    normalized = text.casefold()
    token_groups = (
        (("expression", "transcript", "rna"), "rna_expression"),
        (("fusion", "rearrangement", "splicing"), "rna_rearrangement"),
        (("unknown", "vus", "significance"), "vus"),
        (("coverage",), "low_coverage"),
        (("trial", "nct"), "clinical_trial_context"),
        (("immunotherapy", "microsatellite", "mutational", "tmb", "msi"), "immunotherapy_marker"),
        (("detail",), "variant_detail"),
        (("assay", "limitation", "disclaimer", "description"), "assay_limitation"),
        (("variant", "genomic", "copy", "number", "mutation"), "molecular_finding"),
        (("metadata", "diagnosis", "specimen", "physician"), "case_metadata"),
    )
    for tokens, chunk_type in token_groups:
        if any(token in normalized for token in tokens):
            return chunk_type
    return "unknown"
