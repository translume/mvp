from __future__ import annotations

from dataclasses import dataclass


class RetrievalScopeError(ValueError):
    """Raised when retrieval configuration would overclaim unsupported behavior."""


LEXICAL_RETRIEVAL_MODE = "lexical"
LEXICAL_RETRIEVAL_METHOD = "opensearch_metadata_lexical"
UNSUPPORTED_VECTOR_RETRIEVAL_MODES = frozenset({"vector", "hybrid", "hnsw", "knn"})


@dataclass(frozen=True)
class RetrievalScope:
    """Describe the active OpenSearch retrieval behavior.

    Acceptance criteria:
        1. `mode` names the configured retrieval scope.
        2. `method` is written into retrieved chunks for auditability.
        3. `uses_embeddings` is false for MVP lexical retrieval.
        4. No unsupported vector/HNSW behavior is represented as active.
    """

    mode: str
    method: str
    uses_embeddings: bool


def normalize_retrieval_mode(value: str | None) -> str:
    """Normalize and validate a retrieval mode string.

    Acceptance criteria:
        1. Blank values resolve to lexical retrieval.
        2. Lexical retrieval is accepted.
        3. Vector/HNSW/hybrid modes fail loudly because no real embedding
           generation path exists in the production workflow yet.
        4. Unknown modes fail loudly.
        5. Function is pure.
    """
    mode = (value or LEXICAL_RETRIEVAL_MODE).strip().casefold()
    if not mode:
        mode = LEXICAL_RETRIEVAL_MODE
    if mode == LEXICAL_RETRIEVAL_MODE:
        return mode
    if mode in UNSUPPORTED_VECTOR_RETRIEVAL_MODES:
        raise RetrievalScopeError(
            "Vector/HNSW retrieval is not enabled in this MVP because no real "
            "local embedding generation and indexing path is configured. Set "
            "TRANSLUME_RETRIEVAL_MODE=lexical or implement a real embedding "
            "provider before enabling vector retrieval."
        )
    raise RetrievalScopeError(
        f"unsupported retrieval mode: {value!r}; supported MVP mode is 'lexical'"
    )


def build_retrieval_scope(value: str | None = None) -> RetrievalScope:
    """Return the active retrieval scope.

    Acceptance criteria:
        1. Returns a lexical scope for the current MVP.
        2. Fails loudly for vector/HNSW/hybrid modes.
        3. Does not create placeholder embedding behavior.
    """
    mode = normalize_retrieval_mode(value)
    return RetrievalScope(
        mode=mode,
        method=LEXICAL_RETRIEVAL_METHOD,
        uses_embeddings=False,
    )


def require_lexical_retrieval_scope(value: str | None = None) -> RetrievalScope:
    """Return lexical retrieval scope or raise if another mode is requested."""
    return build_retrieval_scope(value)
