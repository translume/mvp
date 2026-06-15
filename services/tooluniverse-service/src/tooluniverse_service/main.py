from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from tooluniverse_service.vendor_runtime import (
    VendorRuntimeError,
    assert_remote_model_env_blocked,
    import_vendor_module,
    read_json_file,
)
from translume_schemas.entities import NormalizedEntitySet
from translume_schemas.graph import GraphEvidenceArtifact
from translume_schemas.tools import ToolRunArtifact

app = FastAPI(title="tooluniverse_service")


class WorkflowRequest(BaseModel):
    workflows: list[str]
    entities: dict[str, object]
    graph: dict[str, object]


@app.get("/health")
def health() -> dict[str, object]:
    """Return service health and ToolUniverse availability."""
    repo_path = _repo_path()
    try:
        _load_registry(repo_path)
        vendor_available = True
        error = None
    except VendorRuntimeError as runtime_error:
        vendor_available = False
        error = str(runtime_error)
    return {
        "status": "ok",
        "service": "tooluniverse_service",
        "vendor_path": str(repo_path),
        "workflow_config": str(_workflow_config_path()),
        "vendor_available": vendor_available,
        "error": error,
    }


@app.post("/workflows")
async def workflows(request: WorkflowRequest) -> dict[str, object]:
    """Run allow-listed ToolUniverse workflows through vendored ToolUniverse.

    Acceptance criteria:
        1. Requires the real ToolUniverse registry from the vendored repo.
        2. Requires explicit workflow configuration.
        3. Runs only requested workflows present in the configuration.
        4. Does not fabricate evidence summaries or tool results.
        5. Blocks remote model-provider environment variables.
    """
    try:
        assert_remote_model_env_blocked()
        entities = NormalizedEntitySet.model_validate(request.entities)
        graph = GraphEvidenceArtifact.model_validate(request.graph)
        registry = _load_registry(_repo_path())
        workflow_config = _load_workflow_config(_workflow_config_path())
        artifacts = [
            _run_workflow(workflow, workflow_config, registry, entities, graph)
            for workflow in request.workflows
        ]
    except (ValueError, VendorRuntimeError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return {"artifacts": [artifact.model_dump(mode="json") for artifact in artifacts]}


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


def _load_registry(repo_path: Path) -> dict[str, Any]:
    """Load ToolUniverse's real tool registry.

    Acceptance criteria:
        1. Imports ToolUniverse from the vendored repository.
        2. Uses ToolUniverse's `get_tool_registry` function when available.
        3. Raises if the registry is missing or not a dictionary.
    """
    import_vendor_module(repo_path, _module_names())
    registry_getter = None
    try:
        from tooluniverse.tool_registry import get_tool_registry

        registry_getter = get_tool_registry
    except ImportError:
        module = import_vendor_module(repo_path, _module_names())
        registry_getter = getattr(module, "get_tool_registry", None)
    if registry_getter is None:
        raise VendorRuntimeError("ToolUniverse get_tool_registry is unavailable")
    registry = registry_getter()
    if not isinstance(registry, dict):
        raise VendorRuntimeError("ToolUniverse registry must be a dictionary")
    return registry


def _load_workflow_config(path: Path) -> dict[str, Any]:
    payload = read_json_file(path)
    workflows = payload.get("workflows")
    if not isinstance(workflows, dict):
        raise VendorRuntimeError("ToolUniverse workflow config missing workflows object")
    return workflows


def _run_workflow(
    workflow: str,
    workflow_config: dict[str, Any],
    registry: dict[str, Any],
    entities: NormalizedEntitySet,
    graph: GraphEvidenceArtifact,
) -> ToolRunArtifact:
    spec = workflow_config.get(workflow)
    if not isinstance(spec, dict):
        raise VendorRuntimeError(f"ToolUniverse workflow is not configured: {workflow}")
    steps = spec.get("steps")
    if not isinstance(steps, list) or not steps:
        raise VendorRuntimeError(f"ToolUniverse workflow has no executable steps: {workflow}")
    evidence_items: list[dict[str, str]] = []
    summaries: list[str] = []
    for step in steps:
        if not isinstance(step, dict):
            raise VendorRuntimeError(f"invalid ToolUniverse step for workflow {workflow}")
        result = _run_step(step, registry, entities, graph)
        evidence_items.extend(_result_to_evidence_items(workflow, result))
        summaries.append(_summary_from_result(result))
    artifact_id = f"artifact_{uuid5(NAMESPACE_URL, entities.artifact_id + workflow + ':tooluniverse').hex[:16]}"
    return ToolRunArtifact(
        artifact_id=artifact_id,
        workflow=workflow,
        input_entity_ids=[entity.entity_id for entity in entities.entities],
        summary="\n".join(item for item in summaries if item).strip(),
        evidence_items=evidence_items,
        warnings=[],
        requires_human_review=True,
    )


def _run_step(
    step: dict[str, Any],
    registry: dict[str, Any],
    entities: NormalizedEntitySet,
    graph: GraphEvidenceArtifact,
) -> Any:
    tool_name = str(step.get("tool_name", "")).strip()
    if not tool_name:
        raise VendorRuntimeError("ToolUniverse step missing tool_name")
    tool_class = registry.get(tool_name)
    if tool_class is None:
        raise VendorRuntimeError(f"ToolUniverse tool not found in registry: {tool_name}")
    config = step.get("config", {})
    if not isinstance(config, dict):
        raise VendorRuntimeError(f"ToolUniverse tool config must be an object: {tool_name}")
    arguments_template = step.get("arguments", {})
    if not isinstance(arguments_template, dict):
        raise VendorRuntimeError(f"ToolUniverse tool arguments must be an object: {tool_name}")
    arguments = _render_arguments(arguments_template, entities, graph)
    try:
        tool = tool_class(config)
        return tool.run(arguments)
    except Exception as error:
        raise VendorRuntimeError(f"ToolUniverse tool failed: {tool_name}: {error}") from error


def _render_arguments(
    template: dict[str, Any],
    entities: NormalizedEntitySet,
    graph: GraphEvidenceArtifact,
) -> dict[str, Any]:
    context = _template_context(entities, graph)
    return {key: _render_value(value, context) for key, value in template.items()}


def _template_context(
    entities: NormalizedEntitySet,
    graph: GraphEvidenceArtifact,
) -> dict[str, Any]:
    groups: dict[str, list[str]] = {}
    for entity in entities.entities:
        groups.setdefault(entity.entity_type, []).append(entity.normalized_label)
    return {
        "entities": [entity.normalized_label for entity in entities.entities],
        "genes": groups.get("gene", []),
        "diseases": groups.get("disease", []),
        "variants": groups.get("variant", []),
        "first_gene": _first(groups.get("gene", [])),
        "first_disease": _first(groups.get("disease", [])),
        "first_variant": _first(groups.get("variant", [])),
        "copy_number_loss": groups.get("copy_number_loss", []),
        "copy_number_gain": groups.get("copy_number_gain", []),
        "graph_nodes": [node.label for node in graph.nodes],
        "graph_relations": [edge.relation_type for edge in graph.edges],
    }


def _render_value(value: Any, context: dict[str, Any]) -> Any:
    if isinstance(value, str) and value.startswith("$"):
        key = value[1:]
        if key not in context:
            raise VendorRuntimeError(f"unknown ToolUniverse argument placeholder: {value}")
        return context[key]
    if isinstance(value, list):
        return [_render_value(item, context) for item in value]
    if isinstance(value, dict):
        return {key: _render_value(item, context) for key, item in value.items()}
    return value


def _result_to_evidence_items(workflow: str, result: Any) -> list[dict[str, str]]:
    if isinstance(result, list):
        return [_flatten_evidence_item(workflow, item) for item in result]
    return [_flatten_evidence_item(workflow, result)]


def _flatten_evidence_item(workflow: str, item: Any) -> dict[str, str]:
    if isinstance(item, dict):
        flattened = {str(key): _to_text(value) for key, value in item.items()}
        flattened.setdefault("workflow", workflow)
        return flattened
    return {"workflow": workflow, "value": _to_text(item)}


def _summary_from_result(result: Any) -> str:
    if isinstance(result, dict):
        for key in ("summary", "description", "result", "message"):
            value = result.get(key)
            if value:
                return _to_text(value)
    return _to_text(result)[:1200]


def _to_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    return repr(value)


def _first(values: list[str]) -> str:
    return values[0] if values else ""
