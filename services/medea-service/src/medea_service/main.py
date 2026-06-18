from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from medea_service.local_runtime import (
    LocalMedeaRoutingConfig,
    build_local_medea_routing_config,
    configure_and_patch_medea_for_local_vllm,
)
from medea_service.vendor_runtime import VendorRuntimeError, import_vendor_module
from translume_schemas.evidence import EvidenceContextBundle
from translume_schemas.medea import MedeaReasoningArtifact

app = FastAPI(title="medea_service")


class ReasonRequest(BaseModel):
    context: dict[str, object]


@app.get("/health")
def health() -> dict[str, object]:
    """Return service health, vendored Medea availability, and local routing status.

    Acceptance criteria:
        1. Reports whether the real vendored Medea package can import.
        2. Reports whether local-vLLM routing is configured.
        3. Reports remote-provider configuration failures explicitly.
        4. Does not run bounded reasoning or fabricate readiness.
    """
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
    return {
        "status": "ok",
        "service": "medea_service",
        "vendor_path": str(repo_path),
        "vendor_available": vendor_available,
        "local_model_configured": local_model_configured,
        "remote_provider_blocked": remote_provider_blocked,
        "local_model_base_url": local_model_base_url,
        "local_model_name": local_model_name,
        "error": vendor_error or routing_error,
    }


@app.get("/runtime-contract")
def runtime_contract() -> dict[str, object]:
    """Validate Medea import, local-vLLM routing, and patchability without faking reasoning.

    Acceptance criteria:
        1. Imports the real vendored Medea package.
        2. Requires local vLLM routing configuration.
        3. Blocks remote-provider credentials.
        4. Patches Medea LLM call sites from Translume-owned code.
        5. Returns patched module names for live VM validation.
    """
    try:
        medea_module = import_vendor_module(_repo_path(), _module_names())
        routing, patched_modules = configure_and_patch_medea_for_local_vllm(medea_module)
        _assert_medea_reasoning_members(medea_module)
    except VendorRuntimeError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return {
        "status": "ok",
        "service": "medea_service",
        "vendor_available": True,
        "local_model_configured": True,
        "remote_provider_blocked": True,
        "local_chat_completion_patched": True,
        "patched_modules": list(patched_modules),
        "local_model_base_url": routing.vllm_base_url,
        "local_model_name": routing.model_name,
    }


@app.post("/reason")
async def reason(request: ReasonRequest) -> dict[str, object]:
    """Run bounded Medea reasoning using local-vLLM-routed vendored Medea.

    Acceptance criteria:
        1. Requires the real vendored Medea package.
        2. Requires validated local vLLM configuration.
        3. Blocks remote model-provider credentials.
        4. Patches Medea LLM call sites to local vLLM from outside the vendor repo.
        5. Executes Medea literature_reasoning; no fallback reasoning is made up.
        6. Normalizes Medea output to `MedeaReasoningArtifact`.
    """
    try:
        context = EvidenceContextBundle.model_validate(request.context)
        medea_module = import_vendor_module(_repo_path(), _module_names())
        routing, patched_modules = configure_and_patch_medea_for_local_vllm(medea_module)
        result = _run_medea_literature_reasoning(
            medea_module,
            context,
            routing=routing,
        )
        artifact = _artifact_from_medea_result(
            context,
            result,
            routing=routing,
            patched_modules=patched_modules,
        )
    except (ValueError, VendorRuntimeError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return artifact.model_dump(mode="json")


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


def _run_medea_literature_reasoning(
    medea_module: Any,
    context: EvidenceContextBundle,
    *,
    routing: LocalMedeaRoutingConfig,
) -> Any:
    """Run Medea's bounded literature reasoning entrypoint.

    Acceptance criteria:
        1. Requires `literature_reasoning` entrypoint and module classes.
        2. Builds the query from structured context, not hardcoded disease facts.
        3. Uses the local vLLM model configured in `routing`.
        4. Raises if Medea execution fails.
    """
    _assert_medea_reasoning_members(medea_module)
    try:
        llm_config = medea_module.LLMConfig({"temperature": 0.0})
        literature_llm = medea_module.AgentLLM(llm_config, llm_name=routing.model_name)
        literature_actions = [
            medea_module.LiteratureSearch(model_name=routing.model_name, verbose=False),
            medea_module.PaperJudge(model_name=routing.model_name, verbose=False),
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
        return medea_module.literature_reasoning(
            query=_query_from_context(context),
            literature_module=literature_module,
        )
    except Exception as error:
        raise VendorRuntimeError(f"Medea bounded reasoning failed: {error}") from error


def _query_from_context(context: EvidenceContextBundle) -> str:
    findings = [
        f"{finding.gene or ''} {finding.alteration}".strip()
        for finding in context.extraction.molecular_findings
    ]
    disease = context.extraction.disease or "the reported tumor type"
    graph_terms = sorted({node.label for node in context.graph_evidence.nodes})[:20]
    tool_summaries = [output.workflow for output in context.tool_outputs][:10]
    return (
        "Provide literature and omics reasoning support for reviewable tumor-behavior "
        f"hypotheses in {disease}. Reported molecular findings: "
        + "; ".join(findings)
        + ". Graph context terms: "
        + ", ".join(graph_terms)
        + ". ToolUniverse workflows available: "
        + ", ".join(tool_summaries)
        + ". Do not recommend treatment; identify support, uncertainty, and validation gaps."
    )


def _artifact_from_medea_result(
    context: EvidenceContextBundle,
    result: Any,
    *,
    routing: LocalMedeaRoutingConfig,
    patched_modules: tuple[str, ...],
) -> MedeaReasoningArtifact:
    text = _result_to_text(result)
    if not text.strip():
        raise VendorRuntimeError("Medea returned empty reasoning output")
    artifact_id = f"artifact_{uuid5(NAMESPACE_URL, context.artifact_id + ':medea_service').hex[:16]}"
    warnings = [
        "medea_output_is_bounded_reasoning_support_not_clinical_truth",
        "medea_model_calls_routed_through_local_vllm",
        "patched_modules=" + ",".join(patched_modules),
        "local_model=" + routing.model_name,
    ]
    return MedeaReasoningArtifact(
        artifact_id=artifact_id,
        reasoning_mode="medea_literature_reasoning_local_vllm",
        summary=text[:4000],
        supported_hypotheses=[],
        weakened_hypotheses=[],
        warnings=warnings,
        requires_human_review=True,
    )


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
