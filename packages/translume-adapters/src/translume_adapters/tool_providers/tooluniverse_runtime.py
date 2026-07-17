from __future__ import annotations

import importlib
import json
import re
import sys
from collections.abc import Mapping
from datetime import date, timedelta
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Protocol
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
    "therapy_context",
    "resistance_mechanism_context",
    "biomarker_retesting_context",
    "guideline_context",
    "clinical_trial_context",
    "lineage_transformation_context",
    "recent_therapy_agent_backfill_context",
)
MAX_TOOL_QUERY_TERMS = 8
MAX_GRAPH_QUERY_TERMS = 3
LITERATURE_GENE_BATCH_SIZE = 3
MAX_LITERATURE_QUERIES = 8
STEP_FAILURE_POLICIES = frozenset({"fail", "record_unavailable"})


class ToolUniverseWorkflowError(ProviderUnavailableError):
    """Raised when ToolUniverse cannot execute a real configured workflow."""


class LocalToolOverride(Protocol):
    """Generic exact-name local tool route owned by the governed runtime."""

    tool_name: str

    def run(
        self,
        *,
        arguments: Mapping[str, Any],
        context: Mapping[str, Any],
        use_cache: bool,
        validate: bool,
    ) -> Any: ...

    def health_report(self) -> Mapping[str, object]: ...

    def close(self) -> None: ...


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
        local_tool_overrides: Mapping[str, LocalToolOverride] | None = None,
    ) -> None:
        self._repo_path = repo_path
        self._workflow_config_path = workflow_config_path
        self._module_names = module_names
        self._local_tool_overrides = MappingProxyType(
            dict(local_tool_overrides or {})
        )
        validate_local_tool_overrides(self._local_tool_overrides)

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
            validate_override_names_in_catalog(
                catalog=catalog,
                overrides=self._local_tool_overrides,
            )
            required_names = workflow_tool_names(
                catalog,
                catalog.required_workflows,
            )
            vendor_names = vendor_tool_names(
                required_names,
                frozenset(self._local_tool_overrides),
            )
            engine = load_tooluniverse_engine(
                repo_path=self._repo_path,
                module_names=self._module_names,
                tool_names=vendor_names,
            )
            vendor_loaded = loaded_tool_names(engine)
            required_set = set(required_names)
            local_health = {
                name: handler.health_report()
                for name, handler in self._local_tool_overrides.items()
                if name in required_set
            }
            local_loaded = {
                name
                for name, report in local_health.items()
                if report.get("status") == "healthy"
            }
            loaded_union = vendor_loaded | local_loaded
            missing_tools = sorted(required_set - loaded_union)
            unhealthy_local = sorted(
                name
                for name, report in local_health.items()
                if report.get("status") != "healthy"
            )
            runtime_ready = not missing_tools and not unhealthy_local
            return {
                "vendor_available": True,
                "workflow_config_valid": True,
                "runtime_ready": runtime_ready,
                "configured_workflows": sorted(catalog.workflows),
                "required_workflows": list(catalog.required_workflows),
                "missing_required_workflows": [],
                "vendor_loaded_tools": sorted(vendor_loaded),
                "local_tool_overrides": sorted(self._local_tool_overrides),
                "local_tool_health": local_health,
                "loaded_tools": sorted(loaded_union),
                "missing_configured_tools": missing_tools,
                "error": None,
            }
        except ToolUniverseWorkflowError as error:
            return {
                "vendor_available": False,
                "workflow_config_valid": False,
                "runtime_ready": False,
                "configured_workflows": [],
                "required_workflows": list(REQUIRED_MVP_WORKFLOWS),
                "missing_required_workflows": list(REQUIRED_MVP_WORKFLOWS),
                "vendor_loaded_tools": [],
                "local_tool_overrides": sorted(self._local_tool_overrides),
                "local_tool_health": {},
                "loaded_tools": [],
                "missing_configured_tools": [],
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
        validate_override_names_in_catalog(
            catalog=catalog,
            overrides=self._local_tool_overrides,
        )
        requested = tuple(workflows)
        validate_requested_workflows(requested, catalog)
        configured_names = workflow_tool_names(catalog, requested)
        tool_names = vendor_tool_names(
            configured_names,
            frozenset(self._local_tool_overrides),
        )
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
                local_tool_overrides=self._local_tool_overrides,
            )
            for workflow in requested
        ]

    def close(self) -> None:
        """Close each distinct local override exactly once."""
        seen: set[int] = set()
        for handler in self._local_tool_overrides.values():
            identity = id(handler)
            if identity in seen:
                continue
            seen.add(identity)
            handler.close()


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
        6. Step failure policies and minimum-success requirements are valid.
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
        foreach_context = step.get("foreach_context")
        if foreach_context is not None and (
            not isinstance(foreach_context, str) or not foreach_context.strip()
        ):
            raise ToolUniverseWorkflowError(
                "ToolUniverse step foreach_context must be a non-empty string: "
                f"{workflow}[{index}]"
            )
        failure_policy = str(step.get("failure_policy", "fail")).strip()
        if failure_policy not in STEP_FAILURE_POLICIES:
            allowed = ", ".join(sorted(STEP_FAILURE_POLICIES))
            raise ToolUniverseWorkflowError(
                f"ToolUniverse step has invalid failure_policy: "
                f"{workflow}[{index}]: {failure_policy!r}; allowed: {allowed}"
            )
    minimum_successful_steps = spec.get("minimum_successful_steps", 0)
    if (
        not isinstance(minimum_successful_steps, int)
        or isinstance(minimum_successful_steps, bool)
        or minimum_successful_steps < 0
        or minimum_successful_steps > len(steps)
    ):
        raise ToolUniverseWorkflowError(
            "ToolUniverse workflow minimum_successful_steps must be an integer "
            f"between 0 and {len(steps)}: {workflow}"
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


def validate_local_tool_overrides(
    overrides: Mapping[str, LocalToolOverride],
) -> None:
    """Validate immutable exact-name local dispatch entries.

    Acceptance criteria:
        1. Names are non-empty and contain no surrounding whitespace.
        2. Mapping keys exactly match handler tool names.
        3. Validation performs no I/O and does not mutate the mapping.
    """
    for name, handler in overrides.items():
        if not name or name != name.strip():
            raise ToolUniverseWorkflowError(
                f"invalid local override name: {name!r}"
            )
        if getattr(handler, "tool_name", None) != name:
            raise ToolUniverseWorkflowError(
                "local override key does not match handler.tool_name: "
                f"{name!r}"
            )


def validate_override_names_in_catalog(
    *,
    catalog: ToolUniverseWorkflowCatalog,
    overrides: Mapping[str, LocalToolOverride],
) -> None:
    """Reject local override names absent from governed workflows."""
    configured = set(
        workflow_tool_names(catalog, tuple(catalog.workflows))
    )
    unknown = sorted(set(overrides) - configured)
    if unknown:
        raise ToolUniverseWorkflowError(
            "local override names are not present in governed workflows: "
            + ", ".join(unknown)
        )


def vendor_tool_names(
    configured_names: tuple[str, ...],
    override_names: frozenset[str],
) -> tuple[str, ...]:
    """Return configured names not routed through local overrides."""
    return tuple(
        name for name in configured_names if name not in override_names
    )


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
    if not tool_names:
        return engine
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
    local_tool_overrides: Mapping[str, LocalToolOverride] | None = None,
) -> ToolRunArtifact:
    """Execute one configured workflow and normalize real tool outputs.

    Acceptance criteria:
        1. Required step failures stop the workflow.
        2. Optional unavailable steps create explicit evidence and warnings.
        3. Configured minimum successful steps are enforced.
        4. Successful tool outputs remain normalized as evidence items.
    """
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
    warnings: list[str] = []
    successful_steps = 0
    unavailable_steps: list[str] = []
    for index, step in enumerate(spec["steps"]):
        invocation_contexts = expand_step_contexts(step, context)
        step_succeeded = False
        try:
            for batch_index, invocation_context in enumerate(invocation_contexts):
                result = run_workflow_step(
                    workflow=workflow,
                    step_index=index,
                    step=step,
                    engine=engine,
                    context=invocation_context,
                    local_tool_overrides=local_tool_overrides or {},
                )
                query = str(invocation_context.get("foreach_value", ""))
                evidence_items.extend(
                    result_to_evidence_items(
                        workflow,
                        index,
                        step,
                        result,
                        query=query,
                        batch_index=batch_index,
                    )
                )
                summary = summary_from_result(result)
                if summary:
                    summaries.append(summary)
                step_succeeded = True
        except ToolUniverseWorkflowError as error:
            if step_succeeded:
                warnings.append(
                    f"partial_query_failure:{step['tool_name']}:{batch_index}"
                )
                successful_steps += 1
                continue
            if (
                step_failure_policy(step) != "record_unavailable"
                or not is_external_source_unavailability(error)
            ):
                raise
            unavailable = unavailable_step_evidence_item(
                workflow=workflow,
                step_index=index,
                step=step,
                error=error,
            )
            evidence_items.append(unavailable)
            warnings.append(unavailable["warning"])
            summaries.append(unavailable["summary"])
            unavailable_steps.append(unavailable["tool_name"])
            continue
        if step_succeeded:
            successful_steps += 1
    required_successes = workflow_minimum_successful_steps(spec)
    if successful_steps < required_successes:
        unavailable = ", ".join(unavailable_steps) or "none"
        raise ToolUniverseWorkflowError(
            f"ToolUniverse workflow {workflow} requires at least "
            f"{required_successes} successful source step(s); got "
            f"{successful_steps}. Unavailable sources: {unavailable}"
        )
    artifact_id = f"artifact_{uuid5(NAMESPACE_URL, entities.artifact_id + workflow + ':tooluniverse').hex[:16]}"
    return ToolRunArtifact(
        artifact_id=artifact_id,
        workflow=workflow,
        input_entity_ids=[entity.entity_id for entity in entities.entities],
        summary="\n".join(summaries).strip(),
        evidence_items=(
            deduplicate_literature_evidence(evidence_items)
            if workflow == "literature_validation"
            else evidence_items
        ),
        warnings=warnings,
        requires_human_review=True,
    )


def step_failure_policy(step: dict[str, Any]) -> str:
    """Return a validated failure policy for one workflow step.

    Acceptance criteria:
        1. Missing policy defaults to fail.
        2. Returned policy is in STEP_FAILURE_POLICIES.
        3. Invalid policies raise ToolUniverseWorkflowError.
    """
    policy = str(step.get("failure_policy", "fail")).strip()
    if policy not in STEP_FAILURE_POLICIES:
        raise ToolUniverseWorkflowError(f"invalid ToolUniverse failure policy: {policy!r}")
    return policy


def workflow_minimum_successful_steps(spec: dict[str, Any]) -> int:
    """Return the minimum number of successful steps required by a workflow.

    Acceptance criteria:
        1. Missing configuration defaults to zero successful steps.
        2. Returned value is a nonnegative integer.
        3. Invalid configuration raises ToolUniverseWorkflowError.
    """
    value = spec.get("minimum_successful_steps", 0)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ToolUniverseWorkflowError(
            "ToolUniverse minimum_successful_steps must be a nonnegative integer"
        )
    return value


def unavailable_step_evidence_item(
    *,
    workflow: str,
    step_index: int,
    step: dict[str, Any],
    error: ToolUniverseWorkflowError,
) -> dict[str, str]:
    """Return explicit evidence that an optional external source was unavailable.

    Acceptance criteria:
        1. Preserves workflow, tool, source, status, and reason.
        2. Captures an HTTP status code when the provider exposes one.
        3. Does not fabricate scientific evidence.
    """
    tool_name = str(step["tool_name"])
    reason = str(error)
    status_code = external_http_status_code(reason)
    summary = f"{tool_name} unavailable: {reason}"
    warning = f"external_source_unavailable:{tool_name}:{status_code or 'unknown'}"
    return {
        "workflow": workflow,
        "tool_name": tool_name,
        "step_index": str(step_index),
        "status": "unavailable_external_source",
        "source": tool_name,
        "http_status": status_code or "unknown",
        "reason": reason,
        "summary": summary,
        "warning": warning,
    }


def is_external_source_unavailability(error: ToolUniverseWorkflowError) -> bool:
    """Return whether a workflow error represents an unavailable external source.

    Acceptance criteria:
        1. HTTP, timeout, and connection failures are treated as unavailable.
        2. Configuration and programming failures remain fatal.
        3. Same error message returns the same result.
    """
    message = str(error).casefold()
    markers = (
        "http error",
        "timed out",
        "timeout",
        "failed to connect",
        "connection error",
    )
    return any(marker in message for marker in markers)


def external_http_status_code(value: str) -> str | None:
    """Return the first three-digit HTTP status code in an error message.

    Acceptance criteria:
        1. Same input returns the same status code or None.
        2. Does not mutate caller-owned strings.
        3. Only standalone three-digit status codes are returned.
    """
    match = re.search(r"\b([1-5][0-9]{2})\b", value)
    return match.group(1) if match else None


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


def expand_step_contexts(
    step: dict[str, Any],
    context: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return immutable-style per-value contexts for a workflow step.

    Acceptance criteria:
        1. A step without foreach_context executes once with copied context.
        2. A foreach step executes once for every configured context value.
        3. Every expanded context exposes foreach_value.
        4. Caller-owned step and context mappings are not mutated.
    """
    foreach_key = step.get("foreach_context")
    if foreach_key is None:
        return [dict(context)]
    values = context.get(str(foreach_key))
    if not isinstance(values, list) or not values:
        raise ToolUniverseWorkflowError(
            "ToolUniverse foreach_context requires a non-empty list: "
            f"{foreach_key}"
        )
    return [{**context, "foreach_value": value} for value in values]


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
    local_tool_overrides: Mapping[str, LocalToolOverride] | None = None,
) -> Any:
    """Execute one step through an exact local route or the real engine."""
    validate_required_context(workflow, step_index, step, context)
    tool_name = str(step["tool_name"]).strip()
    arguments = render_arguments(step.get("arguments", {}), context)
    if bool(step.get("omit_empty", False)):
        arguments = omit_empty_arguments(arguments)
    overrides = local_tool_overrides or {}
    override = overrides.get(tool_name)
    if override is not None:
        try:
            result = override.run(
                arguments=arguments,
                context=context,
                use_cache=bool(step.get("use_cache", False)),
                validate=bool(step.get("validate", True)),
            )
        except (ValueError, ProviderUnavailableError) as error:
            raise ToolUniverseWorkflowError(
                "Local ToolUniverse override failed: "
                f"{workflow}[{step_index}] {tool_name}: {error}"
            ) from error
    else:
        function_call = {"name": tool_name, "arguments": arguments}
        runner = getattr(engine, "run_one_function", None)
        if runner is None:
            raise ToolUniverseWorkflowError(
                "ToolUniverse.run_one_function is unavailable"
            )
        try:
            result = runner(
                function_call,
                use_cache=bool(step.get("use_cache", False)),
                validate=bool(step.get("validate", True)),
            )
        except Exception as error:
            raise ToolUniverseWorkflowError(
                "ToolUniverse tool failed: "
                f"{workflow}[{step_index}] {tool_name}: {error}"
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
    """Build dynamic workflow arguments from entities and targeted graph slices.

    Acceptance criteria:
        1. Keeps unbounded entity and graph lists available for audit.
        2. Preserves first gene, disease, and variant values.
        3. Bounds generated ToolUniverse query strings deterministically.
        4. Prioritizes source entities before graph-expanded context.
        5. Exposes therapy-pressure, resistance-path, drug-target-biomarker,
           and biomarker-monitoring graph terms as distinct workflow inputs.
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

    therapy_graph_terms = subgraph_query_terms(graph, "therapy_pressure")
    therapy_graph_relations = subgraph_relation_terms(graph, "therapy_pressure")
    resistance_graph_terms = subgraph_query_terms(graph, "resistance_path")
    resistance_graph_relations = subgraph_relation_terms(graph, "resistance_path")
    drug_target_graph_terms = subgraph_query_terms(graph, "drug_target_biomarker")
    drug_target_graph_relations = subgraph_relation_terms(graph, "drug_target_biomarker")
    biomarker_graph_terms = subgraph_query_terms(graph, "biomarker_monitoring")
    biomarker_graph_relations = subgraph_relation_terms(graph, "biomarker_monitoring")

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
    literature_queries = build_literature_queries(
        diseases=diseases,
        genes=gene_terms,
        variants=variants,
    )
    pathway_terms = bounded_query_terms(
        priority_terms=gene_terms,
        secondary_terms=[*graph_nodes, *graph_relations],
    )
    local_pathway_terms = bounded_query_terms(
        priority_terms=[*genes, *diseases],
        secondary_terms=graph_nodes,
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
    therapy_terms = bounded_query_terms(
        priority_terms=[*diseases, *gene_terms, *variants, "therapy"],
        secondary_terms=graph_nodes,
    )
    resistance_terms = bounded_query_terms(
        priority_terms=[*diseases, *gene_terms, "resistance", "escape"],
        secondary_terms=graph_nodes,
    )
    retesting_terms = bounded_query_terms(
        priority_terms=[*diseases, *gene_terms, "ctDNA", "biomarker monitoring"],
        secondary_terms=graph_nodes,
    )
    guideline_terms = bounded_query_terms(
        priority_terms=[*diseases, *gene_terms, "guideline", "biomarker"],
        secondary_terms=[],
    )
    transformation_terms = bounded_query_terms(
        priority_terms=[*diseases, *gene_terms, "histologic transformation"],
        secondary_terms=graph_nodes,
    )
    therapy_pressure_terms = bounded_query_terms(
        priority_terms=[*diseases, *gene_terms, *variants, *therapy_graph_terms],
        secondary_terms=[*therapy_graph_relations, "therapy pressure", "selective pressure"],
    )
    resistance_path_terms = bounded_query_terms(
        priority_terms=[*diseases, *gene_terms, *resistance_graph_terms],
        secondary_terms=[*resistance_graph_relations, "resistance mechanism", "escape route"],
    )
    drug_target_biomarker_terms = bounded_query_terms(
        priority_terms=[*diseases, *gene_terms, *drug_target_graph_terms],
        secondary_terms=[*drug_target_graph_relations, "drug target biomarker"],
    )
    biomarker_monitoring_terms = bounded_query_terms(
        priority_terms=[*diseases, *gene_terms, *biomarker_graph_terms],
        secondary_terms=[*biomarker_graph_relations, "ctDNA", "retesting"],
    )
    lineage_transformation_terms = bounded_query_terms(
        priority_terms=[*diseases, *gene_terms, "histologic transformation"],
        secondary_terms=[*resistance_graph_terms, *graph_nodes],
    )
    recent_agent_terms = bounded_query_terms(
        priority_terms=[
            *diseases,
            *gene_terms,
            "trial agent",
            "targeted therapy",
            _recent_pubmed_date_filter(),
        ],
        secondary_terms=[*drug_target_graph_terms, *therapy_graph_terms],
    )
    recent_agent_trial_terms = bounded_query_terms(
        priority_terms=[*gene_terms, "targeted therapy", "trial agent"],
        secondary_terms=[*drug_target_graph_terms, *therapy_graph_terms],
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
        "graph_retrieval_modes": list(graph.retrieval_modes),
        "literature_query": join_terms(literature_terms),
        "literature_queries": literature_queries,
        "pathway_query": join_terms(pathway_terms),
        "pathway_genes": list(genes[:MAX_TOOL_QUERY_TERMS]),
        "pathway_terms": local_pathway_terms,
        "target_query": join_terms(target_terms),
        "variant_context_query": join_terms(variant_terms),
        "variant_query": join_terms(variant_terms),
        "trial_query": join_terms(trial_terms),
        "clinical_trial_query": join_terms(trial_terms),
        "therapy_query": join_terms(therapy_terms),
        "resistance_query": join_terms(resistance_terms),
        "biomarker_retesting_query": join_terms(retesting_terms),
        "guideline_query": join_terms(guideline_terms),
        "transformation_query": join_terms(transformation_terms),
        "therapy_pressure_query": join_terms(therapy_pressure_terms),
        "resistance_path_query": join_terms(resistance_path_terms),
        "drug_target_biomarker_query": join_terms(drug_target_biomarker_terms),
        "biomarker_monitoring_query": join_terms(biomarker_monitoring_terms),
        "lineage_transformation_query": join_terms(lineage_transformation_terms),
        "recent_therapy_agent_backfill_query": join_terms(recent_agent_terms),
        "recent_therapy_agent_trial_query": join_terms(recent_agent_trial_terms),
    }


def subgraph_query_terms(graph: GraphEvidenceArtifact, retrieval_mode: str) -> list[str]:
    """Return query terms for a targeted graph retrieval mode."""
    terms: list[str] = []
    for subgraph in graph.subgraphs:
        if subgraph.retrieval_mode == retrieval_mode:
            terms.extend(subgraph.query_terms)
    return unique_nonempty(terms)


def subgraph_relation_terms(graph: GraphEvidenceArtifact, retrieval_mode: str) -> list[str]:
    """Return relation terms attached to a targeted graph retrieval mode."""
    edge_ids: set[str] = set()
    for subgraph in graph.subgraphs:
        if subgraph.retrieval_mode == retrieval_mode:
            edge_ids.update(subgraph.edge_ids)
    if not edge_ids:
        return []
    return unique_nonempty(
        [edge.relation_type for edge in graph.edges if edge.edge_id in edge_ids]
    )


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


def build_literature_queries(
    *,
    diseases: list[str],
    genes: list[str],
    variants: list[str],
    gene_batch_size: int = LITERATURE_GENE_BATCH_SIZE,
    max_queries: int = MAX_LITERATURE_QUERIES,
) -> list[str]:
    """Return bounded disease-aware Boolean literature queries.

    Acceptance criteria:
        1. Joins genes within a batch with explicit OR operators.
        2. Joins disease and molecular clauses with an explicit AND operator.
        3. Preserves deterministic source order and removes duplicates.
        4. Produces gene-only or disease/variant fallbacks when needed.
        5. Does not mutate caller-owned term lists.

    Args:
        diseases: Normalized disease labels in source order.
        genes: Normalized gene and copy-number labels in source order.
        variants: Normalized variant labels in source order.
        gene_batch_size: Maximum genes in one OR clause.
        max_queries: Maximum number of returned provider queries.

    Returns:
        Ordered Boolean query strings.

    Raises:
        ValueError: If either configured bound is not positive.
    """
    if gene_batch_size <= 0 or max_queries <= 0:
        raise ValueError("literature query bounds must be positive")
    disease_terms = unique_nonempty(diseases)
    gene_terms = unique_nonempty(genes)[:MAX_TOOL_QUERY_TERMS]
    variant_terms = unique_nonempty(variants)
    gene_batches = partition_terms(gene_terms, gene_batch_size)
    queries: list[str] = []
    if gene_batches:
        disease_clauses = disease_terms or [""]
        for disease in disease_clauses:
            for batch in gene_batches:
                molecular_clause = render_boolean_clause(batch, "OR")
                clauses = [
                    clause
                    for clause in (
                        quote_literature_phrase(disease),
                        f"({molecular_clause})",
                    )
                    if clause and clause != "()"
                ]
                queries.append(" AND ".join(clauses))
    elif disease_terms or variant_terms:
        disease_clause = render_boolean_clause(disease_terms, "OR")
        variant_clause = render_boolean_clause(variant_terms, "OR")
        clauses = [
            f"({clause})"
            for clause in (disease_clause, variant_clause)
            if clause
        ]
        queries.append(" AND ".join(clauses))
    return unique_nonempty(queries)[:max_queries]


def partition_terms(values: list[str], size: int) -> list[list[str]]:
    """Return ordered copies of terms partitioned into fixed-size batches.

    Acceptance criteria:
        1. Preserves input order.
        2. Does not mutate the input list.
        3. Rejects non-positive batch sizes.
    """
    if size <= 0:
        raise ValueError("term batch size must be positive")
    return [list(values[index : index + size]) for index in range(0, len(values), size)]


def render_boolean_clause(values: list[str], operator: str) -> str:
    """Return an explicitly joined Boolean clause for literature providers.

    Acceptance criteria:
        1. Quotes multi-word phrases and preserves single tokens.
        2. Uses only AND or OR operators.
        3. Removes duplicate and empty terms without mutating inputs.
    """
    normalized_operator = operator.strip().upper()
    if normalized_operator not in {"AND", "OR"}:
        raise ValueError("literature Boolean operator must be AND or OR")
    return f" {normalized_operator} ".join(
        quote_literature_phrase(value) for value in unique_nonempty(values)
    )


def quote_literature_phrase(value: str) -> str:
    """Return a safely quoted multi-word literature-search term.

    Acceptance criteria:
        1. Empty values return an empty string.
        2. Multi-word values are enclosed in double quotes.
        3. Embedded double quotes are removed deterministically.
    """
    normalized = " ".join(str(value).replace('"', "").split())
    if not normalized:
        return ""
    return f'"{normalized}"' if " " in normalized else normalized


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
    *,
    query: str = "",
    batch_index: int = 0,
) -> list[dict[str, str]]:
    """Normalize ToolUniverse output into evidence items."""
    tool_name = str(step["tool_name"])
    if isinstance(result, list):
        items = [
            flatten_evidence_item(workflow, step_index, tool_name, item)
            for item in result
        ]
    else:
        items = [flatten_evidence_item(workflow, step_index, tool_name, result)]
    if not query:
        return items
    return [
        {**item, "query": query, "query_batch_index": str(batch_index)}
        for item in items
    ]


def deduplicate_literature_evidence(
    evidence_items: list[dict[str, str]],
) -> list[dict[str, str]]:
    """Return evidence deduplicated by provider and publication identifier.

    Acceptance criteria:
        1. Deduplicates repeated PMID, DOI, and stable ID values per provider.
        2. Preserves first-seen order and metadata.
        3. Preserves items without a stable publication identifier.
        4. Does not mutate caller-owned evidence dictionaries.
    """
    seen: set[tuple[str, str, str]] = set()
    result: list[dict[str, str]] = []
    identifier_fields = ("pmid", "doi", "id")
    for item in evidence_items:
        identifier = next(
            (
                (field, item[field].strip().casefold())
                for field in identifier_fields
                if item.get(field, "").strip()
            ),
            None,
        )
        if identifier is not None:
            key = (
                item.get("tool_name", "").casefold(),
                identifier[0],
                identifier[1],
            )
            if key in seen:
                continue
            seen.add(key)
        result.append(dict(item))
    return result


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




def _recent_pubmed_date_filter() -> str:
    """Return a PubMed-style last-18-month date filter for backfill queries."""
    start = date.today() - timedelta(days=548)
    return f"({start.isoformat()}[dp] : 3000[dp])"


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
