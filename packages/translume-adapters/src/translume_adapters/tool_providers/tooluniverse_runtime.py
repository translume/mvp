from __future__ import annotations

import importlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from translume_adapters.errors import ProviderUnavailableError
from translume_schemas.entities import NormalizedEntitySet
from translume_schemas.graph import GraphEvidenceArtifact
from translume_schemas.tools import ToolRunArtifact

REQUIRED_MVP_WORKFLOWS: tuple[str, ...] = (
    "literature_validation",
    "pathway_context",
    "target_context",
    "variant_context",
    "trial_context_review",
)
MAX_TOOL_QUERY_TERMS = 8
MAX_GRAPH_QUERY_TERMS = 3


class ToolUniverseWorkflowError(ProviderUnavailableError):
    """Raised when ToolUniverse cannot execute a real configured workflow."""


@dataclass(frozen=True)
class ToolUniverseWorkflowCatalog:
    """Validated ToolUniverse workflow configuration.

    Attributes:
        required_workflows: Workflow names that must be configured for the MVP.
        workflows: Mapping of workflow name to executable workflow spec.
    """

    required_workflows: tuple[str, ...]
    workflows: dict[str, dict[str, Any]]


class ToolUniverseRuntime:
    """Real ToolUniverse runtime wrapper used by service and direct adapters.

    This wrapper imports the vendored ToolUniverse repository, loads only the
    tools referenced by governed workflow configuration, and executes those
    tools through ToolUniverse's public ``ToolUniverse`` engine. It does not
    read precomputed evidence files, synthesize missing workflow output, or run
    arbitrary tool names outside the configured workflow catalog.
    """

    def __init__(
        self,
        *,
        repo_path: Path,
        workflow_config_path: Path,
        module_names: tuple[str, ...] = ("tooluniverse",),
    ) -> None:
        self._repo_path = repo_path
        self._workflow_config_path = workflow_config_path
        self._module_names = module_names

    def health_report(self) -> dict[str, object]:
        """Return real ToolUniverse availability and workflow coverage.

        Acceptance criteria:
            1. Imports the vendored ToolUniverse package.
            2. Validates the workflow catalog.
            3. Loads the exact tools required by the configured workflows.
            4. Does not execute any scientific tool calls.
            5. Reports missing dependencies/configuration instead of hiding them.
        """
        try:
            catalog = load_workflow_catalog(self._workflow_config_path)
            tool_names = workflow_tool_names(catalog, catalog.required_workflows)
            engine = load_tooluniverse_engine(
                repo_path=self._repo_path,
                module_names=self._module_names,
                tool_names=tool_names,
            )
            return {
                "vendor_available": True,
                "workflow_config_valid": True,
                "configured_workflows": sorted(catalog.workflows),
                "required_workflows": list(catalog.required_workflows),
                "loaded_tools": sorted(loaded_tool_names(engine)),
                "error": None,
            }
        except ToolUniverseWorkflowError as error:
            return {
                "vendor_available": False,
                "workflow_config_valid": False,
                "configured_workflows": [],
                "required_workflows": list(REQUIRED_MVP_WORKFLOWS),
                "loaded_tools": [],
                "error": str(error),
            }

    async def run_workflows(
        self,
        *,
        workflows: list[str],
        entities: NormalizedEntitySet,
        graph: GraphEvidenceArtifact,
    ) -> list[ToolRunArtifact]:
        """Execute governed ToolUniverse workflows.

        Acceptance criteria:
            1. Every requested workflow must be explicitly configured.
            2. Every configured workflow must map to real ToolUniverse tool names.
            3. ToolUniverse is loaded from the vendored repository path.
            4. Results are normalized to `ToolRunArtifact` only.
            5. Missing workflow context returns skipped artifacts.
            6. Missing configuration and tool execution failures fail loudly.
        """
        catalog = load_workflow_catalog(self._workflow_config_path)
        requested = tuple(workflows)
        validate_requested_workflows(requested, catalog)
        tool_names = workflow_tool_names(catalog, requested)
        engine = load_tooluniverse_engine(
            repo_path=self._repo_path,
            module_names=self._module_names,
            tool_names=tool_names,
        )
        return [
            run_workflow(
                workflow=workflow,
                catalog=catalog,
                engine=engine,
                entities=entities,
                graph=graph,
            )
            for workflow in requested
        ]


def add_tooluniverse_repo_to_path(repo_path: Path) -> None:
    """Add a real vendored ToolUniverse repo to import path.

    Acceptance criteria:
        1. Missing repositories fail loudly.
        2. Empty repositories fail loudly.
        3. Supports ToolUniverse's source layout at `src/`.
        4. Does not create synthetic packages.
    """
    if not repo_path.exists() or not repo_path.is_dir():
        raise ToolUniverseWorkflowError(f"vendored ToolUniverse repo missing: {repo_path}")
    if not any(repo_path.iterdir()):
        raise ToolUniverseWorkflowError(f"vendored ToolUniverse repo is empty: {repo_path}")
    candidates = [repo_path, repo_path / "src"]
    for candidate in candidates:
        if candidate.exists():
            value = str(candidate)
            if value not in sys.path:
                sys.path.insert(0, value)


def import_tooluniverse_module(repo_path: Path, module_names: tuple[str, ...]) -> Any:
    """Import ToolUniverse from the real vendored repo."""
    add_tooluniverse_repo_to_path(repo_path)
    errors: list[str] = []
    for module_name in module_names:
        try:
            return importlib.import_module(module_name)
        except ImportError as error:
            errors.append(f"{module_name}: {error}")
    raise ToolUniverseWorkflowError(
        f"no ToolUniverse module imported from {repo_path}: {'; '.join(errors)}"
    )


def load_workflow_catalog(path: Path) -> ToolUniverseWorkflowCatalog:
    """Load and validate governed ToolUniverse workflow configuration.

    Acceptance criteria:
        1. Config file must exist.
        2. Config must contain a workflows object.
        3. All MVP-required workflows must be configured.
        4. Every workflow must have one or more executable steps.
        5. Every step must name a ToolUniverse tool and argument template.
    """
    if not path.exists():
        raise ToolUniverseWorkflowError(f"ToolUniverse workflow config missing: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ToolUniverseWorkflowError(
            f"ToolUniverse workflow config is invalid JSON: {path}: {error}"
        ) from error
    if not isinstance(payload, dict):
        raise ToolUniverseWorkflowError("ToolUniverse workflow config must be a JSON object")
    workflows = payload.get("workflows")
    if not isinstance(workflows, dict):
        raise ToolUniverseWorkflowError("ToolUniverse workflow config missing workflows object")
    required_raw = payload.get("required_workflows", list(REQUIRED_MVP_WORKFLOWS))
    if not isinstance(required_raw, list) or not all(isinstance(item, str) for item in required_raw):
        raise ToolUniverseWorkflowError("ToolUniverse required_workflows must be a string list")
    required = tuple(item.strip() for item in required_raw if item.strip())
    missing_required = sorted(set(required) - set(workflows))
    if missing_required:
        raise ToolUniverseWorkflowError(
            "ToolUniverse workflow config missing required workflows: "
            + ", ".join(missing_required)
        )
    for workflow, spec in workflows.items():
        validate_workflow_spec(workflow, spec)
    return ToolUniverseWorkflowCatalog(required_workflows=required, workflows=workflows)


def validate_workflow_spec(workflow: str, spec: Any) -> None:
    """Validate one workflow spec without executing tools."""
    if not isinstance(spec, dict):
        raise ToolUniverseWorkflowError(f"ToolUniverse workflow spec must be an object: {workflow}")
    steps = spec.get("steps")
    if not isinstance(steps, list) or not steps:
        raise ToolUniverseWorkflowError(f"ToolUniverse workflow has no executable steps: {workflow}")
    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            raise ToolUniverseWorkflowError(f"ToolUniverse step must be an object: {workflow}[{index}]")
        tool_name = str(step.get("tool_name", "")).strip()
        if not tool_name:
            raise ToolUniverseWorkflowError(f"ToolUniverse step missing tool_name: {workflow}[{index}]")
        arguments = step.get("arguments", {})
        if not isinstance(arguments, dict):
            raise ToolUniverseWorkflowError(
                f"ToolUniverse step arguments must be an object: {workflow}[{index}]"
            )
        required_context = step.get("required_context", [])
        if not isinstance(required_context, list) or not all(isinstance(item, str) for item in required_context):
            raise ToolUniverseWorkflowError(
                f"ToolUniverse step required_context must be a string list: {workflow}[{index}]"
            )


def validate_requested_workflows(
    requested: tuple[str, ...],
    catalog: ToolUniverseWorkflowCatalog,
) -> None:
    """Reject arbitrary or unconfigured workflow execution."""
    if not requested:
        raise ToolUniverseWorkflowError("no ToolUniverse workflows requested")
    unknown = sorted(set(requested) - set(catalog.workflows))
    if unknown:
        raise ToolUniverseWorkflowError(
            "ToolUniverse workflow is not configured: " + ", ".join(unknown)
        )


def workflow_tool_names(
    catalog: ToolUniverseWorkflowCatalog,
    workflows: tuple[str, ...],
) -> tuple[str, ...]:
    """Return unique ToolUniverse tool names required for workflows."""
    names: list[str] = []
    for workflow in workflows:
        spec = catalog.workflows.get(workflow)
        if not isinstance(spec, dict):
            raise ToolUniverseWorkflowError(f"ToolUniverse workflow is not configured: {workflow}")
        for step in spec["steps"]:
            name = str(step["tool_name"]).strip()
            if name not in names:
                names.append(name)
    return tuple(names)


def load_tooluniverse_engine(
    *,
    repo_path: Path,
    module_names: tuple[str, ...],
    tool_names: tuple[str, ...],
) -> Any:
    """Load a real ToolUniverse engine with required tools.

    Acceptance criteria:
        1. Imports the ToolUniverse class from the vendored repo.
        2. Calls ToolUniverse.load_tools(include_tools=...).
        3. Fails if any configured tool is not loaded.
        4. Does not fall back to fake registry output.
    """
    module = import_tooluniverse_module(repo_path, module_names)
    engine_cls = getattr(module, "ToolUniverse", None)
    if engine_cls is None:
        raise ToolUniverseWorkflowError("ToolUniverse class is unavailable")
    engine = engine_cls()
    load_tools = getattr(engine, "load_tools", None)
    if load_tools is None:
        raise ToolUniverseWorkflowError("ToolUniverse.load_tools is unavailable")
    try:
        load_tools(include_tools=list(tool_names), quiet=True)
    except TypeError:
        load_tools(list(tool_names))
    loaded = loaded_tool_names(engine)
    missing = sorted(set(tool_names) - loaded)
    if missing:
        raise ToolUniverseWorkflowError(
            "ToolUniverse configured tools were not loaded: " + ", ".join(missing)
        )
    return engine


def loaded_tool_names(engine: Any) -> set[str]:
    """Return names loaded into a ToolUniverse engine."""
    all_tool_dict = getattr(engine, "all_tool_dict", None)
    if isinstance(all_tool_dict, dict):
        return set(all_tool_dict)
    all_tools = getattr(engine, "all_tools", None)
    if isinstance(all_tools, list):
        names = set()
        for item in all_tools:
            if isinstance(item, dict) and isinstance(item.get("name"), str):
                names.add(item["name"])
        return names
    return set()


def run_workflow(
    *,
    workflow: str,
    catalog: ToolUniverseWorkflowCatalog,
    engine: Any,
    entities: NormalizedEntitySet,
    graph: GraphEvidenceArtifact,
) -> ToolRunArtifact:
    """Execute one configured workflow and normalize real tool outputs."""
    spec = catalog.workflows[workflow]
    context = template_context(entities, graph)
    missing_context = missing_required_context(spec, context)
    if missing_context:
        return skipped_workflow_artifact(
            workflow=workflow,
            entities=entities,
            missing_context=missing_context,
        )
    evidence_items: list[dict[str, str]] = []
    summaries: list[str] = []
    for index, step in enumerate(spec["steps"]):
        result = run_workflow_step(
            workflow=workflow,
            step_index=index,
            step=step,
            engine=engine,
            context=context,
        )
        evidence_items.extend(result_to_evidence_items(workflow, index, step, result))
        summary = summary_from_result(result)
        if summary:
            summaries.append(summary)
    artifact_id = f"artifact_{uuid5(NAMESPACE_URL, entities.artifact_id + workflow + ':tooluniverse').hex[:16]}"
    return ToolRunArtifact(
        artifact_id=artifact_id,
        workflow=workflow,
        input_entity_ids=[entity.entity_id for entity in entities.entities],
        summary="\n".join(summaries).strip(),
        evidence_items=evidence_items,
        warnings=[],
        requires_human_review=True,
    )


def missing_required_context(
    workflow_spec: dict[str, Any],
    context: dict[str, Any],
) -> list[str]:
    """Return missing context keys required by a workflow spec.

    Acceptance criteria:
        1. Checks workflow-level `required_context` values.
        2. Checks step-level `required_context` values.
        3. Treats `None`, empty strings, and empty lists as missing.
        4. Returns keys in deterministic first-seen order without duplicates.

    Args:
        workflow_spec: Validated ToolUniverse workflow specification.
        context: Rendered dynamic context values.

    Returns:
        Missing context keys.
    """
    missing: list[str] = []
    for key in workflow_spec.get("required_context", []):
        if is_missing_context_value(context.get(key)) and key not in missing:
            missing.append(key)
    for step in workflow_spec.get("steps", []):
        for key in step.get("required_context", []):
            if is_missing_context_value(context.get(key)) and key not in missing:
                missing.append(key)
    return missing


def is_missing_context_value(value: Any) -> bool:
    """Return whether a ToolUniverse context value is missing.

    Acceptance criteria:
        1. `None` is missing.
        2. Empty strings are missing.
        3. Empty lists are missing.
        4. Falsey scalar values such as `0` and `False` are preserved.
    """
    return value is None or value == "" or value == []


def skipped_workflow_artifact(
    *,
    workflow: str,
    entities: NormalizedEntitySet,
    missing_context: list[str],
) -> ToolRunArtifact:
    """Return a reviewable artifact for a skipped ToolUniverse workflow.

    Acceptance criteria:
        1. Artifact ID is deterministic for entity set and workflow.
        2. Summary states that required context was missing.
        3. Evidence items do not claim external tool execution.
        4. Requires human review.

    Args:
        workflow: Workflow name that could not execute.
        entities: Normalized entity set used to derive the workflow context.
        missing_context: Missing context keys.

    Returns:
        Tool run artifact documenting the skipped workflow.
    """
    missing = ", ".join(missing_context)
    artifact_id = (
        f"artifact_{uuid5(NAMESPACE_URL, entities.artifact_id + workflow + ':tooluniverse').hex[:16]}"
    )
    return ToolRunArtifact(
        artifact_id=artifact_id,
        workflow=workflow,
        input_entity_ids=[entity.entity_id for entity in entities.entities],
        summary=(
            "ToolUniverse workflow skipped because required context is missing: "
            f"{missing}."
        ),
        evidence_items=[
            {
                "workflow": workflow,
                "status": "skipped_missing_context",
                "missing_context": missing,
            }
        ],
        warnings=[f"missing_required_context:{missing}"],
        requires_human_review=True,
    )


def run_workflow_step(
    *,
    workflow: str,
    step_index: int,
    step: dict[str, Any],
    engine: Any,
    context: dict[str, Any],
) -> Any:
    """Execute one ToolUniverse step through the real engine."""
    validate_required_context(workflow, step_index, step, context)
    tool_name = str(step["tool_name"]).strip()
    arguments = render_arguments(step.get("arguments", {}), context)
    if bool(step.get("omit_empty", False)):
        arguments = omit_empty_arguments(arguments)
    function_call = {"name": tool_name, "arguments": arguments}
    runner = getattr(engine, "run_one_function", None)
    if runner is None:
        raise ToolUniverseWorkflowError("ToolUniverse.run_one_function is unavailable")
    try:
        result = runner(
            function_call,
            use_cache=bool(step.get("use_cache", False)),
            validate=bool(step.get("validate", True)),
        )
    except Exception as error:
        raise ToolUniverseWorkflowError(
            f"ToolUniverse tool failed: {workflow}[{step_index}] {tool_name}: {error}"
        ) from error
    reject_tool_error_result(workflow, step_index, tool_name, result)
    return result


def validate_required_context(
    workflow: str,
    step_index: int,
    step: dict[str, Any],
    context: dict[str, Any],
) -> None:
    """Ensure a configured workflow has real input values before tool execution."""
    for key in step.get("required_context", []):
        value = context.get(key)
        if is_missing_context_value(value):
            raise ToolUniverseWorkflowError(
                f"ToolUniverse workflow {workflow}[{step_index}] requires non-empty context: {key}"
            )


def template_context(
    entities: NormalizedEntitySet,
    graph: GraphEvidenceArtifact,
) -> dict[str, Any]:
    """Build dynamic workflow arguments from normalized entities and graph evidence.

    Acceptance criteria:
        1. Keeps unbounded entity and graph lists available for audit.
        2. Preserves first gene, disease, and variant values.
        3. Bounds generated ToolUniverse query strings deterministically.
        4. Prioritizes source entities before graph-expanded context.
    """
    groups: dict[str, list[str]] = {}
    for entity in entities.entities:
        groups.setdefault(entity.entity_type, []).append(entity.normalized_label)
    genes = unique_nonempty(groups.get("gene", []))
    diseases = unique_nonempty(groups.get("disease", []))
    variants = unique_nonempty(groups.get("variant", []))
    graph_nodes = unique_nonempty([node.label for node in graph.nodes])
    graph_relations = unique_nonempty([edge.relation_type for edge in graph.edges])
    copy_number_loss = unique_nonempty(groups.get("copy_number_loss", []))
    copy_number_gain = unique_nonempty(groups.get("copy_number_gain", []))
    gene_terms = unique_nonempty([*genes, *copy_number_loss, *copy_number_gain])
    literature_terms = bounded_query_terms(
        priority_terms=[
            *diseases,
            *genes,
            *variants,
            *copy_number_loss,
            *copy_number_gain,
        ],
        secondary_terms=graph_nodes,
    )
    pathway_terms = bounded_query_terms(
        priority_terms=gene_terms,
        secondary_terms=[*graph_nodes, *graph_relations],
    )
    target_terms = bounded_query_terms(
        priority_terms=[*diseases, *gene_terms],
        secondary_terms=graph_nodes,
    )
    variant_terms = bounded_query_terms(
        priority_terms=[*genes, *variants, *diseases],
        secondary_terms=[],
    )
    trial_terms = bounded_query_terms(
        priority_terms=[*diseases, *gene_terms],
        secondary_terms=[],
    )
    return {
        "entities": unique_nonempty([entity.normalized_label for entity in entities.entities]),
        "genes": genes,
        "diseases": diseases,
        "variants": variants,
        "first_gene": first(gene_terms),
        "first_disease": first(diseases),
        "first_variant": first(variants),
        "copy_number_loss": copy_number_loss,
        "copy_number_gain": copy_number_gain,
        "graph_nodes": graph_nodes,
        "graph_relations": graph_relations,
        "literature_query": join_terms(literature_terms),
        "pathway_query": join_terms(pathway_terms),
        "target_query": join_terms(target_terms),
        "variant_context_query": join_terms(variant_terms),
        "variant_query": join_terms(variant_terms),
        "trial_query": join_terms(trial_terms),
        "clinical_trial_query": join_terms(trial_terms),
    }


def bounded_query_terms(
    *,
    priority_terms: list[str],
    secondary_terms: list[str],
    max_terms: int = MAX_TOOL_QUERY_TERMS,
    max_secondary_terms: int = MAX_GRAPH_QUERY_TERMS,
) -> list[str]:
    """Return deterministic bounded terms for external tool queries.

    Acceptance criteria:
        1. Preserves priority terms before secondary terms.
        2. Limits secondary terms so graph expansion cannot dominate queries.
        3. Removes duplicates case-insensitively.
        4. Does not mutate caller-owned lists.

    Args:
        priority_terms: Source-derived terms such as disease, gene, and variant.
        secondary_terms: Expansion terms such as graph node labels.
        max_terms: Maximum returned terms.
        max_secondary_terms: Maximum secondary terms considered.

    Returns:
        Ordered, deduplicated, bounded terms.

    Raises:
        ValueError: If limits are negative.
    """
    if max_terms < 0 or max_secondary_terms < 0:
        raise ValueError("query term limits must be non-negative")
    candidates = [
        *priority_terms,
        *unique_nonempty(secondary_terms)[:max_secondary_terms],
    ]
    return unique_nonempty(candidates)[:max_terms]


def omit_empty_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    """Remove empty optional arguments for ToolUniverse tools.

    Acceptance criteria:
        1. Removes only empty strings, empty lists, empty dictionaries, and None.
        2. Preserves falsey but meaningful scalar values such as 0 and False.
        3. Does not mutate the caller-owned argument mapping.
    """
    return {
        key: value
        for key, value in arguments.items()
        if value is not None and value != "" and value != [] and value != {}
    }


def render_arguments(template: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """Render configured ToolUniverse arguments from dynamic context."""
    return {key: render_value(value, context) for key, value in template.items()}


def render_value(value: Any, context: dict[str, Any]) -> Any:
    if isinstance(value, str) and value.startswith("$"):
        key = value[1:]
        if key not in context:
            raise ToolUniverseWorkflowError(f"unknown ToolUniverse argument placeholder: {value}")
        return context[key]
    if isinstance(value, list):
        return [render_value(item, context) for item in value]
    if isinstance(value, dict):
        return {key: render_value(item, context) for key, item in value.items()}
    return value


def reject_tool_error_result(
    workflow: str,
    step_index: int,
    tool_name: str,
    result: Any,
) -> None:
    """Fail when ToolUniverse returns an error-shaped result."""
    if isinstance(result, dict):
        status = str(result.get("status", "")).casefold()
        if status in {"error", "failed", "failure"} or "error" in result:
            raise ToolUniverseWorkflowError(
                f"ToolUniverse tool returned error: {workflow}[{step_index}] {tool_name}: {result}"
            )
    if isinstance(result, str) and result.strip().casefold().startswith(("error", "toolvalidationerror")):
        raise ToolUniverseWorkflowError(
            f"ToolUniverse tool returned error text: {workflow}[{step_index}] {tool_name}: {result[:500]}"
        )


def result_to_evidence_items(
    workflow: str,
    step_index: int,
    step: dict[str, Any],
    result: Any,
) -> list[dict[str, str]]:
    """Normalize ToolUniverse output into evidence items."""
    tool_name = str(step["tool_name"])
    if isinstance(result, list):
        return [flatten_evidence_item(workflow, step_index, tool_name, item) for item in result]
    return [flatten_evidence_item(workflow, step_index, tool_name, result)]


def flatten_evidence_item(
    workflow: str,
    step_index: int,
    tool_name: str,
    item: Any,
) -> dict[str, str]:
    if isinstance(item, dict):
        flattened = {str(key): to_text(value) for key, value in item.items()}
    else:
        flattened = {"value": to_text(item)}
    flattened.setdefault("workflow", workflow)
    flattened.setdefault("tool_name", tool_name)
    flattened.setdefault("step_index", str(step_index))
    return flattened


def summary_from_result(result: Any) -> str:
    if isinstance(result, dict):
        for key in ("summary", "description", "result", "message", "title"):
            value = result.get(key)
            if value:
                return to_text(value)
    if isinstance(result, list):
        return "\n".join(summary_from_result(item) for item in result[:5]).strip()
    return to_text(result)[:1200]


def to_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    except TypeError:
        return repr(value)


def unique_nonempty(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


def join_terms(values: list[str]) -> str:
    return " ".join(unique_nonempty(values)).strip()


def first(values: list[str]) -> str:
    return values[0] if values else ""
