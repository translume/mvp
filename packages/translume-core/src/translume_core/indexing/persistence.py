from __future__ import annotations

from dataclasses import dataclass

from translume_core.indexing.documents import review_packet_to_index_batches
from translume_core.indexing.index_specs import build_all_mvp_index_specs
from translume_schemas.export import ReviewPacketExport


@dataclass(frozen=True)
class PersistenceResult:
    """Summary of OpenSearch persistence work.

    Attributes:
        indexed_documents_by_index: Count of documents indexed by index name.
    """

    indexed_documents_by_index: dict[str, int]


async def ensure_mvp_indexes(
    vector_store: object,
    *,
    vector_dimension: int,
) -> None:
    """Ensure all MVP OpenSearch indexes exist.

    Acceptance criteria:
        1. Builds all MVP index specs deterministically.
        2. Calls the vector store for each index.
        3. Does not silently ignore OpenSearch failures.
        4. Network I/O remains isolated in the supplied vector store.

    Args:
        vector_store: Store object with `ensure_index(index_name, body)`.
        vector_dimension: Dense-vector dimension for document chunks.
    """
    for spec in build_all_mvp_index_specs(vector_dimension):
        await vector_store.ensure_index(
            spec["index_name"],
            spec["body"],
        )


async def persist_review_packet_to_opensearch(
    packet: ReviewPacketExport,
    vector_store: object,
    *,
    vector_dimension: int,
) -> PersistenceResult:
    """Persist a review packet into OpenSearch indexes.

    Acceptance criteria:
        1. Creates indexes before indexing documents.
        2. Indexes chunks, artifacts, graph evidence, tool outputs, Medea
           reasoning, claims, provenance, validation decisions, and ledger events.
        3. Empty batches are skipped.
        4. Any persistence failure propagates to the caller.
        5. The review packet is not mutated.

    Args:
        packet: Review packet to persist.
        vector_store: Store object with `ensure_index` and `index` methods.
        vector_dimension: Dense-vector dimension for index specification.

    Returns:
        Persistence result with document counts by index.
    """
    await ensure_mvp_indexes(vector_store, vector_dimension=vector_dimension)
    batches = review_packet_to_index_batches(packet)
    counts: dict[str, int] = {}
    for index_name, documents in batches.items():
        if not documents:
            counts[index_name] = 0
            continue
        await vector_store.index(index_name, documents)
        counts[index_name] = len(documents)
    return PersistenceResult(indexed_documents_by_index=counts)
