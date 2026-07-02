from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from translume_core.indexing.documents import (
    INDEX_DOCUMENT_CHUNKS,
    document_chunk_to_opensearch_doc,
)
from translume_core.indexing.index_specs import build_document_chunk_index_spec
from translume_core.indexing.retrieval_scope import (
    LEXICAL_RETRIEVAL_METHOD,
    require_lexical_retrieval_scope,
)
from translume_schemas.document import BoundingBox, DocumentChunk, RetrievedDocumentChunk


@dataclass(frozen=True)
class ChunkIndexingResult:
    """Result of early document chunk indexing.

    Attributes:
        indexed_count: Number of chunk documents submitted to OpenSearch.
        index_name: OpenSearch index that received chunk documents.
        retrieval_mode: Active retrieval mode.
        retrieval_method: Method label persisted with retrieved chunks.
    """

    indexed_count: int
    index_name: str = INDEX_DOCUMENT_CHUNKS
    retrieval_mode: str = "lexical"
    retrieval_method: str = LEXICAL_RETRIEVAL_METHOD


async def index_document_chunks_for_retrieval(
    *,
    vector_store: object,
    chunks: list[DocumentChunk],
    retrieval_mode: str = "lexical",
    vector_dimension: int | None = None,
) -> ChunkIndexingResult:
    """Index source document chunks before clinical artifact generation.

    Acceptance criteria:
        1. Ensures the document chunk index exists before indexing.
        2. Converts every provided chunk into an OpenSearch document.
        3. Submits real documents to the configured store.
        4. Does not fabricate embeddings; lexical/metadata indexing remains real.
        5. Fails if vector/HNSW retrieval is requested without a real embedding
           provider and indexing path.
        6. Propagates store failures to the caller.
        7. Does not mutate caller-owned chunks.
    """
    if not chunks:
        raise ValueError("cannot index zero document chunks for retrieval")
    scope = require_lexical_retrieval_scope(retrieval_mode)
    spec = build_document_chunk_index_spec(
        retrieval_mode=scope.mode,
        vector_dimension=vector_dimension,
    )
    await vector_store.ensure_index(spec["index_name"], spec["body"])
    documents = [
        document_chunk_to_opensearch_doc(chunk, retrieval_mode=scope.mode)
        for chunk in chunks
    ]
    await vector_store.index(INDEX_DOCUMENT_CHUNKS, documents, refresh="wait_for")
    return ChunkIndexingResult(
        indexed_count=len(documents),
        retrieval_mode=scope.mode,
        retrieval_method=scope.method,
    )


def build_document_chunk_retrieval_query(
    *,
    case_id: str,
    session_id: str,
    source_file_id: str,
    top_k: int,
    retrieval_mode: str = "lexical",
) -> dict[str, object]:
    """Build a metadata-grounded OpenSearch query for source chunks.

    Acceptance criteria:
        1. Query is scoped to case_id, session_id, and source_file_id.
        2. Query is lexical/metadata only and does not claim vector search.
        3. Query returns chunks in page/chunk order for deterministic extraction.
        4. Non-positive top_k raises ValueError.
        5. Vector/HNSW mode fails loudly until real embeddings are implemented.
        6. Function is pure.
    """
    if top_k <= 0:
        raise ValueError("top_k must be positive")
    require_lexical_retrieval_scope(retrieval_mode)
    return {
        "size": top_k,
        "query": {
            "bool": {
                "filter": [
                    {"term": {"case_id": case_id}},
                    {"term": {"session_id": session_id}},
                    {"term": {"source_file_id": source_file_id}},
                ],
                "must": [{"match_all": {}}],
            }
        },
        "sort": [
            {"page_start": {"order": "asc"}},
            {"chunk_id": {"order": "asc"}},
        ],
    }


async def retrieve_indexed_document_chunks(
    *,
    vector_store: object,
    case_id: str,
    session_id: str,
    source_file_id: str,
    top_k: int,
    retrieval_mode: str = "lexical",
) -> list[RetrievedDocumentChunk]:
    """Retrieve indexed source chunks from OpenSearch.

    Acceptance criteria:
        1. Reads from the real store search boundary.
        2. Returns retrieved chunks with score and retrieval method metadata.
        3. Fails explicitly when OpenSearch returns no chunks.
        4. Fails explicitly when returned documents cannot be converted to chunks.
        5. Does not use in-memory source chunks as a hidden substitute.
        6. Fails loudly if vector/HNSW mode is requested without embeddings.
    """
    scope = require_lexical_retrieval_scope(retrieval_mode)
    query = build_document_chunk_retrieval_query(
        case_id=case_id,
        session_id=session_id,
        source_file_id=source_file_id,
        top_k=top_k,
        retrieval_mode=scope.mode,
    )
    raw_results = await vector_store.search(INDEX_DOCUMENT_CHUNKS, query)
    retrieved = [
        opensearch_doc_to_retrieved_chunk(item, retrieval_method=scope.method)
        for item in raw_results
    ]
    if not retrieved:
        raise RuntimeError(
            "OpenSearch returned zero source chunks after early chunk indexing; "
            "clinical artifact generation is blocked because report extraction "
            "must be retrieval-grounded."
        )
    return retrieved


def opensearch_doc_to_retrieved_chunk(
    document: dict[str, Any],
    *,
    retrieval_method: str = LEXICAL_RETRIEVAL_METHOD,
) -> RetrievedDocumentChunk:
    """Convert an OpenSearch hit into a retrieved source chunk.

    Acceptance criteria:
        1. Preserves source-backed chunk fields.
        2. Preserves OpenSearch score if present.
        3. Marks retrieval_method as opensearch_metadata_lexical.
        4. Does not create or infer embeddings.
        5. Raises KeyError/ValueError when required fields are missing.
    """
    bbox_payload = document.get("bbox")
    bbox = BoundingBox.model_validate(bbox_payload) if isinstance(bbox_payload, dict) else None
    score = document.get("_score")
    return RetrievedDocumentChunk(
        chunk=DocumentChunk(
            chunk_id=str(document["chunk_id"]),
            case_id=str(document["case_id"]),
            session_id=str(document["session_id"]),
            source_file_id=str(document["source_file_id"]),
            report_type=str(document["report_type"]),
            page_start=int(document["page_start"]),
            page_end=int(document["page_end"]),
            section=str(document["section"]),
            chunk_type=str(document["chunk_type"]),
            source_text=str(document["source_text"]),
            source_block_ids=[str(item) for item in document["source_block_ids"]],
            bbox=bbox,
            needs_human_review=bool(document["needs_human_review"]),
        ),
        score=float(score) if isinstance(score, int | float) else None,
        retrieval_method=retrieval_method,
    )
