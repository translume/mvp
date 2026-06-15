from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from medea_service.vendor_runtime import (
    VendorRuntimeError,
    assert_remote_model_env_blocked,
    import_vendor_module,
)
from translume_schemas.evidence import EvidenceContextBundle
from translume_schemas.medea import MedeaReasoningArtifact

app = FastAPI(title="medea_service")


class ReasonRequest(BaseModel):
    context: dict[str, object]


@app.get("/health")
def health() -> dict[str, object]:
    """Return service health and Medea availability."""
    repo_path = _repo_path()
    try:
        import_vendor_module(repo_path, _module_names())
        vendor_available = True
        error = None
    except VendorRuntimeError as runtime_error:
        vendor_available = False
        error = str(runtime_error)
    return {
        "status": "ok",
        "service": "medea_service",
        "vendor_path": str(repo_path),
        "vendor_available": vendor_available,
        "error": error,
    }


@app.post("/reason")
async def reason(request: ReasonRequest) -> dict[str, object]:
    """Run bounded Medea reasoning using the vendored Medea package.

    Acceptance criteria:
        1. Requires the real vendored Medea package.
        2. Requires local vLLM configuration.
        3. Blocks remote model-provider credentials.
        4. Executes configured Medea entrypoint; no fallback reasoning is made up.
        5. Normalizes Medea output to `MedeaReasoningArtifact`.
    """
    try:
        context = EvidenceContextBundle.model_validate(request.context)
        _configure_local_model_environment()
        medea_module = import_vendor_module(_repo_path(), _module_names())
        result = _run_medea_literature_reasoning(medea_module, context)
        artifact = _artifact_from_medea_result(context, result)
    except (ValueError, VendorRuntimeError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return artifact.model_dump(mode="json")


def _repo_path() -> Path:
    return Path(os.getenv("MEDEA_VENDOR_DIR", "/app/third_party/upstream/Medea"))


def _module_names() -> tuple[str, ...]:
    raw = os.getenv("MEDEA_MODULE_NAMES", "medea")
    return tuple(item.strip() for item in raw.split(",") if item.strip())


def _configure_local_model_environment() -> None:
    """Configure Medea to use local OpenAI-compatible vLLM.

    Acceptance criteria:
        1. Requires VLLM_BASE_URL.
        2. Requires VLLM_MODEL.
        3. Rejects remote provider credentials.
        4. Sets only local OpenAI-compatible environment values.
    """
    vllm_base_url = os.getenv("VLLM_BASE_URL", "").strip()
    vllm_model = os.getenv("VLLM_MODEL", "").strip()
    if not vllm_base_url:
        raise VendorRuntimeError("VLLM_BASE_URL is required for Medea local routing")
    if not vllm_model:
        raise VendorRuntimeError("VLLM_MODEL is required for Medea local routing")
    assert_remote_model_env_blocked(allow_local_openai=True)
    os.environ["OPENAI_BASE_URL"] = vllm_base_url.rstrip("/")
    os.environ["OPENAI_API_BASE"] = vllm_base_url.rstrip("/")
    os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY", "local-vllm")
    os.environ["BACKBONE_LLM"] = vllm_model


def _run_medea_literature_reasoning(
    medea_module: Any,
    context: EvidenceContextBundle,
) -> Any:
    """Run Medea's bounded literature reasoning entrypoint.

    Acceptance criteria:
        1. Requires `literature_reasoning` entrypoint.
        2. Requires Medea module classes used to construct a bounded module.
        3. Builds the query from structured context, not hardcoded disease facts.
        4. Raises if Medea execution fails.
    """
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
    model_name = os.environ["BACKBONE_LLM"]
    try:
        llm_config = medea_module.LLMConfig({"temperature": 0.0})
        literature_llm = medea_module.AgentLLM(llm_config, llm_name=model_name)
        literature_actions = [
            medea_module.LiteratureSearch(model_name=model_name, verbose=False),
            medea_module.PaperJudge(model_name=model_name, verbose=False),
            medea_module.OpenScholarReasoning(
                tmp=0.0,
                llm_provider=model_name,
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
    entities = sorted({
        item
        for finding in findings
        for item in finding.split()
        if item
    })
    return (
        "Provide literature and omics reasoning support for reviewable tumor-behavior "
        f"hypotheses in {disease}. Reported molecular findings: "
        + "; ".join(findings)
        + ". Relevant extracted tokens: "
        + ", ".join(entities[:30])
        + ". Do not recommend treatment; identify support, uncertainty, and validation gaps."
    )


def _artifact_from_medea_result(
    context: EvidenceContextBundle,
    result: Any,
) -> MedeaReasoningArtifact:
    text = _result_to_text(result)
    if not text.strip():
        raise VendorRuntimeError("Medea returned empty reasoning output")
    artifact_id = f"artifact_{uuid5(NAMESPACE_URL, context.artifact_id + ':medea_service').hex[:16]}"
    return MedeaReasoningArtifact(
        artifact_id=artifact_id,
        reasoning_mode="medea_literature_reasoning_local_vllm",
        summary=text[:4000],
        supported_hypotheses=[],
        weakened_hypotheses=[],
        warnings=[],
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
