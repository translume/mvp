from __future__ import annotations

import pytest

from translume_core.indexing.documents import document_chunk_to_opensearch_doc
from translume_core.indexing.index_specs import build_document_chunk_index_spec
from translume_core.indexing.retrieval_scope import (
    RetrievalScopeError,
    build_retrieval_scope,
)
from translume_schemas.document import DocumentChunk


def _chunk() -> DocumentChunk:
    return DocumentChunk(
        chunk_id="c1",
        case_id="case",
        session_id="s",
        source_file_id="f",
        report_type="NGS",
        page_start=1,
        page_end=1,
        section="genomic_variants",
        chunk_type="molecular_finding",
        source_text="CHEK2",
        source_block_ids=["b1"],
        needs_human_review=True,
    )


def test_index_spec_contains_filters_without_vector_overclaim() -> None:
    spec = build_document_chunk_index_spec(retrieval_mode="lexical")
    props = spec["body"]["mappings"]["properties"]
    assert props["case_id"]["type"] == "keyword"
    assert props["source_text"]["type"] == "text"
    assert props["retrieval_mode"]["type"] == "keyword"
    assert "embedding" not in props
    assert "settings" not in spec["body"]


def test_vector_index_spec_fails_until_embeddings_exist() -> None:
    with pytest.raises(RetrievalScopeError, match="Vector/HNSW retrieval is not enabled"):
        build_document_chunk_index_spec(retrieval_mode="vector", vector_dimension=384)


def test_document_conversion_rejects_embeddings_in_lexical_mvp() -> None:
    chunk = _chunk()
    with pytest.raises(ValueError, match="embedding was provided"):
        document_chunk_to_opensearch_doc(chunk, [0.1, 0.2], retrieval_mode="lexical")
    with pytest.raises(ValueError, match="expected_vector_dimension"):
        document_chunk_to_opensearch_doc(chunk, expected_vector_dimension=2)


def test_document_conversion_records_lexical_retrieval_scope() -> None:
    doc = document_chunk_to_opensearch_doc(_chunk())
    assert doc["case_id"] == "case"
    assert doc["retrieval_mode"] == "lexical"
    assert doc["retrieval_method"] == "opensearch_metadata_lexical"
    assert "embedding" not in doc


def test_retrieval_scope_rejects_hnsw_without_embeddings() -> None:
    with pytest.raises(RetrievalScopeError, match="Vector/HNSW retrieval is not enabled"):
        build_retrieval_scope("hnsw")
