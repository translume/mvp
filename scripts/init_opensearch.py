from __future__ import annotations

import asyncio
import os

from translume_clients.opensearch import OpenSearchClientConfig, OpenSearchVectorStore
from translume_core.indexing.persistence import ensure_mvp_indexes


async def _main() -> None:
    base_url = os.getenv("OPENSEARCH_URL", "http://localhost:9200")
    timeout_seconds = float(os.getenv("OPENSEARCH_TIMEOUT_SECONDS", "30"))
    retrieval_mode = os.getenv("TRANSLUME_RETRIEVAL_MODE", "lexical")
    vector_dimension_raw = os.getenv("TRANSLUME_VECTOR_DIMENSION", "").strip()
    vector_dimension = int(vector_dimension_raw) if vector_dimension_raw else None
    store = OpenSearchVectorStore(
        OpenSearchClientConfig(
            base_url=base_url,
            timeout_seconds=timeout_seconds,
        )
    )
    await ensure_mvp_indexes(
        store,
        retrieval_mode=retrieval_mode,
        vector_dimension=vector_dimension,
    )
    print(f"OpenSearch MVP indexes ensured at {base_url} using retrieval_mode={retrieval_mode}")


def main() -> int:
    asyncio.run(_main())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
