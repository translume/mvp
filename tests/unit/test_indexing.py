from __future__ import annotations

import pytest

from translume_core.indexing.documents import document_chunk_to_opensearch_doc
from translume_core.indexing.index_specs import build_document_chunk_index_spec
from translume_schemas.document import DocumentChunk


def test_index_spec_contains_filters_and_vector() -> None:
    spec = build_document_chunk_index_spec(384)
    props = spec["body"]["mappings"]["properties"]
    assert props["case_id"]["type"] == "keyword"
    assert props["embedding"]["dimension"] == 384


def test_document_conversion_validates_embedding_dimension() -> None:
    chunk = DocumentChunk(
        chunk_id="c1", case_id="case", session_id="s", source_file_id="f", report_type="NGS",
        page_start=1, page_end=1, section="genomic_variants", chunk_type="molecular_finding",
        source_text="CHEK2", source_block_ids=["b1"], needs_human_review=True,
    )
    with pytest.raises(ValueError, match="embedding dimension mismatch"):
        document_chunk_to_opensearch_doc(chunk, [0.1], expected_vector_dimension=2)
    doc = document_chunk_to_opensearch_doc(chunk, [0.1, 0.2], expected_vector_dimension=2)
    assert doc["case_id"] == "case"
    assert doc["embedding"] == [0.1, 0.2]
