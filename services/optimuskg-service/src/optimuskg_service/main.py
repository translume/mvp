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
        from translume_adapters.graph_providers.optimuskg_runtime import _import_optimuskg

        _import_optimuskg(config.repo_path)
        vendor_available = True
        error = None
    except OptimusKGRuntimeError as runtime_error:
        vendor_available = False
        error = str(runtime_error)
    return {
        "status": "ok",
        "service": "optimuskg_service",
        "vendor_path": str(config.repo_path),
        "vendor_available": vendor_available,
        "runtime": "optimuskg_python_client_get_file_polars_parquet",
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
        repo_path=Path(os.getenv("OPTIMUSKG_VENDOR_DIR", "/app/third_party/upstream/OptimusKG")),
        cache_dir=Path(cache_raw) if cache_raw else None,
        use_lcc=os.getenv("OPTIMUSKG_USE_LCC", "true").casefold() == "true",
        force_download=os.getenv("OPTIMUSKG_FORCE_DOWNLOAD", "false").casefold() == "true",
        max_edges=int(os.getenv("OPTIMUSKG_MAX_EDGES", "500")),
    )
