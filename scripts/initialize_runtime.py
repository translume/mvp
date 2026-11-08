"""Provision real reference data and persistence inside the setup container."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from download_mims_data import (
    download_medeadb,
    download_optimuskg,
    inspect_optimuskg_cache,
    validate_optimuskg_parquet,
)
from translume_clients.opensearch import OpenSearchClientConfig, OpenSearchVectorStore
from translume_clients.postgres import PostgresClientConfig, PostgresLedgerStore
from translume_core.indexing.persistence import ensure_mvp_indexes
from translume_core.vendor.packaged import require_packaged_vendor_sources

ROOT = Path(__file__).resolve().parents[1]


async def initialize_persistence() -> None:
    """Create the real Postgres schema and lexical OpenSearch indexes.

    Acceptance criteria:
        1. Initialization is repeatable and preserves existing patient records.
        2. A required persistence failure stops setup with a nonzero exit.
    """
    postgres = PostgresLedgerStore(PostgresClientConfig(dsn=os.environ["POSTGRES_DSN"]))
    search = OpenSearchVectorStore(
        OpenSearchClientConfig(base_url=os.environ["OPENSEARCH_URL"])
    )
    await postgres.ensure_schema()
    await ensure_mvp_indexes(search, retrieval_mode="lexical", vector_dimension=None)


def main() -> int:
    """Download actual source data, validate it, then initialize persistence.

    Acceptance criteria:
        1. Only active DepMap data and the official OptimusKG pair are fetched.
        2. Existing complete caches and database contents are preserved.
        3. Errors are not caught and converted into successful readiness.
        4. Setup needs no GPU, model weights, host Python, Git or make.
    """
    require_packaged_vendor_sources(ROOT)
    medeadb = Path(os.environ["MEDEADB_PATH"])
    graph_cache = Path(os.environ["OPTIMUSKG_CACHE_DIR"])
    for name in ("TRANSLUME_STORAGE_ROOT", "TRANSLUME_AUDIT_ROOT"):
        path = Path(os.environ[name])
        path.mkdir(parents=True, exist_ok=True)
        if os.getuid() == 0:
            os.chown(path, 1000, 1000)
    print("Downloading/verifying official MedeaDB DepMap correlation data", flush=True)
    download_medeadb(medeadb, max_workers=3)
    print("Downloading/verifying official OptimusKG graph tables", flush=True)
    graph = inspect_optimuskg_cache(graph_cache, use_lcc=True)
    if not graph.available:
        graph = download_optimuskg(
            ROOT / "third_party/upstream/OptimusKG", graph_cache, use_lcc=True
        )
    if not graph.nodes_path or not graph.edges_path:
        raise RuntimeError("OptimusKG did not provide both required graph tables")
    validate_optimuskg_parquet(Path(graph.nodes_path), Path(graph.edges_path))
    if os.getuid() == 0:
        for path in (graph_cache, *graph_cache.rglob("*")):
            if not path.is_symlink():
                os.chown(path, 1000, 1000)
    asyncio.run(initialize_persistence())
    print("Reference data, Postgres schema and lexical indexes are ready", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
