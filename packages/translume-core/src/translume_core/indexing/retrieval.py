from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from translume_core.indexing.documents import (
    INDEX_DOCUMENT_CHUNKS,
    document_chunk_to_opensearch_doc,
)
from translume_core.indexing.index_specs import build_document_chunk_index_spec
from translume_schemas.document import BoundingBox, DocumentChunk, RetrievedDocumentChunk


@dataclass(frozen=True)
class ChunkIndexingResult:
    """Result of early document chunk indexing.

    Attributes:
        indexed_count: Number of chunk documents submitted to OpenSearch.
        index_name: OpenSearch index that received chunk documents.
    """

    indexed_count: int
    index_name: str = INDEX_DOCUMENT_CHUNKS


async def index_document_chunks_for_retrieval(
    *,
    vector_store: object,
    chunks: list[DocumentChunk],
    vector_dimension: int,
) -> ChunkIndexingResult:
    """Index source document chunks before clinical artifact generation.

    Acceptance criteria:
        1. Ensures the document chunk index exists before indexing.
        2. Converts every provided chunk into an OpenSearch document.
        3. Submits real documents to the configured vector store.
        4. Does not fabricate embeddings; lexical/metadata indexing remains real.
        5. Propagates vector-store failures to the caller.
        6. Does not mutate caller-owned chunks.

    Args:
        vector_store: OpenSearch-like store with ensure_index and index methods.
        chunks: Source-backed document chunks from document extraction.
        vector_dimension: Configured vector dimension for the index mapping.

    Returns:
        Count and index name for the indexed chunks.
    """
    if not chunks:
        raise ValueError("cannot index zero document chunks for retrieval")
    spec = build_document_chunk_index_spec(vector_dimension)
    await vector_store.ensure_index(spec["index_name"], spec["body"])
    documents = [document_chunk_to_opensearch_doc(chunk) for chunk in chunks]
    await vector_store.index(INDEX_DOCUMENT_CHUNKS, documents)
    return ChunkIndexingResult(indexed_count=len(documents))


def build_document_chunk_retrieval_query(
    *,
    case_id: str,
    session_id: str,
    source_file_id: str,
    top_k: int,
) -> dict[str, object]:
    """Build a metadata-grounded OpenSearch query for source chunks.

    Acceptance criteria:
        1. Query is scoped to case_id, session_id, and source_file_id.
        2. Query is lexical/metadata only and does not claim vector search.
        3. Query returns chunks in page/chunk order for deterministic extraction.
        4. Non-positive top_k raises ValueError.
        5. Function is pure.
    """
    if top_k <= 0:
        raise ValueError("top_k must be positive")
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
) -> list[RetrievedDocumentChunk]:
    """Retrieve indexed source chunks from OpenSearch.

    Acceptance criteria:
        1. Reads from the real vector store search boundary.
        2. Returns retrieved chunks with score and retrieval method metadata.
        3. Fails explicitly when OpenSearch returns no chunks.
        4. Fails explicitly when returned documents cannot be converted to chunks.
        5. Does not use in-memory source chunks as a hidden substitute.

    Args:
        vector_store: OpenSearch-like store with search method.
        case_id: Case identifier.
        session_id: Session identifier.
        source_file_id: Source file identifier.
        top_k: Maximum chunks to retrieve.

    Returns:
        Retrieved document chunks.
    """
    query = build_document_chunk_retrieval_query(
        case_id=case_id,
        session_id=session_id,
        source_file_id=source_file_id,
        top_k=top_k,
    )
    raw_results = await vector_store.search(INDEX_DOCUMENT_CHUNKS, query)
    retrieved = [opensearch_doc_to_retrieved_chunk(item) for item in raw_results]
    if not retrieved:
        raise RuntimeError(
            "OpenSearch returned zero source chunks after early chunk indexing; "
            "clinical artifact generation is blocked because report extraction "
            "must be retrieval-grounded."
        )
    return retrieved


def opensearch_doc_to_retrieved_chunk(document: dict[str, Any]) -> RetrievedDocumentChunk:
    """Convert an OpenSearch hit into a retrieved source chunk.

    Acceptance criteria:
        1. Preserves source text, source identifiers, page range, and chunk type.
        2. Preserves OpenSearch score when available.
        3. Marks retrieval_method as opensearch_metadata_lexical.
        4. Raises ValueError for missing required chunk fields.
        5. Function is pure.
    """
    required = [
        "chunk_id",
        "case_id",
        "session_id",
        "source_file_id",
        "report_type",
        "page_start",
        "page_end",
        "section",
        "chunk_type",
        "source_text",
        "source_block_ids",
        "needs_human_review",
    ]
    missing = [field for field in required if field not in document]
    if missing:
        raise ValueError(
            "OpenSearch chunk document missing required fields: " + ", ".join(missing)
        )
    bbox = None
    if isinstance(document.get("bbox"), dict):
        bbox = BoundingBox.model_validate(document["bbox"])
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
        retrieval_method="opensearch_metadata_lexical",
    )
