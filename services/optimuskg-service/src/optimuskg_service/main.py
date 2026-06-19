from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from translume_adapters.graph_providers.optimuskg_runtime import (
    OptimusKGGraphConfig,
    OptimusKGRuntimeError,
    retrieve_optimuskg_graph_context,
)
from translume_schemas.entities import NormalizedEntitySet

app = FastAPI(title="optimuskg_service")


class ContextRequest(BaseModel):
    entities: dict[str, object]


@app.get("/health")
def health() -> dict[str, object]:
    """Return service health and real OptimusKG runtime availability."""
    config = _graph_config()
    try:
        # Import/configure only; do not load the graph during health checks.
        from translume_adapters.graph_providers.optimuskg_runtime import (
            _import_optimuskg,
        )

        _import_optimuskg(config.repo_path)
        vendor_available = True
        error = None
    except OptimusKGRuntimeError as runtime_error:
        vendor_available = False
        error = str(runtime_error)
    nodes_path, edges_path = _cached_parquet_paths(config)
    return {
        "status": "ok",
        "service": "optimuskg_service",
        "vendor_path": str(config.repo_path),
        "vendor_available": vendor_available,
        "runtime": "optimuskg_python_client_get_file_polars_parquet",
        "cache_dir": str(config.cache_dir) if config.cache_dir else None,
        "use_lcc": config.use_lcc,
        "data_available": nodes_path is not None and edges_path is not None,
        "nodes_path": str(nodes_path) if nodes_path else None,
        "edges_path": str(edges_path) if edges_path else None,
        "error": error,
    }


@app.post("/context")
async def context(request: ContextRequest) -> dict[str, object]:
    """Retrieve graph evidence from real OptimusKG parquet graph data.

    Acceptance criteria:
        1. Requires a real vendored OptimusKG package import.
        2. Uses OptimusKG's documented get_file parquet client path.
        3. Loads nodes/edges with Polars from OptimusKG parquet tables.
        4. Does not discover or read generic CSV/JSON edge-like files.
        5. Missing package/cache/data returns an explicit HTTP error.
    """
    try:
        entities = NormalizedEntitySet.model_validate(request.entities)
        artifact = retrieve_optimuskg_graph_context(entities, _graph_config())
    except (ValueError, OptimusKGRuntimeError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return artifact.model_dump(mode="json")


def _graph_config() -> OptimusKGGraphConfig:
    cache_raw = os.getenv("OPTIMUSKG_CACHE_DIR", "").strip()
    return OptimusKGGraphConfig(
        repo_path=Path(
            os.getenv("OPTIMUSKG_VENDOR_DIR", "/app/third_party/upstream/OptimusKG")
        ),
        cache_dir=Path(cache_raw) if cache_raw else None,
        use_lcc=os.getenv("OPTIMUSKG_USE_LCC", "true").casefold() == "true",
        force_download=os.getenv("OPTIMUSKG_FORCE_DOWNLOAD", "false").casefold()
        == "true",
        max_edges=int(os.getenv("OPTIMUSKG_MAX_EDGES", "500")),
    )


def _cached_parquet_paths(
    config: OptimusKGGraphConfig,
) -> tuple[Path | None, Path | None]:
    """Locate the exact cached graph pair without triggering a network download."""
    if config.cache_dir is None or not config.cache_dir.is_dir():
        return None, None
    names = (
        (
            "largest_connected_component_nodes.parquet",
            "largest_connected_component_edges.parquet",
        )
        if config.use_lcc
        else ("nodes.parquet", "edges.parquet")
    )
    pairs: list[tuple[Path, Path]] = []
    for nodes_path in config.cache_dir.rglob(names[0]):
        edges_path = nodes_path.parent / names[1]
        if (
            nodes_path.is_file()
            and nodes_path.stat().st_size > 0
            and edges_path.is_file()
            and edges_path.stat().st_size > 0
        ):
            pairs.append((nodes_path, edges_path))
    if not pairs:
        return None, None
    return max(
        pairs,
        key=lambda pair: max(
            pair[0].stat().st_mtime_ns,
            pair[1].stat().st_mtime_ns,
        ),
    )
