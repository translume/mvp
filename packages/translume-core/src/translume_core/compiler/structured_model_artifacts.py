from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Generic, TypeVar
from uuid import NAMESPACE_URL, uuid5

from pydantic import BaseModel, ValidationError

from translume_core.provenance.provenance import build_artifact_provenance
from translume_core.safety.language import validate_safety_language
from translume_schemas.claims import ClaimEvidenceOutput
from translume_schemas.confirmatory import ConfirmatoryTestingOutput
from translume_schemas.document import DocumentChunk, RetrievedDocumentChunk
from translume_schemas.evidence import EvidenceContextBundle
from translume_schemas.export import ClinicalArtifactBundle, ClinicalNarrativeCompilerOutput
from translume_schemas.extraction import MolecularFinding, ReportExtractionOutput
from translume_schemas.matrix import TherapyEvidenceMatrixOutput
from translume_schemas.phenotype import MolecularPhenotypeOutput
from translume_schemas.provenance import ArtifactProvenance
from translume_schemas.sankey import MechanismSankeyOutput
from translume_schemas.tumor_behavior import TumorBehaviorModelOutput


T = TypeVar("T", bound=BaseModel)

_BANNED_CLINICAL_PHRASES = [
    "recommended treatment",
    "should receive",
    "best treatment",
    "will respond",
]


class StructuredArtifactGenerationError(RuntimeError):
    """Raised when local structured-output artifact generation fails.

    Acceptance criteria:
        1. Represents failure rather than substituting a fallback artifact.
        2. Carries the failed schema name or prompt name in the message.
        3. Is raised for invalid JSON, schema mismatch, unsafe text, or ID
           mismatch.
    """


@dataclass(frozen=True)
class StructuredArtifactResult(Generic[T]):
    """A schema-validated clinical artifact plus its provenance."""

    artifact: T
    provenance: ArtifactProvenance


@dataclass(frozen=True)
class PromptPair:
    """System and user prompt templates loaded from configuration files."""

    system: str
    user: str


async def generate_report_extraction_with_model(
    *,
    retrieved_chunks: Sequence[RetrievedDocumentChunk],
    report_type: str,
    source_file_id: str,
    model_provider: object,
    model_name: str,
    prompts_root: Path,
    created_at: datetime,
) -> StructuredArtifactResult[ReportExtractionOutput]:
    """Generate source-grounded ReportExtractionOutput through local vLLM.

    Acceptance criteria:
        1. Uses retrieved OpenSearch chunks, not raw in-memory page text.
        2. Fails if no retrieved source chunks are available.
        3. Calls the configured model provider exactly once for the schema.
        4. Validates the raw model response as ReportExtractionOutput.
        5. Requires the returned artifact ID to match the planned artifact ID.
        6. Source-aligns each molecular finding back to retrieved chunks.
        7. Forces every finding to remain human-reviewable.
        8. Downgrades unsupported findings rather than presenting them as
           confident patient-specific facts.
        9. Does not add graph, literature, treatment, or tumor-behavior
           inference.
    """
    source_chunks = _require_retrieved_source_chunks(retrieved_chunks)
    planned_artifact_id = _artifact_id(source_file_id, "ReportExtractionOutput")
    payload = {
        "planned_artifact_id": planned_artifact_id,
        "report_type": report_type,
        "source_file_id": source_file_id,
        "source_grounding_contract": {
            "model_may_use_only_retrieved_chunks": True,
            "finding_source_text_must_quote_chunk": True,
            "unsupported_findings_must_be_low_confidence": True,
            "graph_literature_treatment_and_behavior_inference_disallowed": True,
        },
        "retrieved_chunks": [_retrieved_chunk_prompt_payload(item) for item in source_chunks],
    }
    result = await _generate_artifact(
        prompt_name="report_extraction",
        schema_model=ReportExtractionOutput,
        planned_artifact_id=planned_artifact_id,
        payload=payload,
        source_artifact_ids=[item.chunk.chunk_id for item in source_chunks],
        source_file_id=source_file_id,
        model_provider=model_provider,
        model_name=model_name,
        prompts_root=prompts_root,
        created_at=created_at,
    )
    aligned = _source_align_report_extraction(
        result.artifact,
        source_chunks,
        report_type=report_type,
        source_file_id=source_file_id,
    )
    _validate_report_extraction_grounding(aligned, source_chunks)
    _validate_safety(aligned.model_dump_json())
    return StructuredArtifactResult(
        artifact=aligned,
        provenance=result.provenance,
    )


async def generate_molecular_phenotype_with_model(
    *,
    context: EvidenceContextBundle,
    model_provider: object,
    model_name: str,
    prompts_root: Path,
    created_at: datetime,
) -> StructuredArtifactResult[MolecularPhenotypeOutput]:
    """Generate MolecularPhenotypeOutput through local vLLM structured output."""
    artifact_id = _artifact_id(context.artifact_id, "MolecularPhenotypeOutput")
    return await _generate_artifact(
        prompt_name="molecular_phenotype",
        schema_model=MolecularPhenotypeOutput,
        planned_artifact_id=artifact_id,
        payload={"evidence_context": context.model_dump(mode="json")},
        source_artifact_ids=_context_source_ids(context),
        source_file_id=context.extraction.source_file_id,
        model_provider=model_provider,
        model_name=model_name,
        prompts_root=prompts_root,
        created_at=created_at,
    )


async def generate_molecular_fit_matrix_with_model(
    *,
    context: EvidenceContextBundle,
    phenotype: MolecularPhenotypeOutput,
    model_provider: object,
    model_name: str,
    prompts_root: Path,
    created_at: datetime,
) -> StructuredArtifactResult[TherapyEvidenceMatrixOutput]:
    """Generate TherapyEvidenceMatrixOutput through local vLLM structured output."""
    artifact_id = _artifact_id(context.artifact_id, "TherapyEvidenceMatrixOutput")
    result = await _generate_artifact(
        prompt_name="molecular_fit_matrix",
        schema_model=TherapyEvidenceMatrixOutput,
        planned_artifact_id=artifact_id,
        payload={
            "evidence_context": context.model_dump(mode="json"),
            "molecular_phenotype": phenotype.model_dump(mode="json"),
        },
        source_artifact_ids=[*_context_source_ids(context), phenotype.artifact_id],
        source_file_id=context.extraction.source_file_id,
        model_provider=model_provider,
        model_name=model_name,
        prompts_root=prompts_root,
        created_at=created_at,
    )
    for row in result.artifact.rows:
        if not row.not_a_recommendation:
            raise StructuredArtifactGenerationError(
                "TherapyEvidenceMatrixOutput row is not marked not_a_recommendation"
            )
        if not row.required_validation.strip():
            raise StructuredArtifactGenerationError(
                "TherapyEvidenceMatrixOutput row is missing required_validation"
            )
    return result


async def generate_mechanism_sankey_with_model(
    *,
    context: EvidenceContextBundle,
    phenotype: MolecularPhenotypeOutput,
    matrix: TherapyEvidenceMatrixOutput,
    model_provider: object,
    model_name: str,
    prompts_root: Path,
    created_at: datetime,
) -> StructuredArtifactResult[MechanismSankeyOutput]:
    """Generate MechanismSankeyOutput through local vLLM structured output."""
    artifact_id = _artifact_id(context.artifact_id, "MechanismSankeyOutput")
    result = await _generate_artifact(
        prompt_name="mechanism_sankey",
        schema_model=MechanismSankeyOutput,
        planned_artifact_id=artifact_id,
        payload={
            "evidence_context": context.model_dump(mode="json"),
            "molecular_phenotype": phenotype.model_dump(mode="json"),
            "molecular_fit_matrix": matrix.model_dump(mode="json"),
        },
        source_artifact_ids=[*_context_source_ids(context), phenotype.artifact_id, matrix.artifact_id],
        source_file_id=context.extraction.source_file_id,
        model_provider=model_provider,
        model_name=model_name,
        prompts_root=prompts_root,
        created_at=created_at,
    )
    node_ids = {node.node_id for node in result.artifact.nodes}
    for link in result.artifact.links:
        if link.source_node_id not in node_ids or link.target_node_id not in node_ids:
            raise StructuredArtifactGenerationError(
                "MechanismSankeyOutput link references a missing node"
            )
    return result


async def generate_confirmatory_testing_with_model(
    *,
    context: EvidenceContextBundle,
    phenotype: MolecularPhenotypeOutput,
    matrix: TherapyEvidenceMatrixOutput,
    sankey: MechanismSankeyOutput,
    model_provider: object,
    model_name: str,
    prompts_root: Path,
    created_at: datetime,
) -> StructuredArtifactResult[ConfirmatoryTestingOutput]:
    """Generate ConfirmatoryTestingOutput through local vLLM structured output."""
    artifact_id = _artifact_id(context.artifact_id, "ConfirmatoryTestingOutput")
    return await _generate_artifact(
        prompt_name="confirmatory_testing",
        schema_model=ConfirmatoryTestingOutput,
        planned_artifact_id=artifact_id,
        payload={
            "evidence_context": context.model_dump(mode="json"),
            "molecular_phenotype": phenotype.model_dump(mode="json"),
            "molecular_fit_matrix": matrix.model_dump(mode="json"),
            "mechanism_sankey": sankey.model_dump(mode="json"),
        },
        source_artifact_ids=[
            *_context_source_ids(context),
            phenotype.artifact_id,
            matrix.artifact_id,
            sankey.artifact_id,
        ],
        source_file_id=context.extraction.source_file_id,
        model_provider=model_provider,
        model_name=model_name,
        prompts_root=prompts_root,
        created_at=created_at,
    )


async def generate_tumor_behavior_model_with_model(
    *,
    context: EvidenceContextBundle,
    phenotype: MolecularPhenotypeOutput,
    matrix: TherapyEvidenceMatrixOutput,
    sankey: MechanismSankeyOutput,
    confirmatory: ConfirmatoryTestingOutput,
    model_provider: object,
    model_name: str,
    prompts_root: Path,
    created_at: datetime,
) -> StructuredArtifactResult[TumorBehaviorModelOutput]:
    """Generate TumorBehaviorModelOutput through local vLLM structured output."""
    artifact_id = _artifact_id(context.artifact_id, "TumorBehaviorModelOutput")
    result = await _generate_artifact(
        prompt_name="tumor_behavior_model",
        schema_model=TumorBehaviorModelOutput,
        planned_artifact_id=artifact_id,
        payload={
            "evidence_context": context.model_dump(mode="json"),
            "molecular_phenotype": phenotype.model_dump(mode="json"),
            "molecular_fit_matrix": matrix.model_dump(mode="json"),
            "mechanism_sankey": sankey.model_dump(mode="json"),
            "confirmatory_testing": confirmatory.model_dump(mode="json"),
        },
        source_artifact_ids=[
            *_context_source_ids(context),
            phenotype.artifact_id,
            matrix.artifact_id,
            sankey.artifact_id,
            confirmatory.artifact_id,
        ],
        source_file_id=context.extraction.source_file_id,
        model_provider=model_provider,
        model_name=model_name,
        prompts_root=prompts_root,
        created_at=created_at,
    )
    for transition in result.artifact.transition_hypotheses:
        if not transition.hypothesis_generating:
            raise StructuredArtifactGenerationError(
                "TumorBehaviorModelOutput transition is not marked hypothesis_generating"
            )
    return result


async def generate_claim_evidence_with_model(
    *,
    context: EvidenceContextBundle,
    phenotype: MolecularPhenotypeOutput,
    matrix: TherapyEvidenceMatrixOutput,
    sankey: MechanismSankeyOutput,
    confirmatory: ConfirmatoryTestingOutput,
    tumor_behavior: TumorBehaviorModelOutput,
    model_provider: object,
    model_name: str,
    prompts_root: Path,
    created_at: datetime,
) -> StructuredArtifactResult[ClaimEvidenceListOutput]:
    """Generate ClaimEvidenceOutput list through local vLLM structured output."""
    artifact_id = _artifact_id(context.artifact_id, "ClaimEvidenceListOutput")
    result = await _generate_artifact(
        prompt_name="claim_evidence",
        schema_model=ClaimEvidenceListOutput,
        planned_artifact_id=artifact_id,
        payload={
            "evidence_context": context.model_dump(mode="json"),
            "molecular_phenotype": phenotype.model_dump(mode="json"),
            "molecular_fit_matrix": matrix.model_dump(mode="json"),
            "mechanism_sankey": sankey.model_dump(mode="json"),
            "confirmatory_testing": confirmatory.model_dump(mode="json"),
            "tumor_behavior_model": tumor_behavior.model_dump(mode="json"),
        },
        source_artifact_ids=[
            *_context_source_ids(context),
            phenotype.artifact_id,
            matrix.artifact_id,
            sankey.artifact_id,
            confirmatory.artifact_id,
            tumor_behavior.artifact_id,
        ],
        source_file_id=context.extraction.source_file_id,
        model_provider=model_provider,
        model_name=model_name,
        prompts_root=prompts_root,
        created_at=created_at,
    )
    for claim in result.artifact.claims:
        if claim.validation_status not in {"needs_review", "validated", "rejected"}:
            raise StructuredArtifactGenerationError(
                f"ClaimEvidenceOutput has invalid validation_status: {claim.validation_status}"
            )
    return result


async def generate_clinical_narrative_with_model(
    *,
    bundle: ClinicalArtifactBundle,
    model_provider: object,
    model_name: str,
    prompts_root: Path,
    created_at: datetime,
) -> StructuredArtifactResult[ClinicalNarrativeCompilerOutput]:
    """Generate ClinicalNarrativeCompilerOutput through local vLLM structured output."""
    source_ids = _bundle_source_ids(bundle)
    artifact_id = _artifact_id(bundle.session_id, "ClinicalNarrativeCompilerOutput")
    return await _generate_artifact(
        prompt_name="clinical_narrative",
        schema_model=ClinicalNarrativeCompilerOutput,
        planned_artifact_id=artifact_id,
        payload={"clinical_artifact_bundle": bundle.model_dump(mode="json")},
        source_artifact_ids=source_ids,
        source_file_id=bundle.extraction.source_file_id,
        model_provider=model_provider,
        model_name=model_name,
        prompts_root=prompts_root,
        created_at=created_at,
    )


class ClaimEvidenceListOutput(BaseModel):
    """Structured-output wrapper because the runtime stores claims as a list."""

    artifact_id: str
    claims: list[ClaimEvidenceOutput]


async def _generate_artifact(
    *,
    prompt_name: str,
    schema_model: type[T],
    planned_artifact_id: str,
    payload: Mapping[str, Any],
    source_artifact_ids: Sequence[str],
    source_file_id: str | None,
    model_provider: object,
    model_name: str,
    prompts_root: Path,
    created_at: datetime,
) -> StructuredArtifactResult[T]:
    prompts = _load_prompt_pair(prompts_root, prompt_name)
    user_prompt = prompts.user.format(
        planned_artifact_id=planned_artifact_id,
        payload_json=json.dumps(payload, sort_keys=True, indent=2),
    )
    schema = schema_model.model_json_schema()
    try:
        raw = await model_provider.structured_completion(
            model_name=model_name,
            system_prompt=prompts.system,
            user_prompt=user_prompt,
            schema_name=schema_model.__name__,
            json_schema=schema,
        )
        artifact = schema_model.model_validate(raw)
    except (ValidationError, ValueError, TypeError) as error:
        raise StructuredArtifactGenerationError(
            f"{schema_model.__name__} local structured output failed validation: {error}"
        ) from error
    _require_artifact_id(artifact, planned_artifact_id, schema_model.__name__)
    _validate_safety(artifact.model_dump_json())
    provenance = build_artifact_provenance(
        artifact_type=schema_model.__name__,
        schema_name=schema_model.__name__,
        model_name=model_name,
        prompt_text=f"{prompts.system}\n\n{user_prompt}",
        schema_json=schema,
        source_artifact_ids=list(source_artifact_ids),
        created_at=created_at,
        source_file_id=source_file_id,
        artifact_id=planned_artifact_id,
    )
    return StructuredArtifactResult(artifact=artifact, provenance=provenance)


def _load_prompt_pair(prompts_root: Path, prompt_name: str) -> PromptPair:
    system_path = prompts_root / f"{prompt_name}_system.md"
    user_path = prompts_root / f"{prompt_name}_user.md"
    if not system_path.exists() or not user_path.exists():
        missing = [str(path) for path in (system_path, user_path) if not path.exists()]
        raise StructuredArtifactGenerationError(
            f"missing structured-output prompt file(s) for {prompt_name}: {', '.join(missing)}"
        )
    return PromptPair(
        system=system_path.read_text(encoding="utf-8"),
        user=user_path.read_text(encoding="utf-8"),
    )


def _require_artifact_id(artifact: BaseModel, planned_artifact_id: str, schema_name: str) -> None:
    actual = getattr(artifact, "artifact_id", None)
    if actual != planned_artifact_id:
        raise StructuredArtifactGenerationError(
            f"{schema_name} returned artifact_id {actual!r}; expected {planned_artifact_id!r}"
        )


def _validate_safety(text: str) -> None:
    validate_safety_language(text, _BANNED_CLINICAL_PHRASES)


def _artifact_id(seed: str, artifact_type: str) -> str:
    return f"artifact_{uuid5(NAMESPACE_URL, f'{seed}:{artifact_type}').hex[:16]}"


def _context_source_ids(context: EvidenceContextBundle) -> list[str]:
    return [
        context.extraction.artifact_id,
        context.graph_evidence.artifact_id,
        *[tool.artifact_id for tool in context.tool_outputs],
        context.medea_reasoning.artifact_id,
    ]


def _bundle_source_ids(bundle: ClinicalArtifactBundle) -> list[str]:
    source_ids = [bundle.extraction.artifact_id]
    if bundle.entities is not None:
        source_ids.append(bundle.entities.artifact_id)
    if bundle.evidence_context is not None:
        source_ids.append(bundle.evidence_context.artifact_id)
    if bundle.phenotype is not None:
        source_ids.append(bundle.phenotype.artifact_id)
    if bundle.matrix is not None:
        source_ids.append(bundle.matrix.artifact_id)
    if bundle.sankey is not None:
        source_ids.append(bundle.sankey.artifact_id)
    if bundle.confirmatory is not None:
        source_ids.append(bundle.confirmatory.artifact_id)
    if bundle.tumor_behavior is not None:
        source_ids.append(bundle.tumor_behavior.artifact_id)
    source_ids.extend(claim.claim_id for claim in bundle.claims)
    return source_ids


def _require_retrieved_source_chunks(
    retrieved_chunks: Sequence[RetrievedDocumentChunk],
) -> list[RetrievedDocumentChunk]:
    """Return non-empty source chunks or fail loudly.

    Acceptance criteria:
        1. Requires at least one retrieved chunk.
        2. Requires every retained chunk to have source text.
        3. Preserves original retrieval metadata.
        4. Does not synthesize fallback source text.
    """
    source_chunks = [item for item in retrieved_chunks if item.chunk.source_text.strip()]
    if not source_chunks:
        raise StructuredArtifactGenerationError(
            "ReportExtractionOutput requires retrieved OpenSearch source chunks"
        )
    return source_chunks


def _retrieved_chunk_prompt_payload(item: RetrievedDocumentChunk) -> dict[str, object]:
    """Return source-grounding payload for one retrieved chunk."""
    return {
        "chunk_id": item.chunk.chunk_id,
        "page_start": item.chunk.page_start,
        "page_end": item.chunk.page_end,
        "section": item.chunk.section,
        "chunk_type": item.chunk.chunk_type,
        "source_text": item.chunk.source_text,
        "retrieval_method": item.retrieval_method,
        "score": item.score,
    }


def _source_align_report_extraction(
    extraction: ReportExtractionOutput,
    retrieved_chunks: Sequence[RetrievedDocumentChunk],
    *,
    report_type: str,
    source_file_id: str,
) -> ReportExtractionOutput:
    chunks = [item.chunk for item in retrieved_chunks]
    findings = [_source_align_finding(finding, chunks) for finding in extraction.molecular_findings]
    return extraction.model_copy(
        update={
            "report_type": report_type,
            "source_file_id": source_file_id,
            "molecular_findings": findings,
            "needs_human_review": True,
        }
    )


def _source_align_finding(
    finding: MolecularFinding,
    chunks: Sequence[DocumentChunk],
) -> MolecularFinding:
    matched = _match_source_chunk(finding, chunks)
    if matched is None:
        return finding.model_copy(
            update={
                "source_chunk_id": None,
                "source_page": None,
                "source_text": None,
                "confidence": min(float(finding.confidence), 0.25),
                "needs_human_review": True,
            }
        )
    source_text = _validated_or_generated_source_text(finding, matched)
    return finding.model_copy(
        update={
            "source_chunk_id": matched.chunk_id,
            "source_page": matched.page_start,
            "source_text": source_text,
            "needs_human_review": True,
        }
    )


def _validated_or_generated_source_text(
    finding: MolecularFinding,
    matched: DocumentChunk,
) -> str:
    if finding.source_text and _is_excerpt_of_chunk(finding.source_text, matched.source_text):
        return " ".join(finding.source_text.split())
    return _source_snippet(matched.source_text, finding)


def _match_source_chunk(
    finding: MolecularFinding,
    chunks: Sequence[DocumentChunk],
) -> DocumentChunk | None:
    if finding.source_chunk_id:
        for chunk in chunks:
            if chunk.chunk_id == finding.source_chunk_id:
                if _finding_supported_by_chunk(finding, chunk):
                    return chunk
                break
    best_score = 0
    best_chunk: DocumentChunk | None = None
    for chunk in chunks:
        score = _source_support_score(finding, chunk)
        if score > best_score:
            best_score = score
            best_chunk = chunk
    return best_chunk if best_score >= _minimum_support_score(finding) else None


def _finding_supported_by_chunk(finding: MolecularFinding, chunk: DocumentChunk) -> bool:
    return _source_support_score(finding, chunk) >= _minimum_support_score(finding)


def _source_support_score(finding: MolecularFinding, chunk: DocumentChunk) -> int:
    text = _normalize_for_match(chunk.source_text)
    score = 0
    if finding.source_text and _is_excerpt_of_chunk(finding.source_text, chunk.source_text):
        score += 4
    gene = finding.gene.strip() if finding.gene else ""
    if gene and _contains_token(text, gene):
        score += 3
    alteration_terms = _informative_terms(finding.alteration)
    score += min(3, sum(1 for term in alteration_terms if _contains_text(text, term)))
    type_terms = _informative_terms(finding.alteration_type.replace("_", " "))
    score += min(1, sum(1 for term in type_terms if _contains_text(text, term)))
    return score


def _minimum_support_score(finding: MolecularFinding) -> int:
    if finding.source_text:
        return 4
    if finding.gene:
        return 4
    return 2


def _is_excerpt_of_chunk(excerpt: str, chunk_text: str) -> bool:
    normalized_excerpt = _normalize_whitespace(excerpt).casefold()
    normalized_chunk = _normalize_whitespace(chunk_text).casefold()
    return bool(normalized_excerpt) and normalized_excerpt in normalized_chunk


def _source_snippet(text: str, finding: MolecularFinding, window: int = 280) -> str:
    terms = [term for term in [finding.gene, *_informative_terms(finding.alteration)] if term]
    lower = text.casefold()
    positions = [lower.find(term.casefold()) for term in terms if lower.find(term.casefold()) >= 0]
    if not positions:
        return " ".join(text[:window].split())
    start_at = min(positions)
    start = max(0, start_at - window // 2)
    end = min(len(text), start_at + window // 2)
    return " ".join(text[start:end].split())


def _validate_report_extraction_grounding(
    extraction: ReportExtractionOutput,
    retrieved_chunks: Sequence[RetrievedDocumentChunk],
) -> None:
    """Validate report extraction remains source-grounded and reviewable.

    Acceptance criteria:
        1. Every molecular finding remains needs_human_review=true.
        2. Source-aligned findings quote/excerpt a retrieved chunk.
        3. Unsupported findings are low confidence.
        4. Report extraction does not contain non-source-backed confident
           patient-specific molecular claims.
    """
    chunk_map = {item.chunk.chunk_id: item.chunk for item in retrieved_chunks}
    for finding in extraction.molecular_findings:
        if not finding.needs_human_review:
            raise StructuredArtifactGenerationError(
                "ReportExtractionOutput finding is not marked needs_human_review"
            )
        if finding.source_chunk_id is None or finding.source_text is None:
            if float(finding.confidence) > 0.25:
                raise StructuredArtifactGenerationError(
                    "ReportExtractionOutput has unsupported finding above low-confidence threshold"
                )
            continue
        chunk = chunk_map.get(finding.source_chunk_id)
        if chunk is None:
            raise StructuredArtifactGenerationError(
                "ReportExtractionOutput finding references unknown source_chunk_id"
            )
        if not _is_excerpt_of_chunk(finding.source_text, chunk.source_text):
            raise StructuredArtifactGenerationError(
                "ReportExtractionOutput finding source_text is not in the retrieved chunk"
            )


def _normalize_for_match(value: str) -> str:
    return _normalize_whitespace(value).casefold()


def _normalize_whitespace(value: str) -> str:
    return " ".join(value.split())


def _contains_token(normalized_text: str, token: str) -> bool:
    return re.search(rf"(?<![A-Za-z0-9]){re.escape(token.casefold())}(?![A-Za-z0-9])", normalized_text) is not None


def _contains_text(normalized_text: str, term: str) -> bool:
    return term.casefold() in normalized_text


def _informative_terms(value: str) -> list[str]:
    terms = []
    for raw in re.split(r"[^A-Za-z0-9+._-]+", value):
        term = raw.strip()
        if len(term) < 3:
            continue
        if term.casefold() in _GENERIC_REPORT_EXTRACTION_TERMS:
            continue
        terms.append(term)
    return list(dict.fromkeys(terms))


_GENERIC_REPORT_EXTRACTION_TERMS = {
    "and",
    "the",
    "with",
    "without",
    "variant",
    "variants",
    "alteration",
    "alterations",
    "copy",
    "number",
    "expression",
    "rna",
    "dna",
    "loss",
    "gain",
    "high",
    "low",
    "detected",
    "reported",
    "present",
    "absent",
}
