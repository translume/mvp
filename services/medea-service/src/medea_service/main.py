"""CPU-only Medea literature and DepMap service with OpenAI inference."""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from threading import Event
from uuid import NAMESPACE_URL, uuid5

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ValidationError
from translume_clients.openai_client import OpenAISyncClient
from translume_ports.model_provider import ModelProviderError
from translume_schemas.evidence import EvidenceContextBundle
from translume_schemas.medea import MedeaReasoningArtifact

from medea_service.database_runtime import (
    MedeaDatabaseError,
    MedeaDBEvidence,
    MedeaDBStatus,
    collect_medeadb_evidence,
    context_genes,
    database_required,
    depmap_correlation,
    evidence_prompt_text,
    inspect_medeadb,
    require_medeadb,
    validate_medeadb_runtime,
)
from medea_service.literature_search import PublicLiteratureSearch, search_queries
from medea_service.openai_literature_action import (
    OpenAILiteratureResult,
    run_literature_pipeline,
)
from medea_service.openai_runtime import (
    OpenAICompletion,
    OpenAIMedeaConfig,
    build_openai_medea_config,
)
from medea_service.vendor_runtime import (
    MedeaSourceRuntime,
    VendorRuntimeError,
    import_vendor_module,
)


@dataclass(frozen=True)
class MedeaServiceRuntime:
    """Service-owned pools and verified source; no local model instances."""

    config: OpenAIMedeaConfig
    source: MedeaSourceRuntime
    model_http: httpx.Client
    literature_http: httpx.Client
    semaphore: asyncio.Semaphore


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Validate source/data, own connection pools, and release them at shutdown."""
    config = build_openai_medea_config()
    source = import_vendor_module(_repo_path(), ("medea",))
    database = inspect_medeadb()
    if database_required():
        validate_medeadb_runtime(source, database)
    model_http = httpx.Client(follow_redirects=False)
    literature_http = httpx.Client(
        follow_redirects=False,
        headers={"User-Agent": "Translume-Literature/0.1"},
    )
    application.state.runtime = MedeaServiceRuntime(
        config, source, model_http, literature_http, asyncio.Semaphore(2)
    )
    try:
        yield
    finally:
        model_http.close()
        literature_http.close()


app = FastAPI(title="medea_service", lifespan=lifespan)


class ReasonRequest(BaseModel):
    context: dict[str, object]


class DepMapCorrelationRequest(BaseModel):
    gene_a: str
    gene_b: str


def _runtime() -> MedeaServiceRuntime:
    runtime = getattr(app.state, "runtime", None)
    if not isinstance(runtime, MedeaServiceRuntime):
        raise VendorRuntimeError("Medea service has not completed startup validation")
    return runtime


@app.get("/health")
def health() -> dict[str, object]:
    """Report configured remote routing and actual active-data availability."""
    try:
        runtime = _runtime()
        database = inspect_medeadb()
        if database_required():
            require_medeadb(database)
    except (MedeaDatabaseError, VendorRuntimeError) as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return {
        "status": "ok",
        "service": "medea_service",
        "vendor_available": True,
        "literature_reasoning_available": True,
        "provider": "openai",
        "remote_model_configured": True,
        "remote_model_name": runtime.config.model_name,
        "reasoning_mode": runtime.config.reasoning_mode,
        "reranker": "openai_embeddings",
        "local_inference_enabled": False,
        "database_required": database_required(),
        "database_available": database.available,
        "database_profile": "depmap_24q2",
        "remote_api_verified": False,
    }


@app.get("/database/status")
def database_status() -> dict[str, object]:
    """Report the exact DepMap files used, without requiring unused checkpoints."""
    status = inspect_medeadb()
    return {
        "status": "ok" if status.available else "incomplete",
        "database_required": database_required(),
        **status.as_dict(),
    }


@app.post("/database/depmap-correlation")
def database_depmap_correlation(request: DepMapCorrelationRequest) -> dict[str, object]:
    """Query the actual upstream memory-mapped GeneCorrelationLookup parser."""
    try:
        runtime = _runtime()
        status = inspect_medeadb()
        require_medeadb(status)
        result = depmap_correlation(
            runtime.source, status, request.gene_a, request.gene_b
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
    """Validate real upstream source and data, not claim a live model probe."""
    try:
        runtime = _runtime()
        database = inspect_medeadb()
        required = database_required()
        parsed = (
            validate_medeadb_runtime(runtime.source, database)
            if required or database.available
            else None
        )
        runtime.source.new_open_scholar_module()
    except (MedeaDatabaseError, VendorRuntimeError) as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return {
        "status": "ok",
        "service": "medea_service",
        "vendor_available": True,
        "literature_reasoning_available": True,
        "provider": "openai",
        "remote_model_configured": True,
        "remote_model_base_url": runtime.config.base_url,
        "remote_model_name": runtime.config.model_name,
        "reasoning_mode": runtime.config.reasoning_mode,
        "reranker": "openai_embeddings",
        "embedding_model": runtime.config.embedding_model,
        "embedding_dimensions": runtime.config.embedding_dimensions,
        "local_inference_enabled": False,
        "remote_api_verified": False,
        "upstream_source_sha256": runtime.source.source_sha256,
        "database_required": required,
        "database_available": database.available,
        "database_parseable": parsed is not None,
        "database_gene_count": parsed.gene_count if parsed else None,
        "database_format": parsed.storage_format if parsed else None,
        "database_profile": "depmap_24q2",
        "medeadb_path": str(database.path),
        "medeadb_resources": database.resources,
    }


@app.post("/reason")
async def reason(request: ReasonRequest) -> dict[str, object]:
    """Run actual literature and database evidence without hiding failed inference.

    Acceptance criteria:
        1. Every successful artifact contains actual search/call/source metadata.
        2. Auth, quota, refusal and timeout failures remain failed requests.
        3. A genuine bounded search with no usable results is labelled explicitly.
        4. Blocking source/API operations run off the FastAPI event loop.
    """
    try:
        context = EvidenceContextBundle.model_validate(request.context)
        runtime = _runtime()
        timeout = _positive_number("MEDEA_TOTAL_TIMEOUT_SECONDS", 7000)
    except ValidationError as error:
        raise HTTPException(
            status_code=422, detail="invalid evidence context"
        ) from error
    except VendorRuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    cancelled = Event()
    await runtime.semaphore.acquire()
    task = asyncio.create_task(
        asyncio.to_thread(_reason_sync, runtime, context, cancelled)
    )
    # Release capacity only when the worker really ends. A network call already
    # in flight remains bounded by its own timeout after overall cancellation.
    task.add_done_callback(lambda _: runtime.semaphore.release())
    try:
        artifact = await asyncio.wait_for(asyncio.shield(task), timeout=timeout)
    except TimeoutError as error:
        cancelled.set()
        task.add_done_callback(_consume_worker_exception)
        raise HTTPException(
            status_code=504, detail="Medea reasoning exceeded its time budget"
        ) from error
    except asyncio.CancelledError:
        cancelled.set()
        task.add_done_callback(_consume_worker_exception)
        raise
    except ModelProviderError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    except (MedeaDatabaseError, VendorRuntimeError) as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return artifact.model_dump(mode="json")


def _consume_worker_exception(task: asyncio.Task) -> None:
    if not task.cancelled():
        task.exception()


def _reason_sync(
    runtime: MedeaServiceRuntime, context: EvidenceContextBundle, cancelled: Event
) -> MedeaReasoningArtifact:
    database = inspect_medeadb()
    required = database_required()
    if required:
        require_medeadb(database)
    evidence = (
        collect_medeadb_evidence(
            runtime.source,
            context,
            database,
            max_pairs=_bounded_integer("MEDEA_DB_MAX_GENE_PAIRS", 10, 1, 100),
            neighbors_per_single_gene=_bounded_integer(
                "MEDEA_DB_SIMILAR_GENES_PER_SINGLE_GENE", 3, 0, 100
            ),
        )
        if database.available
        else None
    )
    client = OpenAISyncClient(
        api_key=runtime.config.api_key,
        base_url=runtime.config.base_url,
        timeout_seconds=runtime.config.timeout_seconds,
        http_client=runtime.model_http,
        audit_path=os.environ.get("OPENAI_AUDIT_PATH") or None,
        correlation_id=context.artifact_id,
    )
    try:
        completion = OpenAICompletion(client, runtime.config, cancelled)
        result = run_literature_pipeline(
            runtime=runtime.source,
            search=PublicLiteratureSearch(runtime.literature_http),
            queries=search_queries(context.extraction.disease, context_genes(context)),
            question=_query_from_context(context, evidence),
            completion=completion,
        )
        return _artifact_from_result(
            context, result, runtime, database, evidence, client
        )
    finally:
        client.close()


def _artifact_from_result(
    context: EvidenceContextBundle,
    result: OpenAILiteratureResult,
    runtime: MedeaServiceRuntime,
    database: MedeaDBStatus,
    evidence: MedeaDBEvidence | None,
    client: OpenAISyncClient,
) -> MedeaReasoningArtifact:
    summaries = []
    if evidence is not None:
        summaries.append(evidence_prompt_text(evidence))
    summaries.append(result.summary)
    warnings = [
        "medea_output_is_bounded_hypothesis_support_not_clinical_truth",
        "medea_model_calls_routed_through_openai",
        "medea_reranking_algorithm=openai_embedding_cosine",
        "literature_scope=bounded_abstract_search_not_exhaustive_review",
        f"literature_status={result.status}",
        f"medeadb_available={str(database.available).lower()}",
        *result.limitations,
    ]
    if evidence is not None:
        warnings.extend(
            (
                "medeadb_evidence_is_exploratory_and_requires_human_review",
                f"medeadb_depmap_pair_count={len(evidence.pairwise)}",
                f"medeadb_depmap_neighbor_count={len(evidence.neighbors)}",
            )
        )
    warnings.extend(
        f"literature_source_unavailable={item.provider}:{item.error_code}"
        for item in result.search_result.searches
        if item.status != "succeeded"
    )
    if len(context_genes(context)) > 12:
        warnings.append("literature_query_gene_limit=first_12_report_genes")
    calls = list(client.call_records)
    mode = (
        "medea_literature_reasoning_with_medeadb_openai"
        if evidence is not None
        else "medea_literature_reasoning_openai"
    )
    return MedeaReasoningArtifact(
        artifact_id=f"artifact_{uuid5(NAMESPACE_URL, context.artifact_id + ':medea_openai').hex[:16]}",
        reasoning_mode=mode,
        summary="\n\n".join(summaries),
        supported_hypotheses=list(result.supported_hypotheses),
        weakened_hypotheses=list(result.weakened_hypotheses),
        warnings=warnings,
        requires_human_review=True,
        decision_support_role="hypothesis_support_only",
        downstream_uses=[
            "resistance_escape_forecast",
            "treatment_pressure_map",
            "biomarker_watch_list",
            "evidence_limitations",
        ],
        source_references=list(result.references),
        literature_searches=list(result.search_result.searches),
        paper_judgements=list(result.judgements),
        model_call_ids=[call.call_id for call in calls],
        model_calls=calls,
        model_provider="openai",
        model_name=runtime.config.model_name,
        model_reasoning_mode=runtime.config.reasoning_mode,
    )


def _query_from_context(
    context: EvidenceContextBundle, evidence: MedeaDBEvidence | None
) -> str:
    findings = [
        f"{finding.gene or ''} {finding.alteration}".strip()
        for finding in context.extraction.molecular_findings
    ]
    disease = context.extraction.disease or "the reported tumor type"
    graph_terms = sorted({node.label for node in context.graph_evidence.nodes})[:20]
    query = (
        "Provide bounded literature and omics hypothesis support for treatment-pressure, "
        "escape-route, biomarker-monitoring, lineage-transformation and validation-gap "
        f"review in {disease}. Reported findings: {'; '.join(findings)}. "
        f"Graph context: {', '.join(graph_terms)}. "
        "Do not recommend or rank therapies, predict outcomes or assert clinical truth. "
        "Distinguish exploratory mechanisms, direct evidence and uncertainty."
    )
    return query + ("\n\n" + evidence_prompt_text(evidence) if evidence else "")


def _repo_path() -> Path:
    return Path(os.getenv("MEDEA_VENDOR_DIR", "/app/third_party/upstream/Medea"))


def _positive_number(name: str, default: float) -> float:
    try:
        value = float(os.environ.get(name, str(default)))
    except ValueError as error:
        raise VendorRuntimeError(f"{name} must be numeric") from error
    if not 0 < value < float("inf"):
        raise VendorRuntimeError(f"{name} must be positive and finite")
    return value


def _bounded_integer(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except ValueError as error:
        raise VendorRuntimeError(f"{name} must be an integer") from error
    if not minimum <= value <= maximum:
        raise VendorRuntimeError(f"{name} must be between {minimum} and {maximum}")
    return value
