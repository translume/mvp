from __future__ import annotations

import os
from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from tooluniverse_service.local_tool_overrides import (
    build_local_tool_overrides,
    truthy,
)
from translume_adapters.errors import ProviderUnavailableError
from tooluniverse_service.vendor_runtime import (
    VendorRuntimeError,
    assert_remote_model_env_blocked,
)
from translume_adapters.tool_providers.tooluniverse_runtime import (
    REQUIRED_MVP_WORKFLOWS,
    ToolUniverseRuntime,
    ToolUniverseWorkflowError,
    load_workflow_catalog,
)
from translume_schemas.entities import NormalizedEntitySet
from translume_schemas.graph import GraphEvidenceArtifact


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Close the cached runtime and its driver during worker shutdown."""
    try:
        yield
    finally:
        reset_runtime_cache()


app = FastAPI(title="tooluniverse_service", lifespan=lifespan)


class WorkflowRequest(BaseModel):
    workflows: list[str]
    entities: dict[str, object]
    graph: dict[str, object]


@app.get("/health")
def health() -> JSONResponse:
    """Return ToolUniverse service readiness without executing scientific tools.

    Acceptance criteria:
        1. Imports the real vendored ToolUniverse package through the runtime.
        2. Validates the required MVP workflow catalog.
        3. Loads configured tool names without executing workflow calls.
        4. Reports missing vendor/config/tool failures explicitly.
        5. Does not fabricate readiness when configuration is incomplete.
    """
    try:
        report = _runtime().health_report()
    except (
        ValueError,
        ProviderUnavailableError,
        ToolUniverseWorkflowError,
    ) as error:
        return JSONResponse(
            status_code=503,
            content={
                "status": "degraded",
                "service": "tooluniverse_service",
                "runtime_ready": False,
                "required_workflows_configured": False,
                "reactome_local_enabled": truthy(
                    os.getenv("REACTOME_LOCAL_ENABLED")
                ),
                "reactome_graphdb_available": False,
                "remote_reactome_enabled": False,
                "error": (
                    f"{type(error).__name__}: {str(error)[:500]}"
                ),
            },
        )
    local_health = report.get("local_tool_health", {})
    reactome = (
        local_health.get("ReactomeContent_search", {})
        if isinstance(local_health, dict)
        else {}
    )
    ready = bool(report.get("runtime_ready"))
    payload = {
        "status": "ok" if ready else "degraded",
        "service": "tooluniverse_service",
        "vendor_path": str(_repo_path()),
        "workflow_config": str(_workflow_config_path()),
        "required_workflows_configured": not bool(
            report.get("missing_required_workflows")
        ),
        "reactome_local_enabled": (
            "ReactomeContent_search"
            in report.get("local_tool_overrides", [])
        ),
        "reactome_graphdb_available": bool(
            reactome.get("reactome_graphdb_available")
        ),
        "reactome_graphdb_database": reactome.get(
            "reactome_graphdb_database"
        ),
        "reactome_graphdb_configured_release": reactome.get(
            "reactome_graphdb_configured_release"
        ),
        "reactome_graphdb_actual_release": reactome.get(
            "reactome_graphdb_actual_release"
        ),
        "reactome_graphdb_release_matches": bool(
            reactome.get("reactome_graphdb_release_matches")
        ),
        "reactome_pathway_count": reactome.get("reactome_pathway_count"),
        "remote_reactome_enabled": False,
        **report,
    }
    return JSONResponse(status_code=200 if ready else 503, content=payload)


@app.post("/workflows")
async def workflows(request: WorkflowRequest) -> dict[str, object]:
    """Run governed ToolUniverse workflows through the real ToolUniverse SDK.

    Acceptance criteria:
        1. Blocks remote model-provider environment variables.
        2. Requires the real vendored ToolUniverse package.
        3. Requires every requested workflow to be explicitly configured.
        4. Executes only configured workflow steps and configured tool names.
        5. Normalizes real tool outputs to ToolRunArtifact objects.
        6. Does not synthesize evidence when tools/configuration are unavailable.
    """
    try:
        assert_remote_model_env_blocked()
        entities = NormalizedEntitySet.model_validate(request.entities)
        graph = GraphEvidenceArtifact.model_validate(request.graph)
        artifacts = await _runtime().run_workflows(
            workflows=request.workflows,
            entities=entities,
            graph=graph,
        )
    except (ValueError, VendorRuntimeError, ToolUniverseWorkflowError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return {"artifacts": [artifact.model_dump(mode="json") for artifact in artifacts]}


@app.get("/workflows/configured")
def configured_workflows() -> dict[str, object]:
    """Return configured workflow names without executing ToolUniverse tools."""
    try:
        catalog = load_workflow_catalog(_workflow_config_path())
    except ToolUniverseWorkflowError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return {
        "required_workflows": list(catalog.required_workflows),
        "configured_workflows": sorted(catalog.workflows),
        "required_workflows_configured": set(catalog.required_workflows).issubset(
            set(catalog.workflows)
        ),
    }


@lru_cache(maxsize=1)
def _runtime() -> ToolUniverseRuntime:
    return ToolUniverseRuntime(
        repo_path=_repo_path(),
        workflow_config_path=_workflow_config_path(),
        module_names=_module_names(),
        local_tool_overrides=build_local_tool_overrides(os.environ),
    )


def reset_runtime_cache() -> None:
    """Close and clear the worker-local runtime cache for shutdown/tests."""
    if _runtime.cache_info().currsize:
        _runtime().close()
    _runtime.cache_clear()


def _repo_path() -> Path:
    return Path(os.getenv("TOOLUNIVERSE_VENDOR_DIR", "/app/third_party/upstream/ToolUniverse"))


def _module_names() -> tuple[str, ...]:
    raw = os.getenv("TOOLUNIVERSE_MODULE_NAMES", "tooluniverse")
    return tuple(item.strip() for item in raw.split(",") if item.strip())


def _workflow_config_path() -> Path:
    return Path(
        os.getenv(
            "TOOLUNIVERSE_WORKFLOW_CONFIG",
            "/app/configs/local/tooluniverse_workflows.json",
        )
    )


def required_mvp_workflows() -> tuple[str, ...]:
    """Expose the required workflow tuple for diagnostics/tests."""
    return REQUIRED_MVP_WORKFLOWS
