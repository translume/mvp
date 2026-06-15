from __future__ import annotations

import asyncio
import os

from translume_clients.opensearch import OpenSearchClientConfig, OpenSearchVectorStore
from translume_core.indexing.persistence import ensure_mvp_indexes


async def _main() -> None:
    base_url = os.getenv("OPENSEARCH_URL", "http://localhost:9200")
    timeout_seconds = float(os.getenv("OPENSEARCH_TIMEOUT_SECONDS", "30"))
    vector_dimension = int(os.getenv("TRANSLUME_VECTOR_DIMENSION", "384"))
    store = OpenSearchVectorStore(
        OpenSearchClientConfig(
            base_url=base_url,
            timeout_seconds=timeout_seconds,
        )
    )
    await ensure_mvp_indexes(store, vector_dimension=vector_dimension)
    print(f"OpenSearch MVP indexes ensured at {base_url}")


def main() -> int:
    asyncio.run(_main())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
