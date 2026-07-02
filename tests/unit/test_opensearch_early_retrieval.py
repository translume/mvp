from __future__ import annotations

import pytest

from translume_core.indexing.documents import INDEX_DOCUMENT_CHUNKS
from translume_core.indexing.retrieval import (
    build_document_chunk_retrieval_query,
    index_document_chunks_for_retrieval,
    retrieve_indexed_document_chunks,
)
from translume_schemas.document import DocumentChunk


class RecordingVectorStore:
    def __init__(self, *, return_documents: bool = True) -> None:
        self.ensured: list[str] = []
        self.indexed: dict[str, list[dict[str, object]]] = {}
        self.index_refreshes: list[str | None] = []
        self.search_queries: list[dict[str, object]] = []
        self.return_documents = return_documents

    async def ensure_index(self, index_name: str, body: dict[str, object]) -> None:
        self.ensured.append(index_name)

    async def index(
        self,
        index_name: str,
        documents: list[dict[str, object]],
        *,
        refresh: str | None = None,
    ) -> None:
        self.indexed.setdefault(index_name, []).extend(documents)
        self.index_refreshes.append(refresh)

    async def search(self, index_name: str, query: dict[str, object]) -> list[dict[str, object]]:
        self.search_queries.append(query)
        if not self.return_documents:
            return []
        return [dict(document, _score=1.0) for document in self.indexed.get(index_name, [])]


def _chunk() -> DocumentChunk:
    return DocumentChunk(
        chunk_id="chunk1",
        case_id="case1",
        session_id="session1",
        source_file_id="file1",
        report_type="NGS",
        page_start=1,
        page_end=1,
        section="GENOMIC VARIANTS",
        chunk_type="molecular_finding",
        source_text="CHEK2 LOF",
        source_block_ids=["block1"],
        needs_human_review=True,
    )


def test_retrieval_query_is_case_session_source_scoped() -> None:
    query = build_document_chunk_retrieval_query(
        case_id="case1",
        session_id="session1",
        source_file_id="file1",
        top_k=10,
    )
    filters = query["query"]["bool"]["filter"]
    assert {"term": {"case_id": "case1"}} in filters
    assert {"term": {"session_id": "session1"}} in filters
    assert {"term": {"source_file_id": "file1"}} in filters
    assert query["size"] == 10


@pytest.mark.asyncio
async def test_chunks_are_indexed_and_retrieved_before_artifacts() -> None:
    store = RecordingVectorStore()
    result = await index_document_chunks_for_retrieval(
        vector_store=store,
        chunks=[_chunk()],
        retrieval_mode="lexical",
    )
    assert result.indexed_count == 1
    assert INDEX_DOCUMENT_CHUNKS in store.ensured
    assert store.index_refreshes == ["wait_for"]
    retrieved = await retrieve_indexed_document_chunks(
        vector_store=store,
        case_id="case1",
        session_id="session1",
        source_file_id="file1",
        top_k=10,
    )
    assert retrieved[0].chunk.chunk_id == "chunk1"
    assert retrieved[0].retrieval_method == "opensearch_metadata_lexical"
    assert store.search_queries


@pytest.mark.asyncio
async def test_zero_retrieved_chunks_blocks_artifact_generation() -> None:
    store = RecordingVectorStore(return_documents=False)
    await index_document_chunks_for_retrieval(
        vector_store=store,
        chunks=[_chunk()],
        retrieval_mode="lexical",
    )
    with pytest.raises(RuntimeError, match="zero source chunks"):
        await retrieve_indexed_document_chunks(
            vector_store=store,
            case_id="case1",
            session_id="session1",
            source_file_id="file1",
            top_k=10,
        )


@pytest.mark.asyncio
async def test_vector_retrieval_mode_is_rejected_until_embeddings_exist() -> None:
    store = RecordingVectorStore()
    with pytest.raises(ValueError, match="Vector/HNSW retrieval is not enabled"):
        await index_document_chunks_for_retrieval(
            vector_store=store,
            chunks=[_chunk()],
            retrieval_mode="vector",
            vector_dimension=384,
        )
