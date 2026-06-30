from __future__ import annotations

import asyncio
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from medea_service.database_runtime import (
    MedeaDatabaseError,
    MedeaDBEvidence,
    MedeaDBStatus,
    collect_medeadb_evidence,
    database_required,
    depmap_correlation,
    evidence_prompt_text,
    inspect_medeadb,
    require_medeadb,
    validate_medeadb_runtime,
)
from medea_service.local_runtime import (
    LocalMedeaRoutingConfig,
    build_local_medea_routing_config,
    configure_and_patch_medea_for_local_vllm,
)
from medea_service.vendor_runtime import VendorRuntimeError, import_vendor_module
from translume_schemas.evidence import EvidenceContextBundle
from translume_schemas.medea import MedeaReasoningArtifact

app = FastAPI(title="medea_service")
_DEFAULT_LITERATURE_MAX_EXEC_STEPS = 6
_UNUSABLE_REASONING_MARKERS = (
    "Action parameter missing or not match with the action",
    "Expected format:",
    "Expcted format:",
    "TaskPackage",
)


class ReasonRequest(BaseModel):
    context: dict[str, object]


class DepMapCorrelationRequest(BaseModel):
    gene_a: str
    gene_b: str


@app.get("/health")
def health() -> dict[str, object]:
    """Return literature-runtime, local-model, and MedeaDB availability."""
    repo_path = _repo_path()
    try:
        import_vendor_module(repo_path, _module_names())
        vendor_available = True
        vendor_error = None
    except VendorRuntimeError as runtime_error:
        vendor_available = False
        vendor_error = str(runtime_error)
    try:
        routing = build_local_medea_routing_config(os.environ)
        local_model_configured = True
        remote_provider_blocked = True
        routing_error = None
        local_model_base_url = routing.vllm_base_url
        local_model_name = routing.model_name
    except VendorRuntimeError as runtime_error:
        local_model_configured = False
        remote_provider_blocked = False
        routing_error = str(runtime_error)
        local_model_base_url = None
        local_model_name = None
    database = inspect_medeadb()
    return {
        "status": "ok",
        "service": "medea_service",
        "vendor_path": str(repo_path),
        "vendor_available": vendor_available,
        "literature_reasoning_available": vendor_available,
        "local_model_configured": local_model_configured,
        "remote_provider_blocked": remote_provider_blocked,
        "local_model_base_url": local_model_base_url,
        "local_model_name": local_model_name,
        "database_required": database_required(),
        "database_available": database.available,
        "medeadb_path": str(database.path),
        "medeadb_resources": database.resources,
        "medeadb_missing": list(database.missing),
        "error": vendor_error or routing_error,
    }


@app.get("/database/status")
def database_status() -> dict[str, object]:
    """Report the exact MedeaDB resources visible to the service."""
    status = inspect_medeadb()
    return {
        "status": "ok" if status.available else "incomplete",
        "database_required": database_required(),
        **status.as_dict(),
    }


@app.post("/database/depmap-correlation")
def database_depmap_correlation(
    request: DepMapCorrelationRequest,
) -> dict[str, object]:
    """Query MedeaDB through upstream Medea's GeneCorrelationLookup parser."""
    try:
        medea_module = import_vendor_module(_repo_path(), _module_names())
        status = inspect_medeadb()
        require_medeadb(status)
        result = depmap_correlation(
            medea_module,
            status,
            request.gene_a,
            request.gene_b,
        )
    except (MedeaDatabaseError, VendorRuntimeError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return {
        "status": "ok",
        "source": "MedeaDB/depmap_24q2",
        "requires_human_review": True,
        **asdict(result),
    }


@app.get("/runtime-contract")
def runtime_contract() -> dict[str, object]:
    """Validate literature reasoning, local vLLM routing, and MedeaDB parsing."""
    try:
        medea_module = import_vendor_module(_repo_path(), _module_names())
        routing, patched_modules = configure_and_patch_medea_for_local_vllm(
            medea_module
        )
        _assert_medea_reasoning_members(medea_module)
        database = inspect_medeadb()
        required = database_required()
        runtime = _validate_database_runtime_if_enabled(
            medea_module,
            database,
            required=required,
        )
    except (MedeaDatabaseError, VendorRuntimeError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return {
        "status": "ok",
        "service": "medea_service",
        "vendor_available": True,
        "literature_reasoning_available": True,
        "local_model_configured": True,
        "remote_provider_blocked": True,
        "local_chat_completion_patched": True,
        "patched_modules": list(patched_modules),
        "local_model_base_url": routing.vllm_base_url,
        "local_model_name": routing.model_name,
        "database_required": required,
        "database_available": database.available,
        "database_parseable": runtime is not None,
        "database_gene_count": runtime.gene_count if runtime else None,
        "database_format": runtime.storage_format if runtime else None,
        "medeadb_path": str(database.path),
        "medeadb_resources": database.resources,
    }


@app.post("/reason")
async def reason(request: ReasonRequest) -> dict[str, object]:
    """Run Medea literature reasoning enriched with bounded MedeaDB evidence."""
    try:
        context = EvidenceContextBundle.model_validate(request.context)
        medea_module = import_vendor_module(_repo_path(), _module_names())
        routing, patched_modules = configure_and_patch_medea_for_local_vllm(
            medea_module
        )
        database = inspect_medeadb()
        required = database_required()
        database_evidence = _collect_database_evidence_if_enabled(
            medea_module,
            context,
            database,
            required=required,
        )
    except (MedeaDatabaseError, ValueError, VendorRuntimeError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    try:
        result = await _run_medea_literature_reasoning_with_timeout(
            medea_module,
            context,
            routing=routing,
            database_evidence=database_evidence,
        )
        artifact = _artifact_from_medea_result(
            context,
            result,
            routing=routing,
            patched_modules=patched_modules,
            database=database,
            database_evidence=database_evidence,
            required_database=required,
        )
    except VendorRuntimeError as error:
        artifact = _unavailable_medea_artifact(
            context,
            routing=routing,
            patched_modules=patched_modules,
            database=database,
            database_evidence=database_evidence,
            required_database=required,
            reason=str(error),
        )
    return artifact.model_dump(mode="json")


def _validate_database_runtime_if_enabled(
    medea_module: Any,
    database: MedeaDBStatus,
    *,
    required: bool,
) -> Any | None:
    """Validate MedeaDB only when required or fully usable.

    Acceptance criteria:
        1. Strict mode: Required MedeaDB failures propagate to the caller.
        2. Optional mode: Missing MedeaDB returns `None`.
        3. Optional mode: Parser/import failures return `None`.
        4. No mutation: Do not mutate the supplied database status.

    Args:
        medea_module: Imported vendored Medea package.
        database: Inspected MedeaDB filesystem status.
        required: Whether `MEDEA_REQUIRE_DATABASE` enables strict mode.

    Returns:
        Parsed MedeaDB runtime when usable, otherwise `None`.

    Raises:
        MedeaDatabaseError: If strict mode validation fails.
    """
    if required:
        return validate_medeadb_runtime(medea_module, database)
    if not database.available:
        return None
    try:
        return validate_medeadb_runtime(medea_module, database)
    except MedeaDatabaseError:
        return None


def _collect_database_evidence_if_enabled(
    medea_module: Any,
    context: EvidenceContextBundle,
    database: MedeaDBStatus,
    *,
    required: bool,
) -> MedeaDBEvidence | None:
    """Collect optional MedeaDB evidence without making it mandatory.

    Acceptance criteria:
        1. Strict mode: Missing or unparseable MedeaDB failures propagate.
        2. Optional mode: Missing MedeaDB returns `None`.
        3. Optional mode: Parser/import failures return `None`.
        4. No mutation: Do not mutate the evidence context or database status.

    Args:
        medea_module: Imported vendored Medea package.
        context: Source evidence context for the reasoning request.
        database: Inspected MedeaDB filesystem status.
        required: Whether `MEDEA_REQUIRE_DATABASE` enables strict mode.

    Returns:
        Bounded MedeaDB evidence when usable, otherwise `None`.

    Raises:
        MedeaDatabaseError: If strict mode validation or parsing fails.
    """
    if required:
        require_medeadb(database)
        return _collect_database_evidence(medea_module, context, database)
    if not database.available:
        return None
    try:
        return _collect_database_evidence(medea_module, context, database)
    except MedeaDatabaseError:
        return None


def _repo_path() -> Path:
    return Path(os.getenv("MEDEA_VENDOR_DIR", "/app/third_party/upstream/Medea"))


def _module_names() -> tuple[str, ...]:
    raw = os.getenv("MEDEA_MODULE_NAMES", "medea")
    return tuple(item.strip() for item in raw.split(",") if item.strip())


def _assert_medea_reasoning_members(medea_module: Any) -> None:
    required_names = (
        "literature_reasoning",
        "AgentLLM",
        "LLMConfig",
        "LiteratureReasoning",
        "LiteratureSearch",
        "PaperJudge",
        "OpenScholarReasoning",
    )
    missing = [name for name in required_names if not hasattr(medea_module, name)]
    if missing:
        raise VendorRuntimeError(
            "Medea package missing required bounded reasoning members: "
            + ", ".join(missing)
        )


def _positive_int_environment(name: str, default: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as error:
        raise MedeaDatabaseError(f"{name} must be an integer") from error
    if value <= 0:
        raise MedeaDatabaseError(f"{name} must be positive")
    return value


def _nonnegative_int_environment(name: str, default: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as error:
        raise MedeaDatabaseError(f"{name} must be an integer") from error
    if value < 0:
        raise MedeaDatabaseError(f"{name} cannot be negative")
    return value


def _collect_database_evidence(
    medea_module: Any,
    context: EvidenceContextBundle,
    database: MedeaDBStatus,
) -> MedeaDBEvidence:
    return collect_medeadb_evidence(
        medea_module,
        context,
        database,
        max_pairs=_positive_int_environment("MEDEA_DB_MAX_GENE_PAIRS", 10),
        neighbors_per_single_gene=_nonnegative_int_environment(
            "MEDEA_DB_SIMILAR_GENES_PER_SINGLE_GENE",
            3,
        ),
    )


def _run_medea_literature_reasoning(
    medea_module: Any,
    context: EvidenceContextBundle,
    *,
    routing: LocalMedeaRoutingConfig,
    database_evidence: MedeaDBEvidence | None,
) -> Any:
    """Run Medea's bounded literature-reasoning entrypoint."""
    _assert_medea_reasoning_members(medea_module)
    try:
        llm_config = medea_module.LLMConfig({"temperature": 0.0})
        literature_llm = medea_module.AgentLLM(
            llm_config,
            llm_name=routing.model_name,
        )
        literature_actions = [
            medea_module.LiteratureSearch(
                model_name=routing.model_name,
                verbose=False,
            ),
            medea_module.PaperJudge(
                model_name=routing.model_name,
                verbose=False,
            ),
            medea_module.OpenScholarReasoning(
                tmp=0.0,
                llm_provider=routing.model_name,
                verbose=False,
            ),
        ]
        literature_module = medea_module.LiteratureReasoning(
            llm=literature_llm,
            actions=literature_actions,
        )
        if hasattr(literature_module, "max_exec_steps"):
            literature_module.max_exec_steps = _positive_int_runtime_environment(
                "MEDEA_LITERATURE_MAX_EXEC_STEPS",
                _DEFAULT_LITERATURE_MAX_EXEC_STEPS,
            )
        return medea_module.literature_reasoning(
            query=_query_from_context(context, database_evidence),
            literature_module=literature_module,
        )
    except Exception as error:
        raise VendorRuntimeError(f"Medea bounded reasoning failed: {error}") from error


async def _run_medea_literature_reasoning_with_timeout(
    medea_module: Any,
    context: EvidenceContextBundle,
    *,
    routing: LocalMedeaRoutingConfig,
    database_evidence: MedeaDBEvidence | None,
) -> Any:
    """Run blocking Medea reasoning off the event loop with a timeout.

    Acceptance criteria:
        1. Runs vendored Medea literature reasoning outside the FastAPI event
           loop so health checks remain responsive.
        2. Uses the existing MIMS request-timeout budget to return before the
           calling API client times out.
        3. Converts timeout into `VendorRuntimeError` so callers can emit the
           schema-valid unavailable Medea artifact.
        4. Does not mutate the evidence context, routing config, or database
           evidence.

    Args:
        medea_module: Imported vendored Medea module.
        context: Source evidence context for the reasoning request.
        routing: Validated local-vLLM routing config.
        database_evidence: Optional bounded MedeaDB evidence.

    Returns:
        Raw vendored Medea reasoning result.

    Raises:
        VendorRuntimeError: If reasoning exceeds the timeout budget.
    """
    timeout_seconds = _medea_reasoning_timeout_seconds()
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(
                _run_medea_literature_reasoning,
                medea_module,
                context,
                routing=routing,
                database_evidence=database_evidence,
            ),
            timeout=timeout_seconds,
        )
    except TimeoutError as error:
        raise VendorRuntimeError(
            "Medea bounded reasoning timed out after "
            f"{timeout_seconds:.3g} seconds"
        ) from error


def _medea_reasoning_timeout_seconds() -> float:
    """Return the Medea reasoning timeout derived from existing settings.

    Acceptance criteria:
        1. Determinism: Same environment returns the same timeout.
        2. Validation: Non-positive or non-numeric values raise
           `VendorRuntimeError`.
        3. Compatibility: Uses existing timeout environment variables instead
           of introducing a new public setting.
        4. Caller headroom: Returns a value below the upstream MIMS client
           timeout when practical.

    Returns:
        Timeout in seconds for one vendored Medea reasoning call.

    Raises:
        VendorRuntimeError: If the selected timeout value is invalid.
    """
    raw = os.getenv(
        "MIMS_TIMEOUT_SECONDS",
        os.getenv("MEDEA_VLLM_TIMEOUT_SECONDS", "240"),
    )
    try:
        client_timeout = float(raw)
    except ValueError as error:
        raise VendorRuntimeError("MIMS_TIMEOUT_SECONDS must be numeric") from error
    if client_timeout <= 0:
        raise VendorRuntimeError("MIMS_TIMEOUT_SECONDS must be positive")
    if client_timeout > 30:
        return client_timeout - 15
    return client_timeout * 0.8


def _query_from_context(
    context: EvidenceContextBundle,
    database_evidence: MedeaDBEvidence | None = None,
) -> str:
    findings = [
        f"{finding.gene or ''} {finding.alteration}".strip()
        for finding in context.extraction.molecular_findings
    ]
    disease = context.extraction.disease or "the reported tumor type"
    graph_terms = sorted({node.label for node in context.graph_evidence.nodes})[:20]
    tool_summaries = [output.workflow for output in context.tool_outputs][:10]
    database_context = (
        "\n\n" + evidence_prompt_text(database_evidence)
        if database_evidence is not None
        else ""
    )
    return (
        "Provide literature and omics reasoning support for reviewable tumor-behavior "
        f"hypotheses in {disease}. Reported molecular findings: "
        + "; ".join(findings)
        + ". Graph context terms: "
        + ", ".join(graph_terms)
        + ". ToolUniverse workflows available: "
        + ", ".join(tool_summaries)
        + database_context
        + "\nDo not recommend treatment; identify support, uncertainty, and validation gaps."
    )


def _artifact_from_medea_result(
    context: EvidenceContextBundle,
    result: Any,
    *,
    routing: LocalMedeaRoutingConfig,
    patched_modules: tuple[str, ...],
    database: MedeaDBStatus,
    database_evidence: MedeaDBEvidence | None,
    required_database: bool,
) -> MedeaReasoningArtifact:
    text = _result_to_text(result)
    _validate_reasoning_text(text)
    artifact_id = f"artifact_{uuid5(NAMESPACE_URL, context.artifact_id + ':medea_service').hex[:16]}"
    warnings = [
        "medea_output_is_bounded_reasoning_support_not_clinical_truth",
        "medea_model_calls_routed_through_local_vllm",
        "patched_modules=" + ",".join(patched_modules),
        "local_model=" + routing.model_name,
        f"medeadb_required={str(required_database).lower()}",
        f"medeadb_available={str(database.available).lower()}",
        "medeadb_path=" + str(database.path),
    ]
    summary_parts: list[str] = []
    if database_evidence is not None:
        summary_parts.append(
            "MedeaDB evidence supplied to literature reasoning:\n"
            + evidence_prompt_text(database_evidence)
        )
        warnings.extend(
            (
                "medeadb_evidence_is_exploratory_and_requires_human_review",
                f"medeadb_depmap_pair_count={len(database_evidence.pairwise)}",
                f"medeadb_depmap_neighbor_count={len(database_evidence.neighbors)}",
            )
        )
        if database_evidence.missing_genes:
            warnings.append(
                "medeadb_missing_report_genes="
                + ",".join(database_evidence.missing_genes)
            )
    elif not database.available:
        warnings.append("medeadb_not_available_for_this_reasoning_run")
    summary_parts.append("Medea literature reasoning:\n" + text)
    mode = (
        "medea_literature_reasoning_with_medeadb_local_vllm"
        if database_evidence is not None
        else "medea_literature_reasoning_local_vllm"
    )
    return MedeaReasoningArtifact(
        artifact_id=artifact_id,
        reasoning_mode=mode,
        summary="\n\n".join(summary_parts)[:4000],
        supported_hypotheses=[],
        weakened_hypotheses=[],
        warnings=warnings,
        requires_human_review=True,
    )


def _unavailable_medea_artifact(
    context: EvidenceContextBundle,
    *,
    routing: LocalMedeaRoutingConfig,
    patched_modules: tuple[str, ...],
    database: MedeaDBStatus,
    database_evidence: MedeaDBEvidence | None,
    required_database: bool,
    reason: str,
) -> MedeaReasoningArtifact:
    """Return a bounded unavailable artifact for unusable upstream reasoning.

    Acceptance criteria:
        1. Returns schema-valid `MedeaReasoningArtifact`.
        2. Does not fabricate literature conclusions or hypotheses.
        3. Preserves local routing and MedeaDB availability metadata.
        4. Requires human review for all downstream claims.

    Args:
        context: Evidence context that was submitted to Medea.
        routing: Local vLLM routing used by the service.
        patched_modules: Vendored modules patched for local model routing.
        database: Inspected MedeaDB status.
        database_evidence: Optional bounded MedeaDB evidence.
        required_database: Whether MedeaDB strict mode was enabled.
        reason: Upstream reasoning failure or unusable-output reason.

    Returns:
        Review-required Medea reasoning artifact.
    """
    artifact_id = f"artifact_{uuid5(NAMESPACE_URL, context.artifact_id + ':medea_service_unavailable').hex[:16]}"
    warnings = [
        "medea_literature_reasoning_unavailable",
        "medea_output_not_used_for_claim_support",
        "medea_model_calls_routed_through_local_vllm",
        "patched_modules=" + ",".join(patched_modules),
        "local_model=" + routing.model_name,
        f"medeadb_required={str(required_database).lower()}",
        f"medeadb_available={str(database.available).lower()}",
        "medeadb_path=" + str(database.path),
        "upstream_reason=" + reason[:500],
    ]
    summary_parts = [
        (
            "Medea literature reasoning was unavailable or unusable for this "
            "case; downstream claims must remain needs_review."
        )
    ]
    if database_evidence is not None:
        summary_parts.append(
            "MedeaDB evidence was available but remains exploratory and "
            "requires human review:\n"
            + evidence_prompt_text(database_evidence)
        )
        warnings.extend(
            (
                "medeadb_evidence_is_exploratory_and_requires_human_review",
                f"medeadb_depmap_pair_count={len(database_evidence.pairwise)}",
                f"medeadb_depmap_neighbor_count={len(database_evidence.neighbors)}",
            )
        )
    elif not database.available:
        warnings.append("medeadb_not_available_for_this_reasoning_run")
    return MedeaReasoningArtifact(
        artifact_id=artifact_id,
        reasoning_mode="medea_literature_reasoning_unavailable",
        summary="\n\n".join(summary_parts)[:4000],
        supported_hypotheses=[],
        weakened_hypotheses=[],
        warnings=warnings,
        requires_human_review=True,
    )


def _validate_reasoning_text(text: str) -> None:
    """Validate that upstream Medea output is usable reasoning text.

    Acceptance criteria:
        1. Rejects blank output.
        2. Rejects agent traces and action-parameter error text.
        3. Rejects placeholder `None` output.
        4. Does not mutate caller-owned values.

    Args:
        text: Text extracted from the upstream Medea result.

    Raises:
        VendorRuntimeError: If the text is unusable as reasoning support.
    """
    normalized = text.strip()
    if not normalized or normalized in {"None", "{}", "[]"}:
        raise VendorRuntimeError("Medea returned empty reasoning output")
    for marker in _UNUSABLE_REASONING_MARKERS:
        if marker in normalized:
            raise VendorRuntimeError(
                "Medea returned an unusable agent trace instead of reasoning"
            )


def _positive_int_runtime_environment(name: str, default: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as error:
        raise VendorRuntimeError(f"{name} must be an integer") from error
    if value <= 0:
        raise VendorRuntimeError(f"{name} must be positive")
    return value


def _result_to_text(result: Any) -> str:
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        for key in ("final", "summary", "result", "R", "PA", "P"):
            value = result.get(key)
            if value:
                return _result_to_text(value)
        return repr(result)
    return repr(result)
