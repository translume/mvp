from __future__ import annotations

from dataclasses import dataclass

from translume_core.indexing.documents import review_packet_to_index_batches
from translume_core.indexing.index_specs import build_all_mvp_index_specs
from translume_core.indexing.retrieval_scope import require_lexical_retrieval_scope
from translume_schemas.export import ReviewPacketExport


@dataclass(frozen=True)
class PersistenceResult:
    """Summary of OpenSearch persistence work.

    Attributes:
        indexed_documents_by_index: Count of documents indexed by index name.
        retrieval_mode: Active retrieval mode for created indexes.
    """

    indexed_documents_by_index: dict[str, int]
    retrieval_mode: str = "lexical"


async def ensure_mvp_indexes(
    vector_store: object,
    *,
    retrieval_mode: str = "lexical",
    vector_dimension: int | None = None,
) -> None:
    """Ensure all MVP OpenSearch indexes exist.

    Acceptance criteria:
        1. Builds all MVP index specs deterministically.
        2. Calls the store for each index.
        3. Does not silently ignore OpenSearch failures.
        4. Network I/O remains isolated in the supplied store.
        5. Does not emit vector/HNSW mappings in lexical MVP mode.
        6. Fails loudly if vector/HNSW mode is requested without embeddings.
    """
    scope = require_lexical_retrieval_scope(retrieval_mode)
    for spec in build_all_mvp_index_specs(
        retrieval_mode=scope.mode,
        vector_dimension=vector_dimension,
    ):
        await vector_store.ensure_index(
            spec["index_name"],
            spec["body"],
        )


async def persist_review_packet_to_opensearch(
    packet: ReviewPacketExport,
    vector_store: object,
    *,
    retrieval_mode: str = "lexical",
    vector_dimension: int | None = None,
) -> PersistenceResult:
    """Persist a review packet into OpenSearch indexes.

    Acceptance criteria:
        1. Creates indexes before indexing documents.
        2. Indexes chunks, artifacts, graph evidence, tool outputs, Medea
           reasoning, claims, provenance, validation decisions, and ledger events.
        3. Empty batches are skipped.
        4. Any persistence failure propagates to the caller.
        5. The review packet is not mutated.
        6. Does not claim vector/HNSW retrieval unless real embeddings exist.
    """
    scope = require_lexical_retrieval_scope(retrieval_mode)
    await ensure_mvp_indexes(
        vector_store,
        retrieval_mode=scope.mode,
        vector_dimension=vector_dimension,
    )
    batches = review_packet_to_index_batches(packet)
    counts: dict[str, int] = {}
    for index_name, documents in batches.items():
        if not documents:
            counts[index_name] = 0
            continue
        await vector_store.index(index_name, documents)
        counts[index_name] = len(documents)
    return PersistenceResult(indexed_documents_by_index=counts, retrieval_mode=scope.mode)
