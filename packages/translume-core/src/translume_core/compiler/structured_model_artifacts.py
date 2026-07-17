from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Generic, TypeVar
from uuid import NAMESPACE_URL, uuid5

from pydantic import BaseModel, Field, StringConstraints, ValidationError

from translume_core.compiler.mechanism_sankey import (
    generate_mechanism_sankey_from_context,
)
from translume_core.provenance.hashing import stable_json_hash
from translume_core.provenance.provenance import build_artifact_provenance
from translume_core.safety.language import validate_safety_language
from translume_ports.model_provider import ModelOutputTruncatedError
from translume_schemas.claims import ClaimEvidenceOutput
from translume_schemas.confirmatory import ConfirmatoryTest, ConfirmatoryTestingOutput
from translume_schemas.decision_brief import OncologistDecisionBrief
from translume_schemas.document import DocumentChunk, RetrievedDocumentChunk
from translume_schemas.evidence import EvidenceContextBundle
from translume_schemas.export import ClinicalArtifactBundle, ClinicalNarrativeCompilerOutput
from translume_schemas.extraction import MolecularFinding, ReportExtractionOutput
from translume_schemas.matrix import TherapyEvidenceMatrixOutput
from translume_schemas.phenotype import MolecularPhenotypeOutput
from translume_schemas.provenance import ArtifactProvenance
from translume_schemas.sankey import MechanismSankeyOutput
from translume_schemas.tumor_behavior import STATE_LABELS, TumorBehaviorModelOutput


T = TypeVar("T", bound=BaseModel)

_BANNED_UNSUPPORTED_CERTAINTY_PHRASES = [
    "will be cured"
]

_VAGUE_NARRATIVE_ALTERATION = re.compile(
    r"\b(?P<prefix>"
    r"the|this|that|a|an|any|identified|detected|observed|noted|"
    r"reported|described"
    r")\s+"
    r"(?P<term>mutation|variant|amplification|deletion|fusion|"
    r"overexpression|underexpression|rearrangement|splicing)\b",
    re.IGNORECASE,
)
_MAX_PROMPT_FINDINGS = 20
_MAX_PROMPT_GRAPH_NODES = 25
_MAX_PROMPT_GRAPH_EDGES = 50
_MAX_PROMPT_TOOL_OUTPUTS = 8
_MAX_PROMPT_TOOL_EVIDENCE_ITEMS = 5
_MAX_PROMPT_EVIDENCE_ITEM_FIELDS = 6
_MAX_PROMPT_RETRIEVED_CHUNKS = 20
_REPORT_EXTRACTION_BATCH_MAX_CHUNKS = 5
_REPORT_EXTRACTION_CRITICAL_CHUNK_MIN_SCORE = 25
_MAX_PROMPT_SOURCE_TEXT_CHARS = 700
_REPORT_EXTRACTION_SOURCE_UNIT_CHARS = 400
_MAX_PROMPT_SUMMARY_CHARS = 1200
_MAX_PROMPT_MISC_TEXT_CHARS = 500
_MAX_PROMPT_MEDEA_SUMMARY_CHARS = 1600
_MAX_PROMPT_HYPOTHESES = 10
_MAX_PROMPT_GENERATED_TEXT_CHARS = 700
_MAX_PROMPT_AXES = 12
_MAX_PROMPT_MATRIX_ROWS = 12
_MAX_PROMPT_SANKEY_NODES = 30
_MAX_PROMPT_SANKEY_LINKS = 60
_MAX_PROMPT_CONFIRMATORY_TESTS = 12
_MAX_PROMPT_CONFIRMATORY_INPUT_FINDINGS = 4
_MAX_PROMPT_CONFIRMATORY_INPUT_GRAPH_NODES = 3
_MAX_PROMPT_CONFIRMATORY_INPUT_GRAPH_EDGES = 4
_MAX_PROMPT_CONFIRMATORY_INPUT_TOOL_OUTPUTS = 1
_MAX_PROMPT_CONFIRMATORY_INPUT_AXES = 2
_MAX_PROMPT_CONFIRMATORY_INPUT_MATRIX_ROWS = 2
_MAX_PROMPT_CONFIRMATORY_INPUT_SANKEY_NODES = 4
_MAX_PROMPT_CONFIRMATORY_INPUT_SANKEY_LINKS = 4
_MAX_PROMPT_CONFIRMATORY_PAYLOAD_CHARS = 12000
_MAX_PROMPT_TUMOR_STATES = 10
_MAX_PROMPT_TRANSITIONS = 10
_MAX_PROMPT_CLAIMS = 20
_MAX_PROMPT_SUPPORT_IDS = 30
_MAX_PROMPT_SANKEY_INPUT_FINDINGS = 6
_MAX_PROMPT_SANKEY_INPUT_GRAPH_NODES = 8
_MAX_PROMPT_SANKEY_INPUT_GRAPH_EDGES = 10
_MAX_PROMPT_SANKEY_INPUT_TOOL_OUTPUTS = 2


_MAX_PROMPT_SANKEY_INPUT_TOOL_EVIDENCE_ITEMS = 1
_MAX_PROMPT_SANKEY_INPUT_HYPOTHESES = 4
_MAX_PROMPT_SANKEY_INPUT_AXES = 3
_MAX_PROMPT_SANKEY_INPUT_MATRIX_ROWS = 2
_MAX_PROMPT_SANKEY_INPUT_TEXT_CHARS = 120
_MAX_PROMPT_SANKEY_INPUT_SUMMARY_CHARS = 200
_MAX_PROMPT_PHENOTYPE_FINDINGS = 10
_MAX_PROMPT_PHENOTYPE_GRAPH_NODES = 8
_MAX_PROMPT_PHENOTYPE_GRAPH_EDGES = 12
_MAX_PROMPT_PHENOTYPE_TOOL_OUTPUTS = 4
_MAX_PROMPT_PHENOTYPE_TOOL_EVIDENCE_ITEMS = 1
_MAX_PROMPT_PHENOTYPE_HYPOTHESES = 4
_MAX_PROMPT_PHENOTYPE_TEXT_CHARS = 160
_MAX_PROMPT_PHENOTYPE_SUMMARY_CHARS = 500
_MAX_PROMPT_CLAIM_INPUT_FINDINGS = 8
_MAX_PROMPT_CLAIM_INPUT_GRAPH_NODES = 6
_MAX_PROMPT_CLAIM_INPUT_GRAPH_EDGES = 8
_MAX_PROMPT_CLAIM_INPUT_TOOL_OUTPUTS = 3
_MAX_PROMPT_CLAIM_INPUT_TOOL_EVIDENCE_ITEMS = 1
_MAX_PROMPT_CLAIM_INPUT_HYPOTHESES = 4
_MAX_PROMPT_CLAIM_INPUT_AXES = 4
_MAX_PROMPT_CLAIM_INPUT_MATRIX_ROWS = 3
_MAX_PROMPT_CLAIM_INPUT_SANKEY_NODES = 8
_MAX_PROMPT_CLAIM_INPUT_SANKEY_LINKS = 8
_MAX_PROMPT_CLAIM_INPUT_CONFIRMATORY_TESTS = 3
_MAX_PROMPT_CLAIM_INPUT_TUMOR_STATES = 3
_MAX_PROMPT_CLAIM_INPUT_TRANSITIONS = 2
_MAX_PROMPT_CLAIM_INPUT_TEXT_CHARS = 120
_MAX_PROMPT_CLAIM_INPUT_SUMMARY_CHARS = 300
_MAX_PROMPT_TUMOR_INPUT_FINDINGS = 8
_MAX_PROMPT_TUMOR_INPUT_GRAPH_NODES = 8
_MAX_PROMPT_TUMOR_INPUT_GRAPH_EDGES = 10
_MAX_PROMPT_TUMOR_INPUT_TOOL_OUTPUTS = 3
_MAX_PROMPT_TUMOR_INPUT_TOOL_EVIDENCE_ITEMS = 1
_MAX_PROMPT_TUMOR_INPUT_HYPOTHESES = 4
_MAX_PROMPT_TUMOR_INPUT_AXES = 4
_MAX_PROMPT_TUMOR_INPUT_MATRIX_ROWS = 4
_MAX_PROMPT_TUMOR_INPUT_SANKEY_NODES = 10
_MAX_PROMPT_TUMOR_INPUT_SANKEY_LINKS = 10
_MAX_PROMPT_TUMOR_INPUT_CONFIRMATORY_TESTS = 4
_MAX_PROMPT_TUMOR_INPUT_TEXT_CHARS = 140
_MAX_PROMPT_TUMOR_INPUT_SUMMARY_CHARS = 360
_MAX_PROMPT_TUMOR_SUPPORT_ID_CHARS = 160
_MAX_PROMPT_TUMOR_BEHAVIOR_PAYLOAD_CHARS = 40000
_MAX_PROMPT_NARRATIVE_FINDINGS = 6
_MAX_PROMPT_NARRATIVE_AXES = 3
_MAX_PROMPT_NARRATIVE_MATRIX_ROWS = 2
_MAX_PROMPT_NARRATIVE_SANKEY_NODES = 6
_MAX_PROMPT_NARRATIVE_SANKEY_LINKS = 6
_MAX_PROMPT_NARRATIVE_CONFIRMATORY_TESTS = 2
_MAX_PROMPT_NARRATIVE_TUMOR_STATES = 2
_MAX_PROMPT_NARRATIVE_TRANSITIONS = 2
_MAX_PROMPT_NARRATIVE_DECISION_ROWS = 1
_MAX_PROMPT_NARRATIVE_CLAIMS = 3
_MAX_PROMPT_NARRATIVE_TEXT_CHARS = 80
_MAX_PROMPT_NARRATIVE_SUMMARY_CHARS = 220
_PROMPT_CONTEXT_CAP_NOTICE = (
    "Context is relevance-capped for prompt length. Missing graph nodes, "
    "edges, tool rows, or reasoning items must not be interpreted as absent "
    "biological evidence."
)
_STRUCTURED_OUTPUT_MAX_ATTEMPTS = 2
_REPAIR_PROMPT_TEXT_CHARS = 6000


class StructuredArtifactGenerationError(RuntimeError):
    """Raised when local structured-output artifact generation fails.

    Acceptance criteria:
        1. Represents failure rather than substituting a fallback artifact.
        2. Carries the failed schema name or prompt name in the message.
        3. Is raised for invalid JSON, schema mismatch, unsafe text, or ID
           mismatch.
    """


class IrreducibleReportExtractionTruncationError(
    StructuredArtifactGenerationError
):
    """Raised when a report batch cannot be safely subdivided further."""


class _BoundedMolecularFinding(MolecularFinding):
    """Bound one leaf finding while retaining the public finding contract."""

    finding_id: str = Field(max_length=160)
    gene: str | None = Field(default=None, max_length=80)
    alteration: str = Field(max_length=200)
    alteration_type: str = Field(max_length=80)
    source_text: str | None = Field(default=None, max_length=300)
    source_chunk_id: str | None = Field(default=None, max_length=120)


_BoundedLeafText = Annotated[str, StringConstraints(max_length=300)]


class _BoundedReportExtractionOutput(ReportExtractionOutput):
    """Bound one model leaf without limiting the merged report artifact."""

    artifact_id: str = Field(max_length=160)
    report_type: str = Field(max_length=80)
    disease: str | None = Field(default=None, max_length=500)
    specimen: str | None = Field(default=None, max_length=500)
    tumor_percentage: str | None = Field(default=None, max_length=120)
    molecular_findings: list[_BoundedMolecularFinding] = Field(max_length=8)
    negative_findings: list[_BoundedLeafText] = Field(
        default_factory=list,
        max_length=6,
    )
    assay_limitations: list[_BoundedLeafText] = Field(
        default_factory=list,
        max_length=6,
    )
    source_file_id: str = Field(max_length=160)


class _BoundedConfirmatoryTest(ConfirmatoryTest):
    """Bound one generated validation-test row."""

    test_id: str = Field(max_length=120)
    question: str = Field(max_length=500)
    why_it_matters: str = Field(max_length=700)
    positive_interpretation: str = Field(max_length=700)
    negative_interpretation: str = Field(max_length=700)
    priority: str = Field(max_length=80)
    evidence_gap: str = Field(max_length=700)
    source_claim_ids: list[Annotated[str, StringConstraints(max_length=160)]] = (
        Field(default_factory=list, max_length=20)
    )


class _BoundedConfirmatoryTestingOutput(ConfirmatoryTestingOutput):
    """Bound model generation without limiting downstream public types."""

    artifact_id: str = Field(max_length=160)
    tests: list[_BoundedConfirmatoryTest] = Field(max_length=12)
    must_not_assume: list[
        Annotated[str, StringConstraints(max_length=500)]
    ] = Field(default_factory=list, max_length=12)


class InvalidMechanismSankeyError(StructuredArtifactGenerationError):
    """Raised when a schema-valid mechanism graph violates graph invariants."""


@dataclass(frozen=True)
class StructuredArtifactResult(Generic[T]):
    """A schema-validated clinical artifact plus its provenance."""

    artifact: T
    provenance: ArtifactProvenance


@dataclass(frozen=True)
class _StructuredArtifactAttemptResult(Generic[T]):
    """Schema-valid model output plus successful prompt metadata."""

    artifact: T
    user_prompt: str
    attempts: int


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
    batch_max_chunks: int = _REPORT_EXTRACTION_BATCH_MAX_CHUNKS,
    input_token_budget: int = 2200,
    initial_max_tokens: int = 2500,
    retry_max_tokens: int = 5000,
    max_split_depth: int = 6,
    min_segment_chars: int = 400,
) -> StructuredArtifactResult[ReportExtractionOutput]:
    """Generate source-grounded ReportExtractionOutput through local vLLM.

    Acceptance criteria:
        1. Uses retrieved OpenSearch chunks, not raw in-memory page text.
        2. Fails if no retrieved source chunks are available.
        3. Processes the full retrieved report in bounded, page-ordered batches.
        4. Preserves clinically critical sections from long NGS reports rather
           than keeping only the first prompt window.
        5. Validates each raw model response as ReportExtractionOutput.
        6. Requires returned artifact IDs to match the planned artifact ID.
        7. Source-aligns each molecular finding back to retrieved chunks.
        8. Forces every finding to remain human-reviewable.
        9. Downgrades unsupported findings rather than presenting them as
           confident patient-specific facts.
       10. Does not add graph, literature, treatment, or tumor-behavior
           inference.
    """
    source_chunks = _require_retrieved_source_chunks(retrieved_chunks)
    prompt_source_units = _segment_report_chunks_for_prompt(source_chunks)
    planned_artifact_id = _artifact_id(source_file_id, "ReportExtractionOutput")
    prompt_batches = await _plan_token_bounded_report_extraction_batches(
        prompt_source_units,
        model_provider=model_provider,
        model_name=model_name,
        input_token_budget=input_token_budget,
        batch_max_chunks=batch_max_chunks,
    )
    batch_artifacts: list[ReportExtractionOutput] = []
    for batch_index, prompt_chunks in enumerate(prompt_batches):
        leaf_artifacts = await _generate_report_extraction_adaptively(
            prompt_chunks=prompt_chunks,
            all_source_chunks=source_chunks,
            planned_artifact_id=planned_artifact_id,
            report_type=report_type,
            source_file_id=source_file_id,
            model_provider=model_provider,
            model_name=model_name,
            prompts_root=prompts_root,
            created_at=created_at,
            batch_index=batch_index,
            total_batches=len(prompt_batches),
            initial_max_tokens=initial_max_tokens,
            retry_max_tokens=retry_max_tokens,
            max_split_depth=max_split_depth,
            min_segment_chars=min_segment_chars,
            depth=0,
        )
        batch_artifacts.extend(leaf_artifacts)
    merged = _merge_report_extraction_batches(
        batch_artifacts,
        planned_artifact_id=planned_artifact_id,
        report_type=report_type,
        source_file_id=source_file_id,
    )
    aligned = _source_align_report_extraction(
        merged,
        source_chunks,
        report_type=report_type,
        source_file_id=source_file_id,
    )
    _validate_report_extraction_grounding(aligned, source_chunks)
    _validate_safety(aligned.model_dump_json())
    provenance = build_artifact_provenance(
        artifact_type="ReportExtractionOutput",
        schema_name="ReportExtractionOutput",
        model_name=model_name,
        prompt_text=json.dumps(
            _report_extraction_planner_summary(
                source_chunks,
                prompt_batches,
                batch_max_chunks=batch_max_chunks,
            ),
            sort_keys=True,
        ),
        schema_json=ReportExtractionOutput.model_json_schema(),
        source_artifact_ids=[item.chunk.chunk_id for item in source_chunks],
        source_chunk_ids=[item.chunk.chunk_id for item in source_chunks],
        source_file_id=source_file_id,
        created_at=created_at,
        generation_status=(
            "batched_model_extraction" if len(prompt_batches) > 1 else "generated"
        ),
        artifact_id=planned_artifact_id,
    )
    return StructuredArtifactResult(artifact=aligned, provenance=provenance)


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
    compact_context = compact_evidence_context_for_molecular_phenotype_prompt(
        context
    )
    return await _generate_artifact(
        prompt_name="molecular_phenotype",
        schema_model=MolecularPhenotypeOutput,
        planned_artifact_id=artifact_id,
        payload={"evidence_context": compact_context},
        source_artifact_ids=_context_source_ids(context),
        source_chunk_ids=_context_source_chunk_ids(context),
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
    compact_context = compact_evidence_context_for_prompt(context)
    result = await _generate_artifact(
        prompt_name="molecular_fit_matrix",
        schema_model=TherapyEvidenceMatrixOutput,
        planned_artifact_id=artifact_id,
        payload={
            "evidence_context": compact_context,
            "molecular_phenotype": compact_phenotype_for_prompt(phenotype),
        },
        source_artifact_ids=[*_context_source_ids(context), phenotype.artifact_id],
        source_chunk_ids=_context_source_chunk_ids(context),
        source_file_id=context.extraction.source_file_id,
        model_provider=model_provider,
        model_name=model_name,
        prompts_root=prompts_root,
        created_at=created_at,
    )
    _validate_molecular_fit_matrix_decision_support(result.artifact)
    return result


def _validate_molecular_fit_matrix_decision_support(
    matrix: TherapyEvidenceMatrixOutput,
) -> None:
    """Validate matrix rows as evidence-grounded decision support.

    Acceptance criteria:
        1. Every row has a clinical-use category instead of a blanket
           not-a-recommendation flag.
        2. Every row has evidence and limitations.
        3. Every row explains validation or before-use testing requirements.
        4. Unsupported certainty language is rejected.

    Args:
        matrix: Model-generated therapy evidence matrix.

    Raises:
        StructuredArtifactGenerationError: If evidence or safety fields are
            missing.
    """
    if not matrix.rows:
        raise StructuredArtifactGenerationError(
            "TherapyEvidenceMatrixOutput requires at least one row"
        )
    for row in matrix.rows:
        if not row.evidence_basis.strip() and not row.evidence_level.strip():
            raise StructuredArtifactGenerationError(
                "TherapyEvidenceMatrixOutput row is missing evidence support"
            )
        if not row.limitations.strip():
            raise StructuredArtifactGenerationError(
                "TherapyEvidenceMatrixOutput row is missing limitations"
            )
        if not (row.required_validation.strip() or row.required_before_use_tests):
            raise StructuredArtifactGenerationError(
                "TherapyEvidenceMatrixOutput row is missing required validation "
                "or required-before-use tests"
            )
        _validate_safety(row.model_dump_json())


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
    compact_context = compact_evidence_context_for_mechanism_sankey_prompt(
        context
    )
    source_artifact_ids = [
        *_context_source_ids(context),
        phenotype.artifact_id,
        matrix.artifact_id,
    ]
    try:
        result = await _generate_artifact(
            prompt_name="mechanism_sankey",
            schema_model=MechanismSankeyOutput,
            planned_artifact_id=artifact_id,
            payload={
                "evidence_context": compact_context,
                "molecular_phenotype": compact_phenotype_for_sankey_prompt(
                    phenotype
                ),
                "molecular_fit_matrix": compact_matrix_for_sankey_prompt(
                    matrix
                ),
            },
            source_artifact_ids=source_artifact_ids,
            source_chunk_ids=_context_source_chunk_ids(context),
            source_file_id=context.extraction.source_file_id,
            model_provider=model_provider,
            model_name=model_name,
            prompts_root=prompts_root,
            created_at=created_at,
            artifact_validator=_normalize_and_validate_mechanism_sankey,
        )
    except StructuredArtifactGenerationError as error:
        if not (
            _is_structured_output_timeout(error)
            or _contains_invalid_mechanism_sankey_error(error)
        ):
            raise
        result = _generate_mechanism_sankey_fallback(
            context=context,
            phenotype=phenotype,
            matrix=matrix,
            planned_artifact_id=artifact_id,
            source_artifact_ids=source_artifact_ids,
            source_chunk_ids=_context_source_chunk_ids(context),
            created_at=created_at,
        )
    return StructuredArtifactResult(
        artifact=result.artifact,
        provenance=result.provenance,
    )


def _generate_mechanism_sankey_fallback(
    *,
    context: EvidenceContextBundle,
    phenotype: MolecularPhenotypeOutput,
    matrix: TherapyEvidenceMatrixOutput,
    planned_artifact_id: str,
    source_artifact_ids: Sequence[str],
    source_chunk_ids: Sequence[str],
    created_at: datetime,
) -> StructuredArtifactResult[MechanismSankeyOutput]:
    """Return deterministic Sankey output after a recoverable model failure.

    Acceptance criteria:
        1. Determinism: Same context, phenotype, matrix, and timestamp return
           equivalent artifact and provenance values.
        2. No mutation: Do not mutate caller-owned schema models or ID lists.
        3. Scope: Use this only for timeout or invalid-graph handling.
        4. Auditability: Mark provenance as `deterministic_fallback`.
        5. Contract: The returned artifact ID matches the planned artifact ID.

    Args:
        context: Combined evidence context.
        phenotype: Molecular phenotype artifact.
        matrix: Molecular-fit matrix artifact.
        planned_artifact_id: Artifact ID reserved for this workflow stage.
        source_artifact_ids: Source artifacts used by provenance.
        source_chunk_ids: Source chunks used by provenance.
        created_at: Timestamp for provenance.

    Returns:
        Deterministic Sankey result with fallback provenance.
    """
    fallback = generate_mechanism_sankey_from_context(
        context,
        phenotype,
        matrix,
    ).model_copy(update={"artifact_id": planned_artifact_id})
    _validate_safety(fallback.model_dump_json())
    provenance = build_artifact_provenance(
        artifact_type="MechanismSankeyOutput",
        schema_name="MechanismSankeyOutput",
        model_name="mechanism_sankey_deterministic_fallback",
        prompt_text=None,
        schema_json=MechanismSankeyOutput.model_json_schema(),
        source_artifact_ids=list(source_artifact_ids),
        source_chunk_ids=list(source_chunk_ids),
        created_at=created_at,
        source_file_id=context.extraction.source_file_id,
        generation_status="deterministic_fallback",
        artifact_id=planned_artifact_id,
    )
    return StructuredArtifactResult(artifact=fallback, provenance=provenance)


def _is_structured_output_timeout(
    error: StructuredArtifactGenerationError,
) -> bool:
    """Return whether a structured-output failure came from a timeout.

    Acceptance criteria:
        1. Determinism: Same exception chain returns the same boolean.
        2. No mutation: Do not mutate exception objects.
        3. Narrowness: Match timeout wording from provider errors only.
        4. Safety: Non-timeout provider and validation errors return `False`.

    Args:
        error: Structured artifact generation failure.

    Returns:
        `True` when the error or chained cause carries timeout wording.
    """
    return _contains_timeout_wording(error)


def _contains_timeout_wording(error: BaseException) -> bool:
    """Return whether an exception chain contains timeout wording."""
    messages = [
        str(item)
        for item in (error, error.__cause__, error.__context__)
        if item is not None
    ]
    return any(
        "timed out" in message.casefold()
        or "readtimeout" in message.casefold()
        for message in messages
    )


def _contains_invalid_mechanism_sankey_error(error: BaseException) -> bool:
    """Return whether an exception chain contains a mechanism graph failure."""
    return any(
        isinstance(item, InvalidMechanismSankeyError)
        for item in (error, error.__cause__, error.__context__)
        if item is not None
    )


def _normalize_and_validate_mechanism_sankey(
    sankey: MechanismSankeyOutput,
) -> MechanismSankeyOutput:
    """Return Sankey output with unique nodes and valid links.

    Acceptance criteria:
        1. Determinism: Same Sankey artifact always produces equivalent output.
        2. No mutation: Do not mutate nodes or links.
        3. Deduplication: Exact duplicate node records are collapsed.
        4. Validation: Conflicting duplicate node IDs raise
           `StructuredArtifactGenerationError`.
        5. Validation: Links must reference existing unique node IDs.

    Args:
        sankey: Mechanism Sankey artifact to normalize and validate.

    Returns:
        A copied Sankey artifact with unique nodes.

    Raises:
        StructuredArtifactGenerationError: If duplicate node IDs conflict or
            any link references a missing node ID.
    """
    nodes = []
    node_fingerprints: dict[str, tuple[str, str, str]] = {}
    for node in sankey.nodes:
        fingerprint = (node.label, node.kind, node.evidence_class)
        existing = node_fingerprints.get(node.node_id)
        if existing is None:
            node_fingerprints[node.node_id] = fingerprint
            nodes.append(node)
            continue
        if existing != fingerprint:
            raise InvalidMechanismSankeyError(
                "MechanismSankeyOutput duplicate node_id has conflicting "
                f"content: {node.node_id}"
            )
    normalized = sankey.model_copy(update={"nodes": nodes})
    _validate_mechanism_sankey_links(normalized)
    return normalized


def _validate_mechanism_sankey_links(
    sankey: MechanismSankeyOutput,
) -> None:
    """Fail when a Sankey link references a missing node.

    Acceptance criteria:
        1. Determinism: Same Sankey artifact always produces the same result.
        2. No mutation: Do not mutate nodes or links.
        3. Validation: Raise `StructuredArtifactGenerationError` for missing
           source or target nodes.

    Args:
        sankey: Mechanism Sankey artifact to validate.

    Raises:
        StructuredArtifactGenerationError: If any link references a missing
            node ID.
    """
    node_ids = {node.node_id for node in sankey.nodes}
    for link in sankey.links:
        if (
            link.source_node_id not in node_ids
            or link.target_node_id not in node_ids
        ):
            raise InvalidMechanismSankeyError(
                "MechanismSankeyOutput link references a missing node"
            )


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
    input_token_budget: int = 8000,
) -> StructuredArtifactResult[ConfirmatoryTestingOutput]:
    """Generate ConfirmatoryTestingOutput through local vLLM structured output."""
    artifact_id = _artifact_id(context.artifact_id, "ConfirmatoryTestingOutput")
    payload = _require_confirmatory_testing_payload_bound(
        {
            "evidence_context": (
                compact_evidence_context_for_confirmatory_testing_prompt(
                    context
                )
            ),
            "molecular_phenotype": (
                compact_phenotype_for_confirmatory_testing_prompt(phenotype)
            ),
            "molecular_fit_matrix": (
                compact_matrix_for_confirmatory_testing_prompt(matrix)
            ),
            "mechanism_sankey": (
                compact_sankey_for_confirmatory_testing_prompt(sankey)
            ),
        }
    )
    result = await _generate_artifact(
        prompt_name="confirmatory_testing",
        schema_model=_BoundedConfirmatoryTestingOutput,
        planned_artifact_id=artifact_id,
        payload=payload,
        source_artifact_ids=[
            *_context_source_ids(context),
            phenotype.artifact_id,
            matrix.artifact_id,
            sankey.artifact_id,
        ],
        source_chunk_ids=_context_source_chunk_ids(context),
        source_file_id=context.extraction.source_file_id,
        model_provider=model_provider,
        model_name=model_name,
        prompts_root=prompts_root,
        created_at=created_at,
        input_token_budget=input_token_budget,
    )
    return StructuredArtifactResult(
        artifact=ConfirmatoryTestingOutput.model_validate(
            result.artifact.model_dump()
        ),
        provenance=_canonicalize_provenance_schema(
            result.provenance,
            ConfirmatoryTestingOutput,
        ),
    )


def _canonicalize_provenance_schema(
    provenance: ArtifactProvenance,
    public_schema: type[BaseModel],
) -> ArtifactProvenance:
    """Return provenance labeled and hashed with its public artifact schema.

    Acceptance criteria:
        1. Schema name and hash describe the public persisted artifact type.
        2. All generation, source, prompt, model, and timestamp fields remain.
        3. The caller-owned provenance record is not mutated.
    """
    schema_name = public_schema.__name__
    return provenance.model_copy(
        update={
            "artifact_type": schema_name,
            "schema_name": schema_name,
            "schema_hash": stable_json_hash(public_schema.model_json_schema()),
        }
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
    payload = compact_tumor_behavior_inputs_for_prompt(
        context=context,
        phenotype=phenotype,
        matrix=matrix,
        sankey=sankey,
        confirmatory=confirmatory,
    )
    source_artifact_ids = [
        *_context_source_ids(context),
        phenotype.artifact_id,
        matrix.artifact_id,
        sankey.artifact_id,
        confirmatory.artifact_id,
    ]
    result = await _generate_artifact(
        prompt_name="tumor_behavior_model",
        schema_model=TumorBehaviorModelOutput,
        planned_artifact_id=artifact_id,
        payload=payload,
        source_artifact_ids=source_artifact_ids,
        source_chunk_ids=_context_source_chunk_ids(context),
        source_file_id=context.extraction.source_file_id,
        model_provider=model_provider,
        model_name=model_name,
        prompts_root=prompts_root,
        created_at=created_at,
    )
    try:
        normalized_artifact = _normalize_and_validate_tumor_behavior(
            result.artifact,
            context=context,
            phenotype=phenotype,
            matrix=matrix,
            sankey=sankey,
            confirmatory=confirmatory,
        )
    except StructuredArtifactGenerationError as error:
        if not _is_repairable_tumor_behavior_validation_error(error):
            raise
        case_terms = _tumor_behavior_case_terms(
            context=context,
            phenotype=phenotype,
            matrix=matrix,
            sankey=sankey,
            confirmatory=confirmatory,
        )
        required_mims_support_ids = _available_mims_support_ids(context)
        allowed_evidence_ids = _tumor_behavior_allowed_evidence_ids(
            context=context,
            phenotype=phenotype,
            matrix=matrix,
            sankey=sankey,
            confirmatory=confirmatory,
        )
        result = await _generate_artifact(
            prompt_name="tumor_behavior_model",
            schema_model=TumorBehaviorModelOutput,
            planned_artifact_id=artifact_id,
            payload=_tumor_behavior_validation_repair_payload(
                payload,
                error=error,
                case_terms=case_terms,
                allowed_evidence_ids=allowed_evidence_ids,
                required_mims_support_ids=required_mims_support_ids,
            ),
            source_artifact_ids=source_artifact_ids,
            source_chunk_ids=_context_source_chunk_ids(context),
            source_file_id=context.extraction.source_file_id,
            model_provider=model_provider,
            model_name=model_name,
            prompts_root=prompts_root,
            created_at=created_at,
        )
        normalized_artifact = _normalize_and_validate_tumor_behavior(
            result.artifact,
            context=context,
            phenotype=phenotype,
            matrix=matrix,
            sankey=sankey,
            confirmatory=confirmatory,
        )
    return StructuredArtifactResult(
        artifact=normalized_artifact,
        provenance=result.provenance,
    )


def _normalize_and_validate_tumor_behavior(
    tumor_behavior: TumorBehaviorModelOutput,
    *,
    context: EvidenceContextBundle,
    phenotype: MolecularPhenotypeOutput,
    matrix: TherapyEvidenceMatrixOutput,
    sankey: MechanismSankeyOutput,
    confirmatory: ConfirmatoryTestingOutput,
) -> TumorBehaviorModelOutput:
    """Normalize and validate a tumor-behavior artifact.

    Acceptance criteria:
        1. Determinism: Same artifact and source evidence return the same
           normalized artifact or validation error.
        2. No mutation: The model-generated artifact is not mutated.
        3. Safety: Existing case-derived, ID, MIMS, and language validation
           rules remain authoritative.
    """
    normalized = _normalize_tumor_behavior_transition_support(
        _normalize_tumor_behavior_review_fields(tumor_behavior)
    )
    _validate_tumor_behavior_is_case_derived(
        normalized,
        context=context,
        phenotype=phenotype,
        matrix=matrix,
        sankey=sankey,
        confirmatory=confirmatory,
    )
    return normalized


def _validate_tumor_behavior_is_case_derived(
    tumor_behavior: TumorBehaviorModelOutput,
    *,
    context: EvidenceContextBundle,
    phenotype: MolecularPhenotypeOutput,
    matrix: TherapyEvidenceMatrixOutput,
    sankey: MechanismSankeyOutput,
    confirmatory: ConfirmatoryTestingOutput,
) -> None:
    """Validate that tumor behavior output is evidence-derived, not templated.

    Acceptance criteria:
        1. Uses the fixed tumor-state vocabulary without adding ad-hoc states.
        2. Requires state support to resolve to report findings, graph evidence,
           ToolUniverse artifacts, Medea reasoning, or explicit missing evidence.
        3. Requires transition support to reference real source artifacts or
           evidence IDs from the current case.
        4. Rejects generic hardcoded transition rationales that do not contain
           case-derived evidence terms.
        5. Rejects unsupported certainty while allowing risk-ranked
           resistance-forecast and treatment-pressure language.
        6. Does not synthesize replacement transitions or substitute fallback
           state evidence.
    """
    if not tumor_behavior.state_evidence:
        raise StructuredArtifactGenerationError(
            "TumorBehaviorModelOutput requires at least one state_evidence record"
        )
    allowed_states = set(STATE_LABELS)
    finding_ids = {
        finding.finding_id for finding in context.extraction.molecular_findings
    }
    graph_ids = {context.graph_evidence.artifact_id}
    graph_ids.update(node.node_id for node in context.graph_evidence.nodes)
    graph_ids.update(edge.edge_id for edge in context.graph_evidence.edges)
    tool_ids = {tool.artifact_id for tool in context.tool_outputs}
    medea_ids = {context.medea_reasoning.artifact_id}
    medea_ids.update(context.medea_reasoning.supported_hypotheses)
    medea_ids.update(context.medea_reasoning.weakened_hypotheses)
    evidence_ids = _tumor_behavior_allowed_evidence_ids(
        context=context,
        phenotype=phenotype,
        matrix=matrix,
        sankey=sankey,
        confirmatory=confirmatory,
    )
    mims_derived_ids = _mims_derived_support_ids(
        context=context,
        phenotype=phenotype,
        matrix=matrix,
        sankey=sankey,
        confirmatory=confirmatory,
    )
    case_terms = _tumor_behavior_case_terms(
        context=context,
        phenotype=phenotype,
        matrix=matrix,
        sankey=sankey,
        confirmatory=confirmatory,
    )
    used_mims_support = False
    for state in tumor_behavior.state_evidence:
        if state.state_label not in allowed_states:
            raise StructuredArtifactGenerationError(
                f"TumorBehaviorModelOutput uses unsupported state_label: {state.state_label}"
            )
        _validate_id_subset(
            state.supporting_findings,
            finding_ids,
            f"state_evidence[{state.state_label}].supporting_findings",
        )
        _validate_id_subset(
            state.graph_support,
            graph_ids,
            f"state_evidence[{state.state_label}].graph_support",
        )
        _validate_id_subset(
            state.tool_support,
            tool_ids,
            f"state_evidence[{state.state_label}].tool_support",
        )
        _validate_id_subset(
            state.medea_support,
            medea_ids,
            f"state_evidence[{state.state_label}].medea_support",
        )
        used_mims_support = used_mims_support or bool(
            state.graph_support or state.tool_support or state.medea_support
        )
        if not (
            state.supporting_findings
            or state.graph_support
            or state.tool_support
            or state.medea_support
            or _is_missing_or_speculative_class(state.evidence_class)
        ):
            raise StructuredArtifactGenerationError(
                f"TumorBehaviorModelOutput state {state.state_label} has no support "
                "and is not marked as missing/speculative evidence"
            )
        if not state.validation_needed:
            raise StructuredArtifactGenerationError(
                f"TumorBehaviorModelOutput state {state.state_label} is not marked validation_needed"
            )
    for transition in tumor_behavior.transition_hypotheses:
        if not transition.hypothesis_generating:
            raise StructuredArtifactGenerationError(
                "TumorBehaviorModelOutput transition is not marked hypothesis_generating"
            )
        if transition.from_state not in allowed_states or transition.to_state not in allowed_states:
            raise StructuredArtifactGenerationError(
                "TumorBehaviorModelOutput transition uses an unsupported state label"
            )
        if transition.from_state == transition.to_state:
            raise StructuredArtifactGenerationError(
                "TumorBehaviorModelOutput transition cannot have identical from_state and to_state"
            )
        if not transition.supporting_artifacts:
            raise StructuredArtifactGenerationError(
                "TumorBehaviorModelOutput transition is missing supporting_artifacts"
            )
        _validate_id_subset(
            transition.supporting_artifacts,
            evidence_ids,
            "transition_hypotheses.supporting_artifacts",
        )
        used_mims_support = used_mims_support or any(
            item in graph_ids
            or item in tool_ids
            or item in medea_ids
            or item in mims_derived_ids
            for item in transition.supporting_artifacts
        )
        _validate_transition_rationale_is_case_derived(transition.rationale, case_terms)
        _reject_unsupported_certainty_language(transition.rationale)
        _reject_unsupported_certainty_language(transition.confidence_label)
        if transition.validation_status != "needs_review":
            raise StructuredArtifactGenerationError(
                "TumorBehaviorModelOutput transition validation_status must be needs_review"
            )
    if _mims_evidence_available(context) and not used_mims_support:
        raise StructuredArtifactGenerationError(
            "TumorBehaviorModelOutput ignored available MIMS evidence support"
        )


def _validate_id_subset(values: Sequence[str], allowed: set[str], field_name: str) -> None:
    unknown = [value for value in values if value not in allowed]
    if unknown:
        raise StructuredArtifactGenerationError(
            f"TumorBehaviorModelOutput {field_name} references unsupported IDs: "
            + ", ".join(sorted(unknown))
        )


def _is_missing_or_speculative_class(value: str) -> bool:
    lowered = value.casefold()
    return "missing" in lowered or "speculative" in lowered or "requires_validation" in lowered


def _mims_evidence_available(context: EvidenceContextBundle) -> bool:
    """Return whether the case has valid MIMS support identifiers.

    Acceptance criteria:
        1. Determinism: Same context returns the same availability result.
        2. No mutation: Does not mutate the evidence context.
        3. Evidence scope: Counts only graph, tool, or Medea evidence present in
           the current case.

    Args:
        context: Current evidence context bundle.

    Returns:
        Whether one or more MIMS support identifiers are available.
    """
    return bool(_available_mims_support_ids(context))


def _available_mims_support_ids(context: EvidenceContextBundle) -> list[str]:
    """Return sorted current-case MIMS identifiers valid for direct citation.

    Acceptance criteria:
        1. Determinism: Same context returns the same sorted identifiers.
        2. No mutation: Does not mutate the evidence context or nested values.
        3. Evidence scope: Includes graph IDs only with graph evidence, tool IDs
           only for current tool outputs, and the Medea artifact ID only with
           Medea content.
        4. Validation: Excludes free-text Medea hypotheses and oversized IDs
           that are not safe prompt-side citations.

    Args:
        context: Current evidence context bundle.

    Returns:
        Sorted direct identifiers that the tumor-behavior model may cite as
        MIMS support.
    """
    support_ids: set[str] = set()
    if context.graph_evidence.nodes or context.graph_evidence.edges:
        support_ids.add(context.graph_evidence.artifact_id)
        support_ids.update(node.node_id for node in context.graph_evidence.nodes)
        support_ids.update(edge.edge_id for edge in context.graph_evidence.edges)
    support_ids.update(tool.artifact_id for tool in context.tool_outputs)
    medea = context.medea_reasoning
    if (
        medea.summary.strip()
        or medea.supported_hypotheses
        or medea.weakened_hypotheses
    ):
        support_ids.add(medea.artifact_id)
    return _compact_tumor_support_ids(support_ids)


def _compact_tumor_support_ids(values: Sequence[str] | set[str]) -> list[str]:
    """Return bounded direct support IDs without truncating identifiers.

    Acceptance criteria:
        1. Determinism: Same input identifiers return the same ordered IDs.
        2. No mutation: Does not mutate the caller-owned collection.
        3. Validation: Omits blank and oversized identifiers rather than
           truncating them into invalid citations.
        4. Boundedness: Returns no more than the prompt support-ID cap.

    Args:
        values: Direct current-case support identifiers.

    Returns:
        Prompt-safe support identifiers.
    """
    return sorted(
        {
            value
            for value in values
            if value.strip()
            and len(value) <= _MAX_PROMPT_TUMOR_SUPPORT_ID_CHARS
        }
    )[:_MAX_PROMPT_SUPPORT_IDS]


def _tumor_behavior_allowed_evidence_ids(
    *,
    context: EvidenceContextBundle,
    phenotype: MolecularPhenotypeOutput,
    matrix: TherapyEvidenceMatrixOutput,
    sankey: MechanismSankeyOutput,
    confirmatory: ConfirmatoryTestingOutput,
) -> set[str]:
    """Return evidence IDs allowed in tumor-behavior transitions.

    Acceptance criteria:
        1. Determinism: Same source artifacts return the same ID set.
        2. No mutation: Input models are not mutated.
        3. Scope: Includes only current-case report, graph, tool, Medea,
           generated artifact, finding, and confirmatory-test IDs.
        4. Safety: Does not include arbitrary model-generated IDs.
    """
    finding_ids = {
        finding.finding_id for finding in context.extraction.molecular_findings
    }
    graph_ids = {context.graph_evidence.artifact_id}
    graph_ids.update(node.node_id for node in context.graph_evidence.nodes)
    graph_ids.update(edge.edge_id for edge in context.graph_evidence.edges)
    tool_ids = {tool.artifact_id for tool in context.tool_outputs}
    medea_ids = {context.medea_reasoning.artifact_id}
    medea_ids.update(context.medea_reasoning.supported_hypotheses)
    medea_ids.update(context.medea_reasoning.weakened_hypotheses)
    confirmatory_ids = {test.test_id for test in confirmatory.tests}
    artifact_ids = {
        context.extraction.artifact_id,
        context.graph_evidence.artifact_id,
        context.medea_reasoning.artifact_id,
        phenotype.artifact_id,
        matrix.artifact_id,
        sankey.artifact_id,
        confirmatory.artifact_id,
        *tool_ids,
    }
    return (
        artifact_ids
        | finding_ids
        | graph_ids
        | tool_ids
        | medea_ids
        | confirmatory_ids
    )


def _mims_derived_support_ids(
    *,
    context: EvidenceContextBundle,
    phenotype: MolecularPhenotypeOutput,
    matrix: TherapyEvidenceMatrixOutput,
    sankey: MechanismSankeyOutput,
    confirmatory: ConfirmatoryTestingOutput,
) -> set[str]:
    """Return generated artifact IDs that carry current-case MIMS support.

    Acceptance criteria:
        1. Determinism: Same artifacts return the same ID set.
        2. No mutation: Input models are not mutated.
        3. Scope: Return an empty set when no MIMS evidence is available.
        4. Provenance: Include only current-case generated artifact IDs and
           confirmatory test IDs already validated elsewhere.

    Args:
        context: Current evidence context.
        phenotype: Current generated molecular phenotype artifact.
        matrix: Current generated molecular-fit matrix artifact.
        sankey: Current generated mechanism Sankey artifact.
        confirmatory: Current generated confirmatory-testing artifact.

    Returns:
        Generated support IDs that can satisfy MIMS-support usage.
    """
    if not _mims_evidence_available(context):
        return set()
    return {
        phenotype.artifact_id,
        matrix.artifact_id,
        sankey.artifact_id,
        confirmatory.artifact_id,
        *(test.test_id for test in confirmatory.tests),
    }


def _tumor_behavior_case_terms(
    *,
    context: EvidenceContextBundle,
    phenotype: MolecularPhenotypeOutput,
    matrix: TherapyEvidenceMatrixOutput,
    sankey: MechanismSankeyOutput,
    confirmatory: ConfirmatoryTestingOutput,
) -> set[str]:
    terms: set[str] = set()
    for finding in context.extraction.molecular_findings:
        _add_case_terms(terms, finding.gene or "")
        _add_case_terms(terms, finding.alteration)
        _add_case_terms(terms, finding.alteration_type.replace("_", " "))
    for node in context.graph_evidence.nodes:
        _add_case_terms(terms, node.label)
        _add_case_terms(terms, node.kind)
    for edge in context.graph_evidence.edges:
        _add_case_terms(terms, edge.relation_type.replace("_", " "))
        _add_case_terms(terms, edge.source)
    for tool in context.tool_outputs:
        _add_case_terms(terms, tool.workflow.replace("_", " "))
        _add_case_terms(terms, tool.summary)
        for item in tool.evidence_items:
            for value in item.values():
                _add_case_terms(terms, value)
    _add_case_terms(terms, context.medea_reasoning.summary)
    for hypothesis in [
        *context.medea_reasoning.supported_hypotheses,
        *context.medea_reasoning.weakened_hypotheses,
    ]:
        _add_case_terms(terms, hypothesis)
    for axis in phenotype.axes:
        _add_case_terms(terms, axis.label)
        _add_case_terms(terms, axis.evidence_class.replace("_", " "))
        _add_case_terms(terms, axis.uncertainty)
    for row in matrix.rows:
        _add_case_terms(terms, row.molecular_fit)
        _add_case_terms(terms, row.fit_label.replace("_", " "))
        _add_case_terms(terms, row.why_from_omics)
        _add_case_terms(terms, row.evidence_basis.replace("_", " "))
        _add_case_terms(terms, row.required_validation)
    for node in sankey.nodes:
        _add_case_terms(terms, node.label)
        _add_case_terms(terms, node.kind.replace("_", " "))
    for link in sankey.links:
        _add_case_terms(terms, link.claim_class.replace("_", " "))
        for source_id in link.source_artifact_ids:
            _add_case_terms(terms, source_id)
    for test in confirmatory.tests:
        _add_case_terms(terms, test.question)
        _add_case_terms(terms, test.why_it_matters)
        _add_case_terms(terms, test.evidence_gap)
    return terms


def _add_case_terms(terms: set[str], value: str) -> None:
    for term in _tumor_behavior_terms(value):
        if len(term) >= 3:
            terms.add(term.casefold())


def _validate_transition_rationale_is_case_derived(
    rationale: str,
    case_terms: set[str],
) -> None:
    rationale_terms = {term.casefold() for term in _tumor_behavior_terms(rationale)}
    if not rationale_terms.intersection(case_terms):
        raise StructuredArtifactGenerationError(
            "TumorBehaviorModelOutput transition rationale does not reference "
            "case-derived evidence terms"
        )


def _is_repairable_tumor_behavior_validation_error(error: BaseException) -> bool:
    """Return whether a tumor-behavior validation error can be retried.

    Acceptance criteria:
        1. Determinism: Same exception message returns the same boolean.
        2. Scope: Matches only transition-rationale, transition-support ID, or
           missing required MIMS-support validation failures.
        3. No mutation: Does not mutate exception state.
    """
    message = str(error)
    return (
        _is_transition_rationale_case_terms_error(error)
        or str(error) == "TumorBehaviorModelOutput ignored available MIMS evidence support"
        or (
        "transition_hypotheses.supporting_artifacts references unsupported IDs"
        in message
        )
    )


def _is_transition_rationale_case_terms_error(error: BaseException) -> bool:
    return (
        "transition rationale does not reference case-derived evidence terms"
        in str(error)
    )


def _tumor_behavior_validation_repair_payload(
    payload: Mapping[str, object],
    *,
    error: BaseException,
    case_terms: set[str],
    allowed_evidence_ids: set[str],
    required_mims_support_ids: Sequence[str],
) -> dict[str, object]:
    """Return a tumor-behavior payload with validation repair instructions.

    Acceptance criteria:
        1. Determinism: Same payload, error, terms, and IDs return the same
           result.
        2. No mutation: The original payload mapping is not mutated.
        3. Scope: Adds only repair instructions; clinical evidence stays in the
           original source payload.
        4. Safety: Requires concrete case terms and whitelisted support IDs
           without allowing new facts, probabilities, or treatment
           recommendations.
        5. MIMS support: Requires a direct current-case MIMS identifier when
           the previous output omitted available MIMS evidence.
    """
    return {
        **dict(payload),
        "repair_instruction": {
            "previous_validation_error": str(error),
            "repair_scope": (
                "Revise transition rationales so each rationale explicitly "
                "mentions at least one concrete case-derived evidence term "
                "from allowed_case_terms. Replace or remove every unsupported "
                "transition supporting_artifacts ID so each cited ID appears "
                "in allowed_supporting_artifact_ids. Do not add new facts, "
                "treatment recommendations, probabilities, or deterministic "
                "outcome claims. If no allowed support applies to a transition, "
                "omit that transition. When required_mims_support_ids is "
                "non-empty, cite at least one of those IDs in graph_support, "
                "tool_support, medea_support, or transition "
                "supporting_artifacts."
            ),
            "allowed_case_terms": sorted(case_terms)[:_MAX_PROMPT_SUPPORT_IDS],
            "allowed_supporting_artifact_ids": sorted(allowed_evidence_ids),
            "required_mims_support_ids": list(required_mims_support_ids),
        },
    }


def _tumor_behavior_terms(value: str) -> list[str]:
    return [
        term
        for term in _informative_terms(value)
        if term.casefold() not in _GENERIC_TUMOR_BEHAVIOR_TERMS
    ]


def _reject_unsupported_certainty_language(value: str) -> None:
    lowered = value.casefold()
    blocked_patterns = (
        r"\b(?:100|100\.0)\s*%\s*(?:response|respond|cure|curative|relapse|progression|benefit)\b",
        r"\b\d+(?:\.\d+)?\s*%\s*(?:relapse|response|benefit|progression|survival)\s+probability\b",
        r"\bprobability\s+of\s+(?:relapse|response|benefit|progression|survival)\b",
        r"\bwill\s+(?:respond|be cured|be curative|survive)\b",
        r"\bguarantee(?:d|s)?\b",
        r"\bdefinitive\s+cure\b",
        r"\bpatient\s+will\s+(?:respond|progress|relapse|recur)\b",
        r"\bpatient\s+should\s+receive\b",
    )
    for pattern in blocked_patterns:
        if re.search(pattern, lowered):
            raise StructuredArtifactGenerationError(
                "TumorBehaviorModelOutput contains unsupported certainty, "
                "probability, or deterministic outcome language"
            )


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
        payload=compact_claim_evidence_inputs_for_prompt(
            context=context,
            phenotype=phenotype,
            matrix=matrix,
            sankey=sankey,
            confirmatory=confirmatory,
            tumor_behavior=tumor_behavior,
        ),
        source_artifact_ids=[
            *_context_source_ids(context),
            phenotype.artifact_id,
            matrix.artifact_id,
            sankey.artifact_id,
            confirmatory.artifact_id,
            tumor_behavior.artifact_id,
        ],
        source_chunk_ids=_context_source_chunk_ids(context),
        source_file_id=context.extraction.source_file_id,
        model_provider=model_provider,
        model_name=model_name,
        prompts_root=prompts_root,
        created_at=created_at,
    )
    normalized_artifact = _normalize_claim_validation_statuses(result.artifact)
    for claim in normalized_artifact.claims:
        if claim.validation_status != "needs_review":
            raise StructuredArtifactGenerationError(
                "ClaimEvidenceOutput validation_status must be needs_review"
            )
    return StructuredArtifactResult(
        artifact=normalized_artifact,
        provenance=result.provenance,
    )


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
    compact_bundle = compact_clinical_narrative_bundle_for_prompt(bundle)
    result = await _generate_artifact(
        prompt_name="clinical_narrative",
        schema_model=ClinicalNarrativeCompilerOutput,
        planned_artifact_id=artifact_id,
        payload={"clinical_artifact_bundle": compact_bundle},
        source_artifact_ids=source_ids,
        source_chunk_ids=_bundle_source_chunk_ids(bundle),
        source_file_id=bundle.extraction.source_file_id,
        model_provider=model_provider,
        model_name=model_name,
        prompts_root=prompts_root,
        created_at=created_at,
        artifact_validator=lambda narrative: (
            _normalize_and_validate_clinical_narrative(
                narrative,
                allowed_source_ids=source_ids,
                narrative_artifact_id=artifact_id,
            )
        ),
    )
    return result


class ClaimEvidenceListOutput(BaseModel):
    """Structured-output wrapper because the runtime stores claims as a list."""

    artifact_id: str
    claims: list[ClaimEvidenceOutput]


def _normalize_validation_status_for_review(_value: object) -> str:
    """Return the initial review status for model-generated artifacts.

    Acceptance criteria:
        1. Determinism: Any input value returns the same normalized status.
        2. No mutation: Caller-owned values are not mutated.
        3. Safety: Model-generated validated or rejected statuses are not
           accepted as human validation decisions.
        4. Reviewability: Every generated validation status starts as
           `needs_review`.

    Args:
        value: Raw model-generated validation status.

    Returns:
        The only allowed initial status, `needs_review`.
    """
    return "needs_review"


def _normalize_tumor_behavior_review_fields(
    tumor_behavior: TumorBehaviorModelOutput,
) -> TumorBehaviorModelOutput:
    """Return tumor behavior output with workflow review gates normalized.

    Acceptance criteria:
        1. Determinism: Same tumor behavior input returns equivalent output.
        2. No mutation: The input model and nested records are not mutated.
        3. Evidence integrity: Do not synthesize supporting evidence IDs or
           biological claims.
        4. Missing evidence: Empty-support states are marked as
           `missing_speculative_evidence`.
        5. Reviewability: All generated states are marked validation-needed.
        6. Hypothesis control: All generated transitions remain
           hypothesis-generating and `needs_review`.

    Args:
        tumor_behavior: Model-generated tumor behavior artifact.

    Returns:
        A copied artifact whose reviewability fields follow workflow policy.
    """
    states = [
        state.model_copy(
            update={
                "evidence_class": (
                    "missing_speculative_evidence"
                    if not (
                        state.supporting_findings
                        or state.graph_support
                        or state.tool_support
                        or state.medea_support
                    )
                    else state.evidence_class
                ),
                "validation_needed": True,
            }
        )
        for state in tumor_behavior.state_evidence
    ]
    transitions = [
        transition.model_copy(
            update={
                "hypothesis_generating": True,
                "validation_status": _normalize_validation_status_for_review(
                    transition.validation_status
                ),
            }
        )
        for transition in tumor_behavior.transition_hypotheses
    ]
    return tumor_behavior.model_copy(
        update={
            "state_evidence": states,
            "transition_hypotheses": transitions,
        }
    )


def _normalize_tumor_behavior_transition_support(
    tumor_behavior: TumorBehaviorModelOutput,
) -> TumorBehaviorModelOutput:
    """Return tumor behavior output without self-referential support IDs.

    Acceptance criteria:
        1. Determinism: Same tumor behavior input returns equivalent output.
        2. No mutation: The input model and nested transitions are not mutated.
        3. Evidence integrity: Do not add or substitute supporting artifacts.
        4. Scope: Remove only the tumor behavior artifact's own ID from
           transition support.
        5. Validation: Transitions with no remaining support still fail later
           validation as missing support.

    Args:
        tumor_behavior: Model-generated tumor behavior artifact.

    Returns:
        A copied artifact whose transitions do not cite the artifact itself as
        support.
    """
    transitions = [
        transition.model_copy(
            update={
                "supporting_artifacts": [
                    artifact_id
                    for artifact_id in transition.supporting_artifacts
                    if artifact_id != tumor_behavior.artifact_id
                ]
            }
        )
        for transition in tumor_behavior.transition_hypotheses
    ]
    return tumor_behavior.model_copy(update={"transition_hypotheses": transitions})


def _normalize_claim_validation_statuses(
    artifact: ClaimEvidenceListOutput,
) -> ClaimEvidenceListOutput:
    """Return claim evidence output with generated statuses reviewable.

    Acceptance criteria:
        1. Determinism: Same claim artifact input returns equivalent output.
        2. No mutation: The input artifact and nested claims are not mutated.
        3. Scope: Only claim validation_status values are normalized.
        4. Reviewability: All generated claims use `needs_review`.

    Args:
        artifact: Model-generated claim evidence artifact.

    Returns:
        A copied artifact whose claim statuses are reviewable.
    """
    claims = [
        claim.model_copy(
            update={
                "validation_status": _normalize_validation_status_for_review(
                    claim.validation_status
                )
            }
        )
        for claim in artifact.claims
    ]
    return artifact.model_copy(update={"claims": claims})


def _normalize_clinical_narrative_fragments(
    narrative: ClinicalNarrativeCompilerOutput,
) -> ClinicalNarrativeCompilerOutput:
    """Return narrative markdown with vague alteration fragments neutralized.

    Acceptance criteria:
        1. Determinism: Same narrative input returns equivalent output.
        2. No mutation: The input narrative is not mutated.
        3. Evidence integrity: Do not add genes, alterations, or source IDs.
        4. Scope: Only vague determiner-led or modifier-led alteration
           fragments are normalized.
        5. Reviewability: Replacement wording remains non-specific and
           clinician-reviewable.

    Args:
        narrative: Model-generated clinical narrative artifact.

    Returns:
        A copied narrative whose markdown avoids unsupported fragments such as
        `the mutation`, `This amplification`, and `identified variant`.
    """
    markdown = _VAGUE_NARRATIVE_ALTERATION.sub(
        _neutral_narrative_fragment,
        narrative.markdown,
    )
    return narrative.model_copy(update={"markdown": markdown})


def _normalize_and_validate_clinical_narrative(
    narrative: ClinicalNarrativeCompilerOutput,
    *,
    allowed_source_ids: Sequence[str],
    narrative_artifact_id: str,
) -> ClinicalNarrativeCompilerOutput:
    """Return narrative text with system-owned provenance identifiers.

    Acceptance criteria:
        1. Source IDs equal the ordered, de-duplicated bundle allowlist.
        2. Unsupported artifact IDs in Markdown raise a validation error.
        3. Caller-owned narrative and ID collections are not mutated.
        4. Existing vague-fragment normalization remains active.
    """
    canonical_ids = list(dict.fromkeys(allowed_source_ids))
    markdown_ids = set(re.findall(r"\bartifact_[A-Za-z0-9_-]+\b", narrative.markdown))
    allowed_markdown_ids = {narrative_artifact_id, *canonical_ids}
    unsupported_markdown_ids = sorted(markdown_ids - allowed_markdown_ids)
    if unsupported_markdown_ids:
        raise StructuredArtifactGenerationError(
            "ClinicalNarrativeCompilerOutput Markdown included unsupported "
            f"artifact IDs: {', '.join(unsupported_markdown_ids[:12])}"
        )
    normalized = _normalize_clinical_narrative_fragments(narrative)
    return normalized.model_copy(update={"source_artifact_ids": canonical_ids})


def _neutral_narrative_fragment(match: re.Match[str]) -> str:
    replacement = "report finding"
    prefix = match.group("prefix")
    if prefix and prefix[0].isupper():
        return replacement.capitalize()
    return replacement


def truncate_text(value: str | None, max_chars: int) -> str | None:
    """Return text capped to a deterministic character budget.

    Acceptance criteria:
        1. Determinism: Same input and limit return the same output.
        2. No mutation: Caller-owned values are not mutated.
        3. Validation: Non-positive limits raise `ValueError`.
        4. Provenance: Truncated output includes omitted character count.

    Args:
        value: Optional text value to cap.
        max_chars: Maximum number of source characters to retain.

    Returns:
        Original text when under limit, truncated text when over limit, or
        `None` when `value` is `None`.

    Raises:
        ValueError: If `max_chars` is less than one.
    """
    if max_chars < 1:
        raise ValueError("max_chars must be positive")
    if value is None:
        return None
    if len(value) <= max_chars:
        return value
    omitted = len(value) - max_chars
    return f"{value[:max_chars]}... [truncated {omitted} chars]"


def entity_labels_from_context(context: EvidenceContextBundle) -> list[str]:
    """Return unique report-derived labels for prompt relevance ranking.

    Acceptance criteria:
        1. Determinism: Label order follows report order.
        2. No mutation: The evidence context is not mutated.
        3. Coverage: Disease, specimen, tumor percentage, gene, alteration,
           and alteration type values are considered.
        4. Normalization: Empty and duplicate labels are removed.

    Args:
        context: Evidence context to inspect.

    Returns:
        Unique non-empty labels from the source report extraction.
    """
    raw_labels = [
        context.extraction.disease,
        context.extraction.specimen,
        context.extraction.tumor_percentage,
    ]
    for finding in context.extraction.molecular_findings:
        raw_labels.extend(
            [
                finding.gene,
                finding.alteration,
                finding.alteration_type,
            ]
        )
    return _unique_nonempty_strings(raw_labels)


def compact_evidence_context_for_prompt(
    context: EvidenceContextBundle,
) -> dict[str, object]:
    """Return a bounded prompt payload for an evidence context.

    Acceptance criteria:
        1. Determinism: Same context returns the same compact payload.
        2. No mutation: The input context is not mutated.
        3. Provenance: Artifact IDs, finding IDs, source chunk IDs, graph IDs,
           tool IDs, and Medea IDs remain present.
        4. Context safety: Truncation metadata states that omitted context is
           not evidence of biological absence.

    Args:
        context: Full evidence context bundle.

    Returns:
        JSON-serializable compact evidence context for vLLM prompts.
    """
    entity_labels = entity_labels_from_context(context)
    findings = [
        _compact_finding_for_prompt(finding)
        for finding in context.extraction.molecular_findings[:_MAX_PROMPT_FINDINGS]
    ]
    return {
        "artifact_id": context.artifact_id,
        "extraction": {
            "artifact_id": context.extraction.artifact_id,
            "report_type": context.extraction.report_type,
            "disease": context.extraction.disease,
            "specimen": context.extraction.specimen,
            "tumor_percentage": context.extraction.tumor_percentage,
            "source_file_id": context.extraction.source_file_id,
            "needs_human_review": context.extraction.needs_human_review,
            "molecular_findings": findings,
            "negative_findings": _compact_text_list(
                context.extraction.negative_findings,
            ),
            "assay_limitations": _compact_text_list(
                context.extraction.assay_limitations,
            ),
            "truncation": {
                "original_molecular_findings": (
                    len(context.extraction.molecular_findings)
                ),
                "kept_molecular_findings": len(findings),
            },
        },
        "graph_evidence": compact_graph_for_prompt(
            context.graph_evidence.model_dump(mode="json"),
            entity_labels,
        ),
        "tool_outputs": compact_tool_outputs_for_prompt(context.tool_outputs),
        "medea_reasoning": compact_medea_reasoning_for_prompt(
            context.medea_reasoning.model_dump(mode="json")
        ),
        "missing_evidence": _compact_text_list(context.missing_evidence),
        "conflicting_evidence": _compact_text_list(
            context.conflicting_evidence,
        ),
        "truncation_notice": _PROMPT_CONTEXT_CAP_NOTICE,
    }


def compact_evidence_context_for_molecular_phenotype_prompt(
    context: EvidenceContextBundle,
) -> dict[str, object]:
    """Return a tight evidence payload for molecular phenotype prompts.

    Acceptance criteria:
        1. Determinism: Same context returns the same compact payload.
        2. No mutation: The input context is not mutated.
        3. Provenance: Artifact IDs, finding IDs, source chunk IDs, graph IDs,
           tool IDs, and Medea IDs remain present for grounding.
        4. Boundedness: Source text, graph context, tool evidence rows, and
           Medea reasoning are capped more tightly than the general serializer.
        5. Safety: Truncation metadata states that omitted context is not
           evidence of biological absence.

    Args:
        context: Full evidence context bundle.

    Returns:
        JSON-serializable evidence context tuned for phenotype generation.
    """
    compact = compact_evidence_context_for_prompt(context)
    extraction = dict(compact["extraction"])
    extraction.update(
        {
            "molecular_findings": [
                _compact_phenotype_input_finding(finding)
                for finding in extraction["molecular_findings"][
                    :_MAX_PROMPT_PHENOTYPE_FINDINGS
                ]
            ],
            "negative_findings": _compact_phenotype_input_texts(
                extraction.get("negative_findings", [])
            ),
            "assay_limitations": _compact_phenotype_input_texts(
                extraction.get("assay_limitations", [])
            ),
        }
    )
    graph = _compact_phenotype_input_graph(
        compact["graph_evidence"],
    )
    medea = _compact_phenotype_input_medea(
        compact["medea_reasoning"],
    )
    return {
        "artifact_id": compact["artifact_id"],
        "extraction": extraction,
        "graph_evidence": graph,
        "tool_outputs": [
            _compact_phenotype_input_tool(tool)
            for tool in compact["tool_outputs"][
                :_MAX_PROMPT_PHENOTYPE_TOOL_OUTPUTS
            ]
        ],
        "medea_reasoning": medea,
        "missing_evidence": _compact_phenotype_input_texts(
            compact.get("missing_evidence", [])
        ),
        "conflicting_evidence": _compact_phenotype_input_texts(
            compact.get("conflicting_evidence", [])
        ),
        "truncation_notice": _PROMPT_CONTEXT_CAP_NOTICE,
    }


def compact_evidence_context_for_claim_evidence_prompt(
    context: EvidenceContextBundle,
) -> dict[str, object]:
    """Return a tight evidence-context payload for claim evidence prompts.

    Acceptance criteria:
        1. Determinism: Same context returns the same compact payload.
        2. No mutation: The input context is not mutated.
        3. Provenance: Artifact, finding, source chunk, graph, tool, and Medea
           IDs remain present for claim grounding.
        4. Boundedness: Source text, graph context, tool evidence rows, and
           Medea reasoning use claim-evidence prompt caps.
    """
    compact = compact_evidence_context_for_prompt(context)
    extraction = dict(compact["extraction"])
    extraction.update(
        {
            "molecular_findings": [
                _compact_claim_input_finding(finding)
                for finding in extraction["molecular_findings"][
                    :_MAX_PROMPT_CLAIM_INPUT_FINDINGS
                ]
            ],
            "negative_findings": _compact_claim_input_texts(
                extraction.get("negative_findings", [])
            ),
            "assay_limitations": _compact_claim_input_texts(
                extraction.get("assay_limitations", [])
            ),
        }
    )
    return {
        "artifact_id": compact["artifact_id"],
        "extraction": extraction,
        "graph_evidence": _compact_claim_input_graph(
            compact["graph_evidence"]
        ),
        "tool_outputs": [
            _compact_claim_input_tool(tool)
            for tool in compact["tool_outputs"][
                :_MAX_PROMPT_CLAIM_INPUT_TOOL_OUTPUTS
            ]
        ],
        "medea_reasoning": _compact_claim_input_medea(
            compact["medea_reasoning"]
        ),
        "missing_evidence": _compact_claim_input_texts(
            compact.get("missing_evidence", [])
        ),
        "conflicting_evidence": _compact_claim_input_texts(
            compact.get("conflicting_evidence", [])
        ),
        "truncation_notice": _PROMPT_CONTEXT_CAP_NOTICE,
    }


def compact_evidence_context_for_tumor_behavior_prompt(
    context: EvidenceContextBundle,
) -> dict[str, object]:
    """Return a tight evidence-context payload for tumor behavior prompts.

    Acceptance criteria:
        1. Determinism: Same context returns the same compact payload.
        2. No mutation: The input context is not mutated.
        3. Provenance: Artifact, finding, source chunk, graph, tool, and Medea
           IDs remain present for tumor-state and transition grounding.
        4. Boundedness: Source text, graph context, tool evidence rows, and
           Medea reasoning use tumor-behavior prompt caps.
        5. Safety: Truncation metadata states that omitted context is not
           evidence of biological absence.

    Args:
        context: Full evidence context bundle.

    Returns:
        JSON-serializable evidence context tuned for tumor behavior generation.
    """
    compact = compact_evidence_context_for_prompt(context)
    extraction = dict(compact["extraction"])
    extraction.update(
        {
            "molecular_findings": [
                _compact_tumor_input_finding(finding)
                for finding in extraction["molecular_findings"][
                    :_MAX_PROMPT_TUMOR_INPUT_FINDINGS
                ]
            ],
            "negative_findings": _compact_tumor_input_texts(
                extraction.get("negative_findings", [])
            ),
            "assay_limitations": _compact_tumor_input_texts(
                extraction.get("assay_limitations", [])
            ),
        }
    )
    return {
        "artifact_id": compact["artifact_id"],
        "extraction": extraction,
        "graph_evidence": _compact_tumor_input_graph(
            compact["graph_evidence"]
        ),
        "tool_outputs": [
            _compact_tumor_input_tool(tool)
            for tool in compact["tool_outputs"][
                :_MAX_PROMPT_TUMOR_INPUT_TOOL_OUTPUTS
            ]
        ],
        "medea_reasoning": _compact_tumor_input_medea(
            compact["medea_reasoning"]
        ),
        "missing_evidence": _compact_tumor_input_texts(
            compact.get("missing_evidence", [])
        ),
        "conflicting_evidence": _compact_tumor_input_texts(
            compact.get("conflicting_evidence", [])
        ),
        "truncation_notice": _PROMPT_CONTEXT_CAP_NOTICE,
    }


def compact_evidence_context_for_clinical_narrative_prompt(
    context: EvidenceContextBundle,
) -> dict[str, object]:
    """Return evidence-context header for clinical narrative prompts.

    Acceptance criteria:
        1. Determinism: Same context returns the same compact payload.
        2. No mutation: The input context is not mutated.
        3. Provenance: Evidence-context, extraction, graph, tool, and Medea
           artifact IDs remain present.
        4. Boundedness: Detailed evidence is omitted because extraction and
           generated artifacts are supplied elsewhere in the narrative bundle.
    """
    return {
        "artifact_id": context.artifact_id,
        "extraction_artifact_id": context.extraction.artifact_id,
        "graph_artifact_id": context.graph_evidence.artifact_id,
        "tool_artifact_ids": [
            tool.artifact_id
            for tool in context.tool_outputs[:_MAX_PROMPT_NARRATIVE_DECISION_ROWS]
        ],
        "medea_artifact_id": context.medea_reasoning.artifact_id,
        "missing_evidence": _compact_narrative_texts(
            context.missing_evidence
        ),
        "conflicting_evidence": _compact_narrative_texts(
            context.conflicting_evidence
        ),
        "truncation_notice": _PROMPT_CONTEXT_CAP_NOTICE,
    }


def compact_evidence_context_for_mechanism_sankey_prompt(
    context: EvidenceContextBundle,
) -> dict[str, object]:
    """Return a tighter evidence-context payload for mechanism Sankey prompts.

    Acceptance criteria:
        1. Determinism: Same context returns the same compact payload.
        2. No mutation: The input context is not mutated.
        3. Provenance: Artifact IDs, finding IDs, graph IDs, tool IDs, and
           Medea IDs remain available for prompt grounding.
        4. Boundedness: Nested evidence lists and free text use stricter
           mechanism-Sankey prompt caps than the general prompt serializer.

    Args:
        context: Full evidence context bundle.

    Returns:
        JSON-serializable evidence context tuned for the mechanism Sankey call.
    """
    compact = compact_evidence_context_for_prompt(context)
    extraction = dict(compact["extraction"])
    findings = [
        _compact_sankey_input_finding(finding)
        for finding in extraction["molecular_findings"][
            :_MAX_PROMPT_SANKEY_INPUT_FINDINGS
        ]
    ]
    extraction.update(
        {
            "molecular_findings": findings,
            "negative_findings": _compact_sankey_input_texts(
                extraction.get("negative_findings", [])
            ),
            "assay_limitations": _compact_sankey_input_texts(
                extraction.get("assay_limitations", [])
            ),
        }
    )
    extraction.pop("truncation", None)
    graph = dict(compact["graph_evidence"])
    graph.update(
        {
            "nodes": graph["nodes"][:_MAX_PROMPT_SANKEY_INPUT_GRAPH_NODES],
            "edges": graph["edges"][:_MAX_PROMPT_SANKEY_INPUT_GRAPH_EDGES],
            "missing_entities": _compact_sankey_input_texts(
                graph.get("missing_entities", [])
            ),
            "warnings": _compact_sankey_input_texts(
                graph.get("warnings", [])
            ),
        }
    )
    graph.pop("truncation", None)
    medea = dict(compact["medea_reasoning"])
    medea.update(
        {
            "summary": truncate_text(
                str(medea.get("summary", "")),
                _MAX_PROMPT_SANKEY_INPUT_SUMMARY_CHARS,
            ),
            "supported_hypotheses": _compact_sankey_input_texts(
                medea.get("supported_hypotheses", []),
                _MAX_PROMPT_SANKEY_INPUT_HYPOTHESES,
            ),
            "weakened_hypotheses": _compact_sankey_input_texts(
                medea.get("weakened_hypotheses", []),
                _MAX_PROMPT_SANKEY_INPUT_HYPOTHESES,
            ),
            "warnings": _compact_sankey_input_texts(
                medea.get("warnings", [])
            ),
        }
    )
    medea.pop("truncation", None)
    return {
        "artifact_id": compact["artifact_id"],
        "extraction": extraction,
        "graph_evidence": graph,
        "tool_outputs": [
            _compact_sankey_input_tool(tool)
            for tool in compact["tool_outputs"][
                :_MAX_PROMPT_SANKEY_INPUT_TOOL_OUTPUTS
            ]
        ],
        "medea_reasoning": medea,
        "missing_evidence": _compact_sankey_input_texts(
            compact.get("missing_evidence", [])
        ),
        "conflicting_evidence": _compact_sankey_input_texts(
            compact.get("conflicting_evidence", [])
        ),
        "truncation_notice": _PROMPT_CONTEXT_CAP_NOTICE,
    }


def compact_graph_for_prompt(
    graph: Mapping[str, Any],
    entity_labels: Sequence[str],
) -> dict[str, object]:
    """Return relevance-capped graph evidence for prompt payloads.

    Acceptance criteria:
        1. Determinism: Same graph and labels return the same node/edge order.
        2. No mutation: Caller-owned graph mappings are not mutated.
        3. Relevance: Exact or partial label matches are ranked before
           connected context nodes, which are ranked before unrelated nodes.
        4. Safety: Returned metadata warns that omitted graph context is not
           evidence of biological absence.

    Args:
        graph: JSON-serializable graph evidence artifact.
        entity_labels: Source report labels used to rank graph relevance.

    Returns:
        Compact graph payload with capped nodes, capped edges, and metadata.
    """
    nodes = list(graph.get("nodes", []))
    edges = list(graph.get("edges", []))
    matched_node_ids = _matched_graph_node_ids(nodes, entity_labels)
    connected_node_ids = _connected_graph_node_ids(edges, matched_node_ids)
    ranked_nodes = sorted(
        nodes,
        key=lambda node: _graph_node_sort_key(
            node,
            entity_labels=entity_labels,
            matched_node_ids=matched_node_ids,
            connected_node_ids=connected_node_ids,
        ),
    )
    kept_nodes = ranked_nodes[:_MAX_PROMPT_GRAPH_NODES]
    kept_node_ids = {
        str(node.get("node_id", "")).strip()
        for node in kept_nodes
        if str(node.get("node_id", "")).strip()
    }
    incident_edges = [
        edge
        for edge in edges
        if _edge_source_id(edge) in kept_node_ids
        or _edge_target_id(edge) in kept_node_ids
    ]
    ranked_edges = sorted(
        incident_edges,
        key=lambda edge: _graph_edge_sort_key(edge, kept_node_ids),
    )
    kept_edges = ranked_edges[:_MAX_PROMPT_GRAPH_EDGES]
    kept_edge_ids = {
        str(edge.get("edge_id", "")).strip()
        for edge in kept_edges
        if str(edge.get("edge_id", "")).strip()
    }
    return {
        "artifact_id": graph.get("artifact_id"),
        "source_entity_ids": _compact_id_list(
            _string_sequence(graph.get("source_entity_ids", [])),
        ),
        "retrieval_modes": _compact_id_list(
            _string_sequence(graph.get("retrieval_modes", [])),
        ),
        "nodes": [_compact_graph_node_for_prompt(node) for node in kept_nodes],
        "edges": [_compact_graph_edge_for_prompt(edge) for edge in kept_edges],
        "subgraphs": _compact_graph_subgraphs_for_prompt(
            _mapping_sequence(graph.get("subgraphs", [])),
            kept_node_ids=kept_node_ids,
            kept_edge_ids=kept_edge_ids,
        ),
        "missing_entities": _compact_text_list(
            _string_sequence(graph.get("missing_entities", [])),
        ),
        "warnings": _compact_text_list(
            _string_sequence(graph.get("warnings", [])),
        ),
        "truncation": {
            "original_nodes": len(nodes),
            "kept_nodes": len(kept_nodes),
            "original_edges": len(edges),
            "kept_edges": len(kept_edges),
            "original_subgraphs": len(_mapping_sequence(graph.get("subgraphs", []))),
            "kept_subgraphs": min(
                len(_mapping_sequence(graph.get("subgraphs", []))),
                _MAX_PROMPT_TOOL_OUTPUTS,
            ),
            "node_cap": _MAX_PROMPT_GRAPH_NODES,
            "edge_cap": _MAX_PROMPT_GRAPH_EDGES,
            "notice": _PROMPT_CONTEXT_CAP_NOTICE,
        },
    }


def compact_tool_outputs_for_prompt(
    tool_outputs: Sequence[object],
) -> list[dict[str, object]]:
    """Return bounded ToolUniverse artifacts for prompt payloads.

    Acceptance criteria:
        1. Determinism: Tool order and evidence item order are preserved.
        2. No mutation: Tool artifacts are not mutated.
        3. Provenance: Artifact IDs, workflow names, and input entity IDs are
           retained.
        4. Boundedness: Tool count, summary text, and evidence item count are
           capped.

    Args:
        tool_outputs: Full ToolUniverse artifacts.

    Returns:
        Compact list of JSON-serializable tool output dictionaries.
    """
    compact_outputs = []
    for tool in tool_outputs[:_MAX_PROMPT_TOOL_OUTPUTS]:
        payload = tool.model_dump(mode="json")
        evidence_items = _mapping_sequence(payload.get("evidence_items", []))
        compact_outputs.append(
            {
                "artifact_id": payload.get("artifact_id"),
                "workflow": payload.get("workflow"),
                "input_entity_ids": _compact_id_list(
                    _string_sequence(payload.get("input_entity_ids", [])),
                ),
                "summary": truncate_text(
                    payload.get("summary", ""),
                    _MAX_PROMPT_SUMMARY_CHARS,
                ),
                "evidence_items": [
                    _compact_evidence_item_for_prompt(item)
                    for item in evidence_items[:_MAX_PROMPT_TOOL_EVIDENCE_ITEMS]
                ],
                "warnings": _compact_text_list(
                    _string_sequence(payload.get("warnings", [])),
                ),
                "requires_human_review": payload.get(
                    "requires_human_review",
                    True,
                ),
                "truncation": {
                    "original_evidence_items": len(evidence_items),
                    "kept_evidence_items": min(
                        len(evidence_items),
                        _MAX_PROMPT_TOOL_EVIDENCE_ITEMS,
                    ),
                    "notice": _PROMPT_CONTEXT_CAP_NOTICE,
                },
            }
        )
    return compact_outputs


def compact_medea_reasoning_for_prompt(
    medea_reasoning: Mapping[str, Any],
) -> dict[str, object]:
    """Return bounded Medea reasoning for prompt payloads.

    Acceptance criteria:
        1. Determinism: Hypothesis order is preserved.
        2. No mutation: Caller-owned mappings are not mutated.
        3. Provenance: Artifact ID and reasoning mode remain present.
        4. Boundedness: Summary and hypothesis lists are capped.

    Args:
        medea_reasoning: JSON-serializable Medea reasoning artifact.

    Returns:
        Compact Medea reasoning dictionary.
    """
    supported = list(medea_reasoning.get("supported_hypotheses", []))
    weakened = list(medea_reasoning.get("weakened_hypotheses", []))
    return {
        "artifact_id": medea_reasoning.get("artifact_id"),
        "reasoning_mode": medea_reasoning.get("reasoning_mode"),
        "decision_support_role": medea_reasoning.get(
            "decision_support_role",
            "hypothesis_support_only",
        ),
        "downstream_uses": _compact_text_list(
            _string_sequence(medea_reasoning.get("downstream_uses", [])),
            max_items=_MAX_PROMPT_TOOL_EVIDENCE_ITEMS,
        ),
        "summary": truncate_text(
            medea_reasoning.get("summary", ""),
            _MAX_PROMPT_MEDEA_SUMMARY_CHARS,
        ),
        "supported_hypotheses": _compact_text_list(supported),
        "weakened_hypotheses": _compact_text_list(weakened),
        "warnings": _compact_text_list(
            _string_sequence(medea_reasoning.get("warnings", [])),
        ),
        "requires_human_review": medea_reasoning.get(
            "requires_human_review",
            True,
        ),
        "truncation": {
            "original_supported_hypotheses": len(supported),
            "kept_supported_hypotheses": min(
                len(supported),
                _MAX_PROMPT_HYPOTHESES,
            ),
            "original_weakened_hypotheses": len(weakened),
            "kept_weakened_hypotheses": min(
                len(weakened),
                _MAX_PROMPT_HYPOTHESES,
            ),
            "notice": _PROMPT_CONTEXT_CAP_NOTICE,
        },
    }


def compact_clinical_artifact_bundle_for_prompt(
    bundle: ClinicalArtifactBundle,
) -> dict[str, object]:
    """Return bounded clinical artifact bundle for narrative prompts.

    Acceptance criteria:
        1. Determinism: Same bundle returns the same compact payload.
        2. No mutation: The input bundle is not mutated.
        3. Provenance: Source artifact IDs and source chunk IDs are retained.
        4. Boundedness: The nested evidence context is prompt-capped.

    Args:
        bundle: Full clinical artifact bundle.

    Returns:
        JSON-serializable compact bundle for vLLM prompts.
    """
    compact_context = (
        compact_evidence_context_for_prompt(bundle.evidence_context)
        if bundle.evidence_context is not None
        else None
    )
    return {
        "case_id": bundle.case_id,
        "session_id": bundle.session_id,
        "extraction": _compact_extraction_for_prompt(bundle.extraction),
        "entities": (
            bundle.entities.model_dump(mode="json")
            if bundle.entities is not None
            else None
        ),
        "evidence_context": compact_context,
        "phenotype": (
            compact_phenotype_for_prompt(bundle.phenotype)
            if bundle.phenotype is not None
            else None
        ),
        "matrix": (
            compact_matrix_for_prompt(bundle.matrix)
            if bundle.matrix is not None
            else None
        ),
        "sankey": (
            compact_sankey_for_prompt(bundle.sankey)
            if bundle.sankey is not None
            else None
        ),
        "confirmatory": (
            compact_confirmatory_for_prompt(bundle.confirmatory)
            if bundle.confirmatory is not None
            else None
        ),
        "tumor_behavior": (
            compact_tumor_behavior_for_prompt(bundle.tumor_behavior)
            if bundle.tumor_behavior is not None
            else None
        ),
        "decision_brief": (
            compact_decision_brief_for_prompt(bundle.decision_brief)
            if bundle.decision_brief is not None
            else None
        ),
        "claims": compact_claims_for_prompt(bundle.claims),
        "source_artifact_ids": _bundle_source_ids(bundle),
        "source_chunk_ids": _bundle_source_chunk_ids(bundle),
        "truncation_notice": _PROMPT_CONTEXT_CAP_NOTICE,
    }


def compact_clinical_narrative_bundle_for_prompt(
    bundle: ClinicalArtifactBundle,
) -> dict[str, object]:
    """Return a tight clinical bundle for narrative generation.

    Acceptance criteria:
        1. Determinism: Same bundle returns the same compact payload.
        2. No mutation: The input bundle and nested artifacts are not mutated.
        3. Provenance: Source artifact IDs, source chunk IDs, finding IDs, and
           claim IDs remain available for narrative grounding.
        4. Boundedness: Nested artifacts, decision-brief rows, claims, and free
           text use clinical-narrative-specific prompt caps.
        5. Safety: Truncation metadata states that omitted context is not
           evidence of biological absence.

    Args:
        bundle: Full clinical artifact bundle.

    Returns:
        JSON-serializable compact bundle for the narrative prompt.
    """
    return {
        "case_id": bundle.case_id,
        "session_id": bundle.session_id,
        "extraction": _compact_extraction_for_clinical_narrative_prompt(
            bundle.extraction
        ),
        "entities": None,
        "evidence_context": (
            compact_evidence_context_for_clinical_narrative_prompt(
                bundle.evidence_context
            )
            if bundle.evidence_context is not None
            else None
        ),
        "phenotype": (
            compact_phenotype_for_clinical_narrative_prompt(bundle.phenotype)
            if bundle.phenotype is not None
            else None
        ),
        "matrix": (
            compact_matrix_for_clinical_narrative_prompt(bundle.matrix)
            if bundle.matrix is not None
            else None
        ),
        "sankey": (
            compact_sankey_for_clinical_narrative_prompt(bundle.sankey)
            if bundle.sankey is not None
            else None
        ),
        "confirmatory": (
            compact_confirmatory_for_clinical_narrative_prompt(
                bundle.confirmatory
            )
            if bundle.confirmatory is not None
            else None
        ),
        "tumor_behavior": (
            compact_tumor_behavior_for_clinical_narrative_prompt(
                bundle.tumor_behavior
            )
            if bundle.tumor_behavior is not None
            else None
        ),
        "decision_brief": (
            compact_decision_brief_for_clinical_narrative_prompt(
                bundle.decision_brief
            )
            if bundle.decision_brief is not None
            else None
        ),
        "claims": compact_claims_for_clinical_narrative_prompt(bundle.claims),
        "source_artifact_ids": _bundle_source_ids(bundle),
        "source_chunk_ids": _bundle_source_chunk_ids(bundle),
        "truncation": {
            "narrative_claim_cap": _MAX_PROMPT_NARRATIVE_CLAIMS,
            "narrative_row_cap": _MAX_PROMPT_NARRATIVE_DECISION_ROWS,
            "notice": _PROMPT_CONTEXT_CAP_NOTICE,
        },
        "truncation_notice": _PROMPT_CONTEXT_CAP_NOTICE,
    }


def compact_claim_evidence_inputs_for_prompt(
    *,
    context: EvidenceContextBundle,
    phenotype: MolecularPhenotypeOutput,
    matrix: TherapyEvidenceMatrixOutput,
    sankey: MechanismSankeyOutput,
    confirmatory: ConfirmatoryTestingOutput,
    tumor_behavior: TumorBehaviorModelOutput,
) -> dict[str, object]:
    """Return compact inputs for claim-evidence generation.

    Acceptance criteria:
        1. Determinism: Same source artifacts return the same payload.
        2. No mutation: Input artifacts are not mutated.
        3. Provenance: IDs needed for claim source attribution are preserved.
        4. Boundedness: Nested evidence, generated artifacts, and free text use
           claim-evidence-specific prompt caps.
        5. Safety: Truncation metadata states that omitted context is not
           evidence of biological absence.

    Args:
        context: Current evidence context bundle.
        phenotype: Current molecular phenotype artifact.
        matrix: Current molecular-fit matrix artifact.
        sankey: Current mechanism Sankey artifact.
        confirmatory: Current confirmatory testing artifact.
        tumor_behavior: Current tumor-behavior artifact.

    Returns:
        JSON-serializable payload for the claim-evidence structured-output call.
    """
    return {
        "evidence_context": compact_evidence_context_for_claim_evidence_prompt(
            context
        ),
        "molecular_phenotype": compact_phenotype_for_claim_evidence_prompt(
            phenotype
        ),
        "molecular_fit_matrix": compact_matrix_for_claim_evidence_prompt(
            matrix
        ),
        "mechanism_sankey": compact_sankey_for_claim_evidence_prompt(sankey),
        "confirmatory_testing": compact_confirmatory_for_claim_evidence_prompt(
            confirmatory
        ),
        "tumor_behavior_model": compact_tumor_behavior_for_claim_evidence_prompt(
            tumor_behavior
        ),
        "truncation_notice": _PROMPT_CONTEXT_CAP_NOTICE,
    }


def compact_tumor_behavior_inputs_for_prompt(
    *,
    context: EvidenceContextBundle,
    phenotype: MolecularPhenotypeOutput,
    matrix: TherapyEvidenceMatrixOutput,
    sankey: MechanismSankeyOutput,
    confirmatory: ConfirmatoryTestingOutput,
) -> dict[str, object]:
    """Return compact inputs for tumor-behavior generation.

    Acceptance criteria:
        1. Determinism: Same source artifacts return the same payload.
        2. No mutation: Input artifacts are not mutated.
        3. Provenance: IDs needed for state and transition support remain
           available to the model and downstream validation.
        4. Boundedness: Nested evidence, generated artifacts, and free text use
           tumor-behavior-specific prompt caps.
        5. Safety: Truncation metadata states that omitted context is not
           evidence of biological absence.

    Args:
        context: Current evidence context bundle.
        phenotype: Current molecular phenotype artifact.
        matrix: Current molecular-fit matrix artifact.
        sankey: Current mechanism Sankey artifact.
        confirmatory: Current confirmatory testing artifact.

    Returns:
        JSON-serializable payload for the tumor-behavior structured-output call.
    """
    payload = {
        "mims_support_requirement": {
            "required": _mims_evidence_available(context),
            "allowed_support_ids": _available_mims_support_ids(context),
        },
        "evidence_context": compact_evidence_context_for_tumor_behavior_prompt(
            context
        ),
        "molecular_phenotype": compact_phenotype_for_tumor_behavior_prompt(
            phenotype
        ),
        "molecular_fit_matrix": compact_matrix_for_tumor_behavior_prompt(
            matrix
        ),
        "mechanism_sankey": compact_sankey_for_tumor_behavior_prompt(sankey),
        "confirmatory_testing": compact_confirmatory_for_tumor_behavior_prompt(
            confirmatory
        ),
        "truncation_notice": _PROMPT_CONTEXT_CAP_NOTICE,
    }
    return _require_tumor_behavior_payload_bound(payload)


def _require_tumor_behavior_payload_bound(
    payload: Mapping[str, object],
) -> dict[str, object]:
    """Return a tumor-behavior payload within the configured prompt budget.

    Acceptance criteria:
        1. Determinism: Same payload returns the same result or error.
        2. No mutation: Does not mutate the caller-owned payload mapping.
        3. Validation: Rejects payloads exceeding the hard prompt budget.
        4. Safety: Does not truncate IDs or evidence text after domain-specific
           compaction has selected the prompt evidence.

    Args:
        payload: Fully compacted tumor-behavior prompt payload.

    Returns:
        Copy of the bounded prompt payload.

    Raises:
        StructuredArtifactGenerationError: If domain-specific compaction did
            not produce a payload within the safe prompt budget.
    """
    bounded = dict(payload)
    payload_chars = len(json.dumps(bounded, sort_keys=True))
    if payload_chars > _MAX_PROMPT_TUMOR_BEHAVIOR_PAYLOAD_CHARS:
        raise StructuredArtifactGenerationError(
            "TumorBehaviorModelOutput prompt payload exceeds the configured "
            f"character budget: {payload_chars} > "
            f"{_MAX_PROMPT_TUMOR_BEHAVIOR_PAYLOAD_CHARS}"
        )
    return bounded


def compact_evidence_context_for_confirmatory_testing_prompt(
    context: EvidenceContextBundle,
) -> dict[str, object]:
    """Return validation-relevant evidence under confirmatory prompt caps.

    Acceptance criteria:
        1. Determinism: Identical context returns identical compact output.
        2. No mutation: Caller-owned artifacts are not modified.
        3. Grounding: Retained rows preserve artifact and finding identifiers.
        4. Boundedness: Nested evidence uses confirmatory-specific caps.
    """
    compact = compact_evidence_context_for_tumor_behavior_prompt(context)
    extraction = dict(compact["extraction"])
    extraction["molecular_findings"] = extraction["molecular_findings"][
        :_MAX_PROMPT_CONFIRMATORY_INPUT_FINDINGS
    ]
    graph = dict(compact["graph_evidence"])
    graph_nodes = list(graph.get("nodes", []))
    graph_edges = list(graph.get("edges", []))
    graph["nodes"] = graph_nodes[
        :_MAX_PROMPT_CONFIRMATORY_INPUT_GRAPH_NODES
    ]
    graph["edges"] = graph_edges[
        :_MAX_PROMPT_CONFIRMATORY_INPUT_GRAPH_EDGES
    ]
    return {
        "artifact_id": compact["artifact_id"],
        "extraction": extraction,
        "graph_evidence": graph,
        "tool_outputs": compact["tool_outputs"][
            :_MAX_PROMPT_CONFIRMATORY_INPUT_TOOL_OUTPUTS
        ],
        "medea_reasoning": compact["medea_reasoning"],
        "missing_evidence": compact["missing_evidence"],
        "conflicting_evidence": compact["conflicting_evidence"],
        "truncation_notice": _PROMPT_CONTEXT_CAP_NOTICE,
    }


def compact_phenotype_for_confirmatory_testing_prompt(
    phenotype: MolecularPhenotypeOutput,
) -> dict[str, object]:
    """Return phenotype axes needed to select validation tests."""
    compact = compact_phenotype_for_tumor_behavior_prompt(phenotype)
    return {
        **compact,
        "axes": compact["axes"][:_MAX_PROMPT_CONFIRMATORY_INPUT_AXES],
    }


def compact_matrix_for_confirmatory_testing_prompt(
    matrix: TherapyEvidenceMatrixOutput,
) -> dict[str, object]:
    """Return only matrix fields needed to formulate validation tests."""
    compact = compact_matrix_for_tumor_behavior_prompt(matrix)
    rows = [
        {
            "rank": row.get("rank"),
            "molecular_fit": row.get("molecular_fit"),
            "fit_label": row.get("fit_label"),
            "matched_biomarkers": row.get("matched_biomarkers", []),
            "limitations": row.get("limitations"),
            "required_validation": row.get("required_validation"),
            "required_before_use_tests": row.get(
                "required_before_use_tests",
                [],
            ),
            "confidence": row.get("confidence"),
            "evidence_level": row.get("evidence_level"),
        }
        for row in compact["rows"][:_MAX_PROMPT_CONFIRMATORY_INPUT_MATRIX_ROWS]
    ]
    return {
        "artifact_id": compact["artifact_id"],
        "rows": rows,
        "truncation": {
            **compact["truncation"],
            "kept_rows": len(rows),
            "row_cap": _MAX_PROMPT_CONFIRMATORY_INPUT_MATRIX_ROWS,
        },
    }


def compact_sankey_for_confirmatory_testing_prompt(
    sankey: MechanismSankeyOutput,
) -> dict[str, object]:
    """Return bounded mechanism endpoints relevant to confirmatory tests."""
    compact = compact_sankey_for_tumor_behavior_prompt(sankey)
    return {
        **compact,
        "nodes": compact["nodes"][:_MAX_PROMPT_CONFIRMATORY_INPUT_SANKEY_NODES],
        "links": compact["links"][:_MAX_PROMPT_CONFIRMATORY_INPUT_SANKEY_LINKS],
    }


def _require_confirmatory_testing_payload_bound(
    payload: Mapping[str, object],
) -> dict[str, object]:
    """Apply a deterministic final reduction and enforce the hard budget."""
    bounded = json.loads(json.dumps(payload, sort_keys=True))
    payload_chars = len(json.dumps(bounded, sort_keys=True))
    if payload_chars > _MAX_PROMPT_CONFIRMATORY_PAYLOAD_CHARS:
        evidence = bounded["evidence_context"]
        extraction = evidence["extraction"]
        graph = evidence["graph_evidence"]
        phenotype = bounded["molecular_phenotype"]
        matrix = bounded["molecular_fit_matrix"]
        sankey = bounded["mechanism_sankey"]
        extraction["molecular_findings"] = extraction["molecular_findings"][:3]
        graph["nodes"] = graph["nodes"][:2]
        graph["edges"] = graph["edges"][:2]
        phenotype["axes"] = phenotype["axes"][:1]
        matrix["rows"] = matrix["rows"][:1]
        sankey["nodes"] = sankey["nodes"][:3]
        sankey["links"] = sankey["links"][:2]
        bounded["budget_reduction"] = {
            "applied": True,
            "notice": _PROMPT_CONTEXT_CAP_NOTICE,
        }
        payload_chars = len(json.dumps(bounded, sort_keys=True))
    if payload_chars > _MAX_PROMPT_CONFIRMATORY_PAYLOAD_CHARS:
        raise StructuredArtifactGenerationError(
            "ConfirmatoryTestingOutput prompt payload exceeds the configured "
            f"character budget: {payload_chars} > "
            f"{_MAX_PROMPT_CONFIRMATORY_PAYLOAD_CHARS}"
        )
    return bounded


def compact_phenotype_for_prompt(
    phenotype: MolecularPhenotypeOutput,
) -> dict[str, object]:
    """Return a bounded molecular phenotype payload for prompts.

    Acceptance criteria:
        1. Determinism: Same phenotype returns the same compact payload.
        2. No mutation: The phenotype model is not mutated.
        3. Provenance: The artifact ID and supporting finding IDs are kept.
        4. Boundedness: Axis count and free text are capped.

    Args:
        phenotype: Full molecular phenotype artifact.

    Returns:
        JSON-serializable compact phenotype payload.
    """
    axes = phenotype.axes[:_MAX_PROMPT_AXES]
    return {
        "artifact_id": phenotype.artifact_id,
        "axes": [
            {
                "axis_id": axis.axis_id,
                "label": axis.label,
                "supporting_finding_ids": _compact_id_list(
                    axis.supporting_finding_ids
                ),
                "evidence_class": axis.evidence_class,
                "uncertainty": truncate_text(
                    axis.uncertainty,
                    _MAX_PROMPT_GENERATED_TEXT_CHARS,
                ),
                "validation_needed": axis.validation_needed,
            }
            for axis in axes
        ],
        "limitations": _compact_text_list(phenotype.limitations),
        "truncation": {
            "original_axes": len(phenotype.axes),
            "kept_axes": len(axes),
            "axis_cap": _MAX_PROMPT_AXES,
            "notice": _PROMPT_CONTEXT_CAP_NOTICE,
        },
    }


def compact_phenotype_for_sankey_prompt(
    phenotype: MolecularPhenotypeOutput,
) -> dict[str, object]:
    """Return phenotype payload tuned for the mechanism Sankey call.

    Acceptance criteria:
        1. Determinism: Same phenotype returns the same compact payload.
        2. No mutation: The phenotype model is not mutated.
        3. Provenance: Kept axes retain axis IDs and supporting finding IDs.
        4. Boundedness: Axis count and free text use mechanism-Sankey caps.

    Args:
        phenotype: Full molecular phenotype artifact.

    Returns:
        JSON-serializable phenotype payload for the mechanism Sankey prompt.
    """
    compact = compact_phenotype_for_prompt(phenotype)
    axes = [
        {
            **axis,
            "uncertainty": truncate_text(
                str(axis.get("uncertainty", "")),
                _MAX_PROMPT_SANKEY_INPUT_TEXT_CHARS,
            ),
        }
        for axis in compact["axes"][:_MAX_PROMPT_SANKEY_INPUT_AXES]
    ]
    return {
        "artifact_id": compact["artifact_id"],
        "axes": axes,
        "limitations": _compact_sankey_input_texts(
            compact.get("limitations", [])
        ),
    }


def compact_phenotype_for_claim_evidence_prompt(
    phenotype: MolecularPhenotypeOutput,
) -> dict[str, object]:
    """Return phenotype payload tuned for claim evidence prompts.

    Acceptance criteria:
        1. Determinism: Same phenotype returns the same payload.
        2. No mutation: The phenotype model is not mutated.
        3. Provenance: Kept axes retain axis IDs and supporting finding IDs.
        4. Boundedness: Axis count and free text use claim-evidence caps.
    """
    compact = compact_phenotype_for_prompt(phenotype)
    axes = [
        {
            **axis,
            "label": truncate_text(
                str(axis.get("label", "")),
                _MAX_PROMPT_CLAIM_INPUT_TEXT_CHARS,
            ),
            "uncertainty": truncate_text(
                str(axis.get("uncertainty", "")),
                _MAX_PROMPT_CLAIM_INPUT_TEXT_CHARS,
            ),
        }
        for axis in compact["axes"][:_MAX_PROMPT_CLAIM_INPUT_AXES]
    ]
    return {
        "artifact_id": compact["artifact_id"],
        "axes": axes,
        "limitations": _compact_claim_input_texts(
            compact.get("limitations", [])
        ),
        "truncation": {
            "original_axes": compact["truncation"]["original_axes"],
            "kept_axes": len(axes),
            "axis_cap": _MAX_PROMPT_CLAIM_INPUT_AXES,
            "notice": _PROMPT_CONTEXT_CAP_NOTICE,
        },
    }


def compact_phenotype_for_tumor_behavior_prompt(
    phenotype: MolecularPhenotypeOutput,
) -> dict[str, object]:
    """Return phenotype payload tuned for tumor behavior prompts.

    Acceptance criteria:
        1. Determinism: Same phenotype returns the same payload.
        2. No mutation: The phenotype model is not mutated.
        3. Provenance: Kept axes retain axis IDs and supporting finding IDs.
        4. Boundedness: Axis count and free text use tumor-behavior caps.
    """
    compact = compact_phenotype_for_prompt(phenotype)
    axes = [
        {
            **axis,
            "label": truncate_text(
                str(axis.get("label", "")),
                _MAX_PROMPT_TUMOR_INPUT_TEXT_CHARS,
            ),
            "uncertainty": truncate_text(
                str(axis.get("uncertainty", "")),
                _MAX_PROMPT_TUMOR_INPUT_TEXT_CHARS,
            ),
        }
        for axis in compact["axes"][:_MAX_PROMPT_TUMOR_INPUT_AXES]
    ]
    return {
        "artifact_id": compact["artifact_id"],
        "axes": axes,
        "limitations": _compact_tumor_input_texts(
            compact.get("limitations", [])
        ),
        "truncation": {
            "original_axes": compact["truncation"]["original_axes"],
            "kept_axes": len(axes),
            "axis_cap": _MAX_PROMPT_TUMOR_INPUT_AXES,
            "notice": _PROMPT_CONTEXT_CAP_NOTICE,
        },
    }


def compact_phenotype_for_clinical_narrative_prompt(
    phenotype: MolecularPhenotypeOutput,
) -> dict[str, object]:
    """Return phenotype payload tuned for clinical narrative prompts.

    Acceptance criteria:
        1. Determinism: Same phenotype returns the same payload.
        2. No mutation: The phenotype model is not mutated.
        3. Provenance: Kept axes retain axis IDs and supporting finding IDs.
        4. Boundedness: Axis count and free text use narrative caps.
    """
    compact = compact_phenotype_for_prompt(phenotype)
    axes = [
        {
            **axis,
            "label": truncate_text(
                str(axis.get("label", "")),
                _MAX_PROMPT_NARRATIVE_TEXT_CHARS,
            ),
            "uncertainty": truncate_text(
                str(axis.get("uncertainty", "")),
                _MAX_PROMPT_NARRATIVE_TEXT_CHARS,
            ),
        }
        for axis in compact["axes"][:_MAX_PROMPT_NARRATIVE_AXES]
    ]
    return {
        "artifact_id": compact["artifact_id"],
        "axes": axes,
        "limitations": _compact_narrative_texts(compact.get("limitations", [])),
        "truncation": {
            "original_axes": compact["truncation"]["original_axes"],
            "kept_axes": len(axes),
            "axis_cap": _MAX_PROMPT_NARRATIVE_AXES,
            "notice": _PROMPT_CONTEXT_CAP_NOTICE,
        },
    }


def compact_matrix_for_prompt(
    matrix: TherapyEvidenceMatrixOutput,
) -> dict[str, object]:
    """Return a bounded molecular-fit matrix payload for prompts.

    Acceptance criteria:
        1. Determinism: Row order is preserved.
        2. No mutation: The matrix model is not mutated.
        3. Safety: Clinical-use category and validation text are kept.
        4. Boundedness: Row count and free text are capped.

    Args:
        matrix: Full molecular-fit matrix artifact.

    Returns:
        JSON-serializable compact matrix payload.
    """
    rows = matrix.rows[:_MAX_PROMPT_MATRIX_ROWS]
    return {
        "artifact_id": matrix.artifact_id,
        "rows": [
            {
                "rank": row.rank,
                "molecular_fit": truncate_text(
                    row.molecular_fit,
                    _MAX_PROMPT_GENERATED_TEXT_CHARS,
                ),
                "fit_label": row.fit_label,
                "why_from_omics": truncate_text(
                    row.why_from_omics,
                    _MAX_PROMPT_GENERATED_TEXT_CHARS,
                ),
                "evidence_basis": truncate_text(
                    row.evidence_basis,
                    _MAX_PROMPT_GENERATED_TEXT_CHARS,
                ),
                "limitations": truncate_text(
                    row.limitations,
                    _MAX_PROMPT_GENERATED_TEXT_CHARS,
                ),
                "required_validation": truncate_text(
                    row.required_validation,
                    _MAX_PROMPT_GENERATED_TEXT_CHARS,
                ),
                "clinical_use": row.clinical_use,
                "therapy_class": truncate_text(
                    row.therapy_class,
                    _MAX_PROMPT_GENERATED_TEXT_CHARS,
                ),
                "matched_biomarkers": _compact_text_list(
                    row.matched_biomarkers
                ),
                "resistance_risks": _compact_text_list(row.resistance_risks),
                "required_before_use_tests": _compact_text_list(
                    row.required_before_use_tests
                ),
                "confidence": row.confidence,
                "evidence_level": truncate_text(
                    row.evidence_level,
                    _MAX_PROMPT_GENERATED_TEXT_CHARS,
                ),
            }
            for row in rows
        ],
        "truncation": {
            "original_rows": len(matrix.rows),
            "kept_rows": len(rows),
            "row_cap": _MAX_PROMPT_MATRIX_ROWS,
            "notice": _PROMPT_CONTEXT_CAP_NOTICE,
        },
    }


def compact_matrix_for_sankey_prompt(
    matrix: TherapyEvidenceMatrixOutput,
) -> dict[str, object]:
    """Return matrix payload tuned for the mechanism Sankey call.

    Acceptance criteria:
        1. Determinism: Row order is preserved.
        2. No mutation: The matrix model is not mutated.
        3. Safety: Clinical-use category and validation text are kept.
        4. Boundedness: Row count and free text use mechanism-Sankey caps.

    Args:
        matrix: Full molecular-fit matrix artifact.

    Returns:
        JSON-serializable matrix payload for the mechanism Sankey prompt.
    """
    compact = compact_matrix_for_prompt(matrix)
    rows = [
        {
            **row,
            "molecular_fit": truncate_text(
                str(row.get("molecular_fit", "")),
                _MAX_PROMPT_SANKEY_INPUT_TEXT_CHARS,
            ),
            "why_from_omics": truncate_text(
                str(row.get("why_from_omics", "")),
                _MAX_PROMPT_SANKEY_INPUT_TEXT_CHARS,
            ),
            "evidence_basis": truncate_text(
                str(row.get("evidence_basis", "")),
                _MAX_PROMPT_SANKEY_INPUT_TEXT_CHARS,
            ),
            "limitations": truncate_text(
                str(row.get("limitations", "")),
                _MAX_PROMPT_SANKEY_INPUT_TEXT_CHARS,
            ),
            "required_validation": truncate_text(
                str(row.get("required_validation", "")),
                _MAX_PROMPT_SANKEY_INPUT_TEXT_CHARS,
            ),
        }
        for row in compact["rows"][:_MAX_PROMPT_SANKEY_INPUT_MATRIX_ROWS]
    ]
    return {"artifact_id": compact["artifact_id"], "rows": rows}


def compact_matrix_for_claim_evidence_prompt(
    matrix: TherapyEvidenceMatrixOutput,
) -> dict[str, object]:
    """Return matrix payload tuned for claim evidence prompts.

    Acceptance criteria:
        1. Determinism: Row order is preserved.
        2. No mutation: The matrix model is not mutated.
        3. Provenance: Matrix artifact ID and row context are retained.
        4. Boundedness: Row count and free text use claim-evidence caps.
    """
    compact = compact_matrix_for_prompt(matrix)
    rows = [
        {
            **row,
            "molecular_fit": truncate_text(
                str(row.get("molecular_fit", "")),
                _MAX_PROMPT_CLAIM_INPUT_TEXT_CHARS,
            ),
            "why_from_omics": truncate_text(
                str(row.get("why_from_omics", "")),
                _MAX_PROMPT_CLAIM_INPUT_TEXT_CHARS,
            ),
            "evidence_basis": truncate_text(
                str(row.get("evidence_basis", "")),
                _MAX_PROMPT_CLAIM_INPUT_TEXT_CHARS,
            ),
            "limitations": truncate_text(
                str(row.get("limitations", "")),
                _MAX_PROMPT_CLAIM_INPUT_TEXT_CHARS,
            ),
            "required_validation": truncate_text(
                str(row.get("required_validation", "")),
                _MAX_PROMPT_CLAIM_INPUT_TEXT_CHARS,
            ),
            "therapy_class": truncate_text(
                str(row.get("therapy_class", "")),
                _MAX_PROMPT_CLAIM_INPUT_TEXT_CHARS,
            ),
            "matched_biomarkers": _compact_claim_input_texts(
                row.get("matched_biomarkers", [])
            ),
            "resistance_risks": _compact_claim_input_texts(
                row.get("resistance_risks", [])
            ),
            "required_before_use_tests": _compact_claim_input_texts(
                row.get("required_before_use_tests", [])
            ),
            "evidence_level": truncate_text(
                str(row.get("evidence_level", "")),
                _MAX_PROMPT_CLAIM_INPUT_TEXT_CHARS,
            ),
        }
        for row in compact["rows"][:_MAX_PROMPT_CLAIM_INPUT_MATRIX_ROWS]
    ]
    return {
        "artifact_id": compact["artifact_id"],
        "rows": rows,
        "truncation": {
            "original_rows": compact["truncation"]["original_rows"],
            "kept_rows": len(rows),
            "row_cap": _MAX_PROMPT_CLAIM_INPUT_MATRIX_ROWS,
            "notice": _PROMPT_CONTEXT_CAP_NOTICE,
        },
    }


def compact_matrix_for_tumor_behavior_prompt(
    matrix: TherapyEvidenceMatrixOutput,
) -> dict[str, object]:
    """Return matrix payload tuned for tumor behavior prompts.

    Acceptance criteria:
        1. Determinism: Row order is preserved.
        2. No mutation: The matrix model is not mutated.
        3. Provenance: Matrix artifact ID and row context are retained.
        4. Boundedness: Row count and free text use tumor-behavior caps.
    """
    compact = compact_matrix_for_prompt(matrix)
    rows = [
        {
            **row,
            "molecular_fit": truncate_text(
                str(row.get("molecular_fit", "")),
                _MAX_PROMPT_TUMOR_INPUT_TEXT_CHARS,
            ),
            "why_from_omics": truncate_text(
                str(row.get("why_from_omics", "")),
                _MAX_PROMPT_TUMOR_INPUT_TEXT_CHARS,
            ),
            "evidence_basis": truncate_text(
                str(row.get("evidence_basis", "")),
                _MAX_PROMPT_TUMOR_INPUT_TEXT_CHARS,
            ),
            "limitations": truncate_text(
                str(row.get("limitations", "")),
                _MAX_PROMPT_TUMOR_INPUT_TEXT_CHARS,
            ),
            "required_validation": truncate_text(
                str(row.get("required_validation", "")),
                _MAX_PROMPT_TUMOR_INPUT_TEXT_CHARS,
            ),
            "therapy_class": truncate_text(
                str(row.get("therapy_class", "")),
                _MAX_PROMPT_TUMOR_INPUT_TEXT_CHARS,
            ),
            "matched_biomarkers": _compact_tumor_input_texts(
                row.get("matched_biomarkers", [])
            ),
            "resistance_risks": _compact_tumor_input_texts(
                row.get("resistance_risks", [])
            ),
            "required_before_use_tests": _compact_tumor_input_texts(
                row.get("required_before_use_tests", [])
            ),
            "evidence_level": truncate_text(
                str(row.get("evidence_level", "")),
                _MAX_PROMPT_TUMOR_INPUT_TEXT_CHARS,
            ),
        }
        for row in compact["rows"][:_MAX_PROMPT_TUMOR_INPUT_MATRIX_ROWS]
    ]
    return {
        "artifact_id": compact["artifact_id"],
        "rows": rows,
        "truncation": {
            "original_rows": compact["truncation"]["original_rows"],
            "kept_rows": len(rows),
            "row_cap": _MAX_PROMPT_TUMOR_INPUT_MATRIX_ROWS,
            "notice": _PROMPT_CONTEXT_CAP_NOTICE,
        },
    }


def compact_matrix_for_clinical_narrative_prompt(
    matrix: TherapyEvidenceMatrixOutput,
) -> dict[str, object]:
    """Return matrix payload tuned for clinical narrative prompts.

    Acceptance criteria:
        1. Determinism: Row order is preserved.
        2. No mutation: The matrix model is not mutated.
        3. Provenance: Matrix artifact ID and row context are retained.
        4. Boundedness: Row count and free text use narrative caps.
    """
    compact = compact_matrix_for_prompt(matrix)
    rows = [
        {
            **row,
            "molecular_fit": truncate_text(
                str(row.get("molecular_fit", "")),
                _MAX_PROMPT_NARRATIVE_TEXT_CHARS,
            ),
            "why_from_omics": truncate_text(
                str(row.get("why_from_omics", "")),
                _MAX_PROMPT_NARRATIVE_TEXT_CHARS,
            ),
            "evidence_basis": truncate_text(
                str(row.get("evidence_basis", "")),
                _MAX_PROMPT_NARRATIVE_TEXT_CHARS,
            ),
            "limitations": truncate_text(
                str(row.get("limitations", "")),
                _MAX_PROMPT_NARRATIVE_TEXT_CHARS,
            ),
            "required_validation": truncate_text(
                str(row.get("required_validation", "")),
                _MAX_PROMPT_NARRATIVE_TEXT_CHARS,
            ),
            "therapy_class": truncate_text(
                str(row.get("therapy_class", "")),
                _MAX_PROMPT_NARRATIVE_TEXT_CHARS,
            ),
            "matched_biomarkers": _compact_narrative_texts(
                row.get("matched_biomarkers", [])
            ),
            "resistance_risks": _compact_narrative_texts(
                row.get("resistance_risks", [])
            ),
            "required_before_use_tests": _compact_narrative_texts(
                row.get("required_before_use_tests", [])
            ),
            "evidence_level": truncate_text(
                str(row.get("evidence_level", "")),
                _MAX_PROMPT_NARRATIVE_TEXT_CHARS,
            ),
        }
        for row in compact["rows"][:_MAX_PROMPT_NARRATIVE_MATRIX_ROWS]
    ]
    return {
        "artifact_id": compact["artifact_id"],
        "rows": rows,
        "truncation": {
            "original_rows": compact["truncation"]["original_rows"],
            "kept_rows": len(rows),
            "row_cap": _MAX_PROMPT_NARRATIVE_MATRIX_ROWS,
            "notice": _PROMPT_CONTEXT_CAP_NOTICE,
        },
    }


def compact_sankey_for_prompt(
    sankey: MechanismSankeyOutput,
) -> dict[str, object]:
    """Return a bounded mechanism Sankey payload for prompts.

    Acceptance criteria:
        1. Determinism: Node and link order are preserved.
        2. No mutation: The Sankey model is not mutated.
        3. Provenance: Node IDs, endpoint IDs, and source artifact IDs are
           retained for kept links.
        4. Boundedness: Node and link counts are capped.

    Args:
        sankey: Full mechanism Sankey artifact.

    Returns:
        JSON-serializable compact Sankey payload.
    """
    nodes = sankey.nodes[:_MAX_PROMPT_SANKEY_NODES]
    kept_node_ids = {node.node_id for node in nodes}
    endpoint_links = [
        link
        for link in sankey.links
        if link.source_node_id in kept_node_ids
        or link.target_node_id in kept_node_ids
    ]
    links = endpoint_links[:_MAX_PROMPT_SANKEY_LINKS]
    return {
        "artifact_id": sankey.artifact_id,
        "nodes": [
            {
                "node_id": node.node_id,
                "label": node.label,
                "kind": node.kind,
                "evidence_class": node.evidence_class,
            }
            for node in nodes
        ],
        "links": [
            {
                "source_node_id": link.source_node_id,
                "target_node_id": link.target_node_id,
                "value": link.value,
                "claim_class": link.claim_class,
                "validation_required": link.validation_required,
                "source_artifact_ids": _compact_id_list(
                    link.source_artifact_ids
                ),
            }
            for link in links
        ],
        "truncation": {
            "original_nodes": len(sankey.nodes),
            "kept_nodes": len(nodes),
            "original_links": len(sankey.links),
            "kept_links": len(links),
            "node_cap": _MAX_PROMPT_SANKEY_NODES,
            "link_cap": _MAX_PROMPT_SANKEY_LINKS,
            "notice": _PROMPT_CONTEXT_CAP_NOTICE,
        },
    }


def compact_sankey_for_claim_evidence_prompt(
    sankey: MechanismSankeyOutput,
) -> dict[str, object]:
    """Return Sankey payload tuned for claim evidence prompts.

    Acceptance criteria:
        1. Determinism: Node and link order are preserved.
        2. No mutation: The Sankey model is not mutated.
        3. Provenance: Kept links retain source artifact IDs.
        4. Boundedness: Node and link counts use claim-evidence caps.
    """
    compact = compact_sankey_for_prompt(sankey)
    nodes = [
        {
            **node,
            "label": truncate_text(
                str(node.get("label", "")),
                _MAX_PROMPT_CLAIM_INPUT_TEXT_CHARS,
            ),
        }
        for node in compact["nodes"][:_MAX_PROMPT_CLAIM_INPUT_SANKEY_NODES]
    ]
    kept_node_ids = {str(node.get("node_id", "")) for node in nodes}
    links = [
        link
        for link in compact["links"]
        if str(link.get("source_node_id", "")) in kept_node_ids
        or str(link.get("target_node_id", "")) in kept_node_ids
    ][:_MAX_PROMPT_CLAIM_INPUT_SANKEY_LINKS]
    return {
        "artifact_id": compact["artifact_id"],
        "nodes": nodes,
        "links": links,
        "truncation": {
            "original_nodes": compact["truncation"]["original_nodes"],
            "kept_nodes": len(nodes),
            "original_links": compact["truncation"]["original_links"],
            "kept_links": len(links),
            "node_cap": _MAX_PROMPT_CLAIM_INPUT_SANKEY_NODES,
            "link_cap": _MAX_PROMPT_CLAIM_INPUT_SANKEY_LINKS,
            "notice": _PROMPT_CONTEXT_CAP_NOTICE,
        },
    }


def compact_sankey_for_tumor_behavior_prompt(
    sankey: MechanismSankeyOutput,
) -> dict[str, object]:
    """Return Sankey payload tuned for tumor behavior prompts.

    Acceptance criteria:
        1. Determinism: Node and link order are preserved.
        2. No mutation: The Sankey model is not mutated.
        3. Provenance: Kept links retain source artifact IDs.
        4. Boundedness: Node and link counts use tumor-behavior caps.
    """
    compact = compact_sankey_for_prompt(sankey)
    nodes = [
        {
            **node,
            "label": truncate_text(
                str(node.get("label", "")),
                _MAX_PROMPT_TUMOR_INPUT_TEXT_CHARS,
            ),
        }
        for node in compact["nodes"][:_MAX_PROMPT_TUMOR_INPUT_SANKEY_NODES]
    ]
    kept_node_ids = {str(node.get("node_id", "")) for node in nodes}
    links = [
        link
        for link in compact["links"]
        if str(link.get("source_node_id", "")) in kept_node_ids
        or str(link.get("target_node_id", "")) in kept_node_ids
    ][:_MAX_PROMPT_TUMOR_INPUT_SANKEY_LINKS]
    return {
        "artifact_id": compact["artifact_id"],
        "nodes": nodes,
        "links": links,
        "truncation": {
            "original_nodes": compact["truncation"]["original_nodes"],
            "kept_nodes": len(nodes),
            "original_links": compact["truncation"]["original_links"],
            "kept_links": len(links),
            "node_cap": _MAX_PROMPT_TUMOR_INPUT_SANKEY_NODES,
            "link_cap": _MAX_PROMPT_TUMOR_INPUT_SANKEY_LINKS,
            "notice": _PROMPT_CONTEXT_CAP_NOTICE,
        },
    }


def compact_sankey_for_clinical_narrative_prompt(
    sankey: MechanismSankeyOutput,
) -> dict[str, object]:
    """Return Sankey payload tuned for clinical narrative prompts.

    Acceptance criteria:
        1. Determinism: Node and link order are preserved.
        2. No mutation: The Sankey model is not mutated.
        3. Provenance: Kept links retain source artifact IDs.
        4. Boundedness: Node and link counts use narrative caps.
    """
    compact = compact_sankey_for_prompt(sankey)
    nodes = [
        {
            **node,
            "label": truncate_text(
                str(node.get("label", "")),
                _MAX_PROMPT_NARRATIVE_TEXT_CHARS,
            ),
        }
        for node in compact["nodes"][:_MAX_PROMPT_NARRATIVE_SANKEY_NODES]
    ]
    kept_node_ids = {str(node.get("node_id", "")) for node in nodes}
    links = [
        link
        for link in compact["links"]
        if str(link.get("source_node_id", "")) in kept_node_ids
        or str(link.get("target_node_id", "")) in kept_node_ids
    ][:_MAX_PROMPT_NARRATIVE_SANKEY_LINKS]
    return {
        "artifact_id": compact["artifact_id"],
        "nodes": nodes,
        "links": links,
        "truncation": {
            "original_nodes": compact["truncation"]["original_nodes"],
            "kept_nodes": len(nodes),
            "original_links": compact["truncation"]["original_links"],
            "kept_links": len(links),
            "node_cap": _MAX_PROMPT_NARRATIVE_SANKEY_NODES,
            "link_cap": _MAX_PROMPT_NARRATIVE_SANKEY_LINKS,
            "notice": _PROMPT_CONTEXT_CAP_NOTICE,
        },
    }


def compact_confirmatory_for_prompt(
    confirmatory: ConfirmatoryTestingOutput,
) -> dict[str, object]:
    """Return a bounded confirmatory-testing payload for prompts.

    Acceptance criteria:
        1. Determinism: Test order is preserved.
        2. No mutation: The confirmatory-testing model is not mutated.
        3. Provenance: Test IDs and source claim IDs are retained.
        4. Boundedness: Test count and free text are capped.

    Args:
        confirmatory: Full confirmatory-testing artifact.

    Returns:
        JSON-serializable compact confirmatory-testing payload.
    """
    tests = confirmatory.tests[:_MAX_PROMPT_CONFIRMATORY_TESTS]
    return {
        "artifact_id": confirmatory.artifact_id,
        "tests": [
            {
                "test_id": test.test_id,
                "question": truncate_text(
                    test.question,
                    _MAX_PROMPT_GENERATED_TEXT_CHARS,
                ),
                "why_it_matters": truncate_text(
                    test.why_it_matters,
                    _MAX_PROMPT_GENERATED_TEXT_CHARS,
                ),
                "positive_interpretation": truncate_text(
                    test.positive_interpretation,
                    _MAX_PROMPT_GENERATED_TEXT_CHARS,
                ),
                "negative_interpretation": truncate_text(
                    test.negative_interpretation,
                    _MAX_PROMPT_GENERATED_TEXT_CHARS,
                ),
                "priority": test.priority,
                "evidence_gap": truncate_text(
                    test.evidence_gap,
                    _MAX_PROMPT_GENERATED_TEXT_CHARS,
                ),
                "source_claim_ids": _compact_id_list(test.source_claim_ids),
            }
            for test in tests
        ],
        "must_not_assume": _compact_text_list(confirmatory.must_not_assume),
        "truncation": {
            "original_tests": len(confirmatory.tests),
            "kept_tests": len(tests),
            "test_cap": _MAX_PROMPT_CONFIRMATORY_TESTS,
            "notice": _PROMPT_CONTEXT_CAP_NOTICE,
        },
    }


def compact_confirmatory_for_claim_evidence_prompt(
    confirmatory: ConfirmatoryTestingOutput,
) -> dict[str, object]:
    """Return confirmatory-testing payload tuned for claim evidence prompts.

    Acceptance criteria:
        1. Determinism: Test order is preserved.
        2. No mutation: The confirmatory-testing model is not mutated.
        3. Provenance: Test IDs and source claim IDs are retained.
        4. Boundedness: Test count and free text use claim-evidence caps.
    """
    compact = compact_confirmatory_for_prompt(confirmatory)
    tests = [
        {
            **test,
            "question": truncate_text(
                str(test.get("question", "")),
                _MAX_PROMPT_CLAIM_INPUT_TEXT_CHARS,
            ),
            "why_it_matters": truncate_text(
                str(test.get("why_it_matters", "")),
                _MAX_PROMPT_CLAIM_INPUT_TEXT_CHARS,
            ),
            "positive_interpretation": truncate_text(
                str(test.get("positive_interpretation", "")),
                _MAX_PROMPT_CLAIM_INPUT_TEXT_CHARS,
            ),
            "negative_interpretation": truncate_text(
                str(test.get("negative_interpretation", "")),
                _MAX_PROMPT_CLAIM_INPUT_TEXT_CHARS,
            ),
            "evidence_gap": truncate_text(
                str(test.get("evidence_gap", "")),
                _MAX_PROMPT_CLAIM_INPUT_TEXT_CHARS,
            ),
        }
        for test in compact["tests"][:_MAX_PROMPT_CLAIM_INPUT_CONFIRMATORY_TESTS]
    ]
    return {
        "artifact_id": compact["artifact_id"],
        "tests": tests,
        "must_not_assume": _compact_claim_input_texts(
            compact.get("must_not_assume", [])
        ),
        "truncation": {
            "original_tests": compact["truncation"]["original_tests"],
            "kept_tests": len(tests),
            "test_cap": _MAX_PROMPT_CLAIM_INPUT_CONFIRMATORY_TESTS,
            "notice": _PROMPT_CONTEXT_CAP_NOTICE,
        },
    }


def compact_confirmatory_for_tumor_behavior_prompt(
    confirmatory: ConfirmatoryTestingOutput,
) -> dict[str, object]:
    """Return confirmatory-testing payload tuned for tumor behavior prompts.

    Acceptance criteria:
        1. Determinism: Test order is preserved.
        2. No mutation: The confirmatory-testing model is not mutated.
        3. Provenance: Test IDs and source claim IDs are retained.
        4. Boundedness: Test count and free text use tumor-behavior caps.
    """
    compact = compact_confirmatory_for_prompt(confirmatory)
    tests = [
        {
            **test,
            "question": truncate_text(
                str(test.get("question", "")),
                _MAX_PROMPT_TUMOR_INPUT_TEXT_CHARS,
            ),
            "why_it_matters": truncate_text(
                str(test.get("why_it_matters", "")),
                _MAX_PROMPT_TUMOR_INPUT_TEXT_CHARS,
            ),
            "positive_interpretation": truncate_text(
                str(test.get("positive_interpretation", "")),
                _MAX_PROMPT_TUMOR_INPUT_TEXT_CHARS,
            ),
            "negative_interpretation": truncate_text(
                str(test.get("negative_interpretation", "")),
                _MAX_PROMPT_TUMOR_INPUT_TEXT_CHARS,
            ),
            "evidence_gap": truncate_text(
                str(test.get("evidence_gap", "")),
                _MAX_PROMPT_TUMOR_INPUT_TEXT_CHARS,
            ),
        }
        for test in compact["tests"][:_MAX_PROMPT_TUMOR_INPUT_CONFIRMATORY_TESTS]
    ]
    return {
        "artifact_id": compact["artifact_id"],
        "tests": tests,
        "must_not_assume": _compact_tumor_input_texts(
            compact.get("must_not_assume", [])
        ),
        "truncation": {
            "original_tests": compact["truncation"]["original_tests"],
            "kept_tests": len(tests),
            "test_cap": _MAX_PROMPT_TUMOR_INPUT_CONFIRMATORY_TESTS,
            "notice": _PROMPT_CONTEXT_CAP_NOTICE,
        },
    }


def compact_confirmatory_for_clinical_narrative_prompt(
    confirmatory: ConfirmatoryTestingOutput,
) -> dict[str, object]:
    """Return confirmatory-testing payload tuned for narrative prompts.

    Acceptance criteria:
        1. Determinism: Test order is preserved.
        2. No mutation: The confirmatory-testing model is not mutated.
        3. Provenance: Test IDs and source claim IDs are retained.
        4. Boundedness: Test count and free text use narrative caps.
    """
    compact = compact_confirmatory_for_prompt(confirmatory)
    tests = [
        {
            **test,
            "question": truncate_text(
                str(test.get("question", "")),
                _MAX_PROMPT_NARRATIVE_TEXT_CHARS,
            ),
            "why_it_matters": truncate_text(
                str(test.get("why_it_matters", "")),
                _MAX_PROMPT_NARRATIVE_TEXT_CHARS,
            ),
            "positive_interpretation": truncate_text(
                str(test.get("positive_interpretation", "")),
                _MAX_PROMPT_NARRATIVE_TEXT_CHARS,
            ),
            "negative_interpretation": truncate_text(
                str(test.get("negative_interpretation", "")),
                _MAX_PROMPT_NARRATIVE_TEXT_CHARS,
            ),
            "evidence_gap": truncate_text(
                str(test.get("evidence_gap", "")),
                _MAX_PROMPT_NARRATIVE_TEXT_CHARS,
            ),
        }
        for test in compact["tests"][
            :_MAX_PROMPT_NARRATIVE_CONFIRMATORY_TESTS
        ]
    ]
    return {
        "artifact_id": compact["artifact_id"],
        "tests": tests,
        "must_not_assume": _compact_narrative_texts(
            compact.get("must_not_assume", [])
        ),
        "truncation": {
            "original_tests": compact["truncation"]["original_tests"],
            "kept_tests": len(tests),
            "test_cap": _MAX_PROMPT_NARRATIVE_CONFIRMATORY_TESTS,
            "notice": _PROMPT_CONTEXT_CAP_NOTICE,
        },
    }


def compact_tumor_behavior_for_prompt(
    tumor_behavior: TumorBehaviorModelOutput,
) -> dict[str, object]:
    """Return a bounded tumor-behavior payload for prompts.

    Acceptance criteria:
        1. Determinism: State and transition order are preserved.
        2. No mutation: The tumor-behavior model is not mutated.
        3. Provenance: Support IDs for kept states and transitions are kept.
        4. Boundedness: State, transition, support-ID, and free-text payloads
           are capped.

    Args:
        tumor_behavior: Full tumor-behavior artifact.

    Returns:
        JSON-serializable compact tumor-behavior payload.
    """
    states = tumor_behavior.state_evidence[:_MAX_PROMPT_TUMOR_STATES]
    transitions = tumor_behavior.transition_hypotheses[
        :_MAX_PROMPT_TRANSITIONS
    ]
    return {
        "artifact_id": tumor_behavior.artifact_id,
        "state_evidence": [
            {
                "state_label": state.state_label,
                "supporting_findings": _compact_id_list(
                    state.supporting_findings
                ),
                "graph_support": _compact_id_list(state.graph_support),
                "tool_support": _compact_id_list(state.tool_support),
                "medea_support": _compact_id_list(state.medea_support),
                "evidence_class": state.evidence_class,
                "uncertainty": truncate_text(
                    state.uncertainty,
                    _MAX_PROMPT_GENERATED_TEXT_CHARS,
                ),
                "validation_needed": state.validation_needed,
            }
            for state in states
        ],
        "transition_hypotheses": [
            {
                "from_state": transition.from_state,
                "to_state": transition.to_state,
                "rationale": truncate_text(
                    transition.rationale,
                    _MAX_PROMPT_GENERATED_TEXT_CHARS,
                ),
                "supporting_artifacts": _compact_id_list(
                    transition.supporting_artifacts
                ),
                "confidence_label": transition.confidence_label,
                "validation_status": transition.validation_status,
                "hypothesis_generating": transition.hypothesis_generating,
            }
            for transition in transitions
        ],
        "limitations": _compact_text_list(tumor_behavior.limitations),
        "truncation": {
            "original_state_evidence": len(tumor_behavior.state_evidence),
            "kept_state_evidence": len(states),
            "original_transition_hypotheses": len(
                tumor_behavior.transition_hypotheses
            ),
            "kept_transition_hypotheses": len(transitions),
            "state_cap": _MAX_PROMPT_TUMOR_STATES,
            "transition_cap": _MAX_PROMPT_TRANSITIONS,
            "notice": _PROMPT_CONTEXT_CAP_NOTICE,
        },
    }


def compact_tumor_behavior_for_claim_evidence_prompt(
    tumor_behavior: TumorBehaviorModelOutput,
) -> dict[str, object]:
    """Return tumor-behavior payload tuned for claim evidence prompts.

    Acceptance criteria:
        1. Determinism: State and transition order are preserved.
        2. No mutation: The tumor-behavior model is not mutated.
        3. Provenance: Support IDs for kept states and transitions are kept.
        4. Boundedness: State, transition, and free-text payloads use
           claim-evidence caps.
    """
    compact = compact_tumor_behavior_for_prompt(tumor_behavior)
    states = [
        {
            **state,
            "uncertainty": truncate_text(
                str(state.get("uncertainty", "")),
                _MAX_PROMPT_CLAIM_INPUT_TEXT_CHARS,
            ),
        }
        for state in compact["state_evidence"][
            :_MAX_PROMPT_CLAIM_INPUT_TUMOR_STATES
        ]
    ]
    transitions = [
        {
            **transition,
            "rationale": truncate_text(
                str(transition.get("rationale", "")),
                _MAX_PROMPT_CLAIM_INPUT_TEXT_CHARS,
            ),
        }
        for transition in compact["transition_hypotheses"][
            :_MAX_PROMPT_CLAIM_INPUT_TRANSITIONS
        ]
    ]
    return {
        "artifact_id": compact["artifact_id"],
        "state_evidence": states,
        "transition_hypotheses": transitions,
        "limitations": _compact_claim_input_texts(
            compact.get("limitations", [])
        ),
        "truncation": {
            "original_state_evidence": compact["truncation"][
                "original_state_evidence"
            ],
            "kept_state_evidence": len(states),
            "original_transition_hypotheses": compact["truncation"][
                "original_transition_hypotheses"
            ],
            "kept_transition_hypotheses": len(transitions),
            "state_cap": _MAX_PROMPT_CLAIM_INPUT_TUMOR_STATES,
            "transition_cap": _MAX_PROMPT_CLAIM_INPUT_TRANSITIONS,
            "notice": _PROMPT_CONTEXT_CAP_NOTICE,
        },
    }


def compact_tumor_behavior_for_clinical_narrative_prompt(
    tumor_behavior: TumorBehaviorModelOutput,
) -> dict[str, object]:
    """Return tumor-behavior payload tuned for narrative prompts.

    Acceptance criteria:
        1. Determinism: State and transition order are preserved.
        2. No mutation: The tumor-behavior model is not mutated.
        3. Provenance: Support IDs for kept states and transitions are kept.
        4. Boundedness: State, transition, and free-text payloads use
           narrative caps.
    """
    compact = compact_tumor_behavior_for_prompt(tumor_behavior)
    states = [
        {
            **state,
            "uncertainty": truncate_text(
                str(state.get("uncertainty", "")),
                _MAX_PROMPT_NARRATIVE_TEXT_CHARS,
            ),
        }
        for state in compact["state_evidence"][
            :_MAX_PROMPT_NARRATIVE_TUMOR_STATES
        ]
    ]
    transitions = [
        {
            **transition,
            "rationale": truncate_text(
                str(transition.get("rationale", "")),
                _MAX_PROMPT_NARRATIVE_TEXT_CHARS,
            ),
        }
        for transition in compact["transition_hypotheses"][
            :_MAX_PROMPT_NARRATIVE_TRANSITIONS
        ]
    ]
    return {
        "artifact_id": compact["artifact_id"],
        "state_evidence": states,
        "transition_hypotheses": transitions,
        "limitations": _compact_narrative_texts(
            compact.get("limitations", [])
        ),
        "truncation": {
            "original_state_evidence": compact["truncation"][
                "original_state_evidence"
            ],
            "kept_state_evidence": len(states),
            "original_transition_hypotheses": compact["truncation"][
                "original_transition_hypotheses"
            ],
            "kept_transition_hypotheses": len(transitions),
            "state_cap": _MAX_PROMPT_NARRATIVE_TUMOR_STATES,
            "transition_cap": _MAX_PROMPT_NARRATIVE_TRANSITIONS,
            "notice": _PROMPT_CONTEXT_CAP_NOTICE,
        },
    }


def compact_decision_brief_for_prompt(
    brief: OncologistDecisionBrief,
) -> dict[str, object]:
    """Return a bounded oncologist decision brief payload for prompts.

    Acceptance criteria:
        1. Determinism: Same brief returns the same compact payload.
        2. No mutation: The decision brief is not mutated.
        3. Provenance: Source artifact IDs and source chunk IDs are retained.
        4. Boundedness: Row counts and free text are capped for narrative use.
    """
    return {
        "artifact_id": brief.artifact_id,
        "clinical_decision_summary": truncate_text(
            brief.clinical_decision_summary,
            _MAX_PROMPT_GENERATED_TEXT_CHARS,
        ),
        "current_tumor_state": brief.current_tumor_state.model_dump(mode="json"),
        "actionable_biology": [
            item.model_dump(mode="json")
            for item in brief.actionable_biology[:_MAX_PROMPT_MATRIX_ROWS]
        ],
        "ranked_treatment_options": [
            item.model_dump(mode="json")
            for item in brief.ranked_treatment_options[:_MAX_PROMPT_MATRIX_ROWS]
        ],
        "treatment_pressure_map": [
            item.model_dump(mode="json")
            for item in brief.treatment_pressure_map[:_MAX_PROMPT_MATRIX_ROWS]
        ],
        "resistance_forecast": [
            item.model_dump(mode="json")
            for item in brief.resistance_forecast[:_MAX_PROMPT_TRANSITIONS]
        ],
        "biomarker_watch_list": [
            item.model_dump(mode="json")
            for item in brief.biomarker_watch_list[:_MAX_PROMPT_FINDINGS]
        ],
        "retesting_triggers": [
            item.model_dump(mode="json")
            for item in brief.retesting_triggers[:_MAX_PROMPT_TRANSITIONS]
        ],
        "next_test_recommendations": [
            item.model_dump(mode="json")
            for item in brief.next_test_recommendations[:_MAX_PROMPT_TRANSITIONS]
        ],
        "evidence_limitations": [
            item.model_dump(mode="json")
            for item in brief.evidence_limitations[:_MAX_PROMPT_HYPOTHESES]
        ],
        "translational_assessment": (
            brief.translational_assessment.model_dump(mode="json")
            if brief.translational_assessment is not None
            else None
        ),
        "source_artifact_ids": _compact_id_list(brief.source_artifact_ids),
        "source_chunk_ids": _compact_id_list(brief.source_chunk_ids),
        "validation_status": brief.validation_status,
        "truncation": {
            "actionable_biology": len(brief.actionable_biology),
            "ranked_treatment_options": len(brief.ranked_treatment_options),
            "treatment_pressure_map": len(brief.treatment_pressure_map),
            "resistance_forecast": len(brief.resistance_forecast),
            "biomarker_watch_list": len(brief.biomarker_watch_list),
            "retesting_triggers": len(brief.retesting_triggers),
            "next_test_recommendations": len(brief.next_test_recommendations),
            "notice": _PROMPT_CONTEXT_CAP_NOTICE,
        },
    }


def compact_decision_brief_for_clinical_narrative_prompt(
    brief: OncologistDecisionBrief,
) -> dict[str, object]:
    """Return decision brief payload tuned for narrative prompts.

    Acceptance criteria:
        1. Determinism: Same brief returns the same compact payload.
        2. No mutation: The decision brief is not mutated.
        3. Provenance: Source artifact IDs and source chunk IDs are retained.
        4. Boundedness: Decision rows and nested free text use narrative caps.
    """
    return {
        "artifact_id": brief.artifact_id,
        "clinical_decision_summary": truncate_text(
            brief.clinical_decision_summary,
            _MAX_PROMPT_NARRATIVE_SUMMARY_CHARS,
        ),
        "current_tumor_state": _compact_narrative_mapping(
            brief.current_tumor_state.model_dump(mode="json")
        ),
        "actionable_biology": [
            _compact_narrative_mapping(item.model_dump(mode="json"))
            for item in brief.actionable_biology[
                :_MAX_PROMPT_NARRATIVE_DECISION_ROWS
            ]
        ],
        "ranked_treatment_options": [
            _compact_narrative_mapping(item.model_dump(mode="json"))
            for item in brief.ranked_treatment_options[
                :_MAX_PROMPT_NARRATIVE_DECISION_ROWS
            ]
        ],
        "treatment_pressure_map": [
            _compact_narrative_mapping(item.model_dump(mode="json"))
            for item in brief.treatment_pressure_map[
                :_MAX_PROMPT_NARRATIVE_DECISION_ROWS
            ]
        ],
        "resistance_forecast": [
            _compact_narrative_mapping(item.model_dump(mode="json"))
            for item in brief.resistance_forecast[
                :_MAX_PROMPT_NARRATIVE_DECISION_ROWS
            ]
        ],
        "biomarker_watch_list": [
            _compact_narrative_mapping(item.model_dump(mode="json"))
            for item in brief.biomarker_watch_list[
                :_MAX_PROMPT_NARRATIVE_DECISION_ROWS
            ]
        ],
        "retesting_triggers": [
            _compact_narrative_mapping(item.model_dump(mode="json"))
            for item in brief.retesting_triggers[
                :_MAX_PROMPT_NARRATIVE_DECISION_ROWS
            ]
        ],
        "next_test_recommendations": [
            _compact_narrative_mapping(item.model_dump(mode="json"))
            for item in brief.next_test_recommendations[
                :_MAX_PROMPT_NARRATIVE_DECISION_ROWS
            ]
        ],
        "translational_assessment": (
            _compact_narrative_mapping(
                brief.translational_assessment.model_dump(mode="json")
            )
            if brief.translational_assessment is not None
            else None
        ),
        "therapy_escape_sankey_paths": [
            _compact_narrative_mapping(item.model_dump(mode="json"))
            for item in brief.therapy_escape_sankey_paths[
                :_MAX_PROMPT_NARRATIVE_DECISION_ROWS
            ]
        ],
        "evidence_sentence_map": [
            _compact_narrative_mapping(item.model_dump(mode="json"))
            for item in brief.evidence_sentence_map[
                :_MAX_PROMPT_NARRATIVE_DECISION_ROWS
            ]
        ],
        "evidence_limitations": [
            _compact_narrative_mapping(item.model_dump(mode="json"))
            for item in brief.evidence_limitations[
                :_MAX_PROMPT_NARRATIVE_DECISION_ROWS
            ]
        ],
        "source_artifact_ids": _compact_id_list(brief.source_artifact_ids),
        "source_chunk_ids": _compact_id_list(brief.source_chunk_ids),
        "validation_status": brief.validation_status,
        "truncation": {
            "actionable_biology": len(brief.actionable_biology),
            "ranked_treatment_options": len(brief.ranked_treatment_options),
            "treatment_pressure_map": len(brief.treatment_pressure_map),
            "resistance_forecast": len(brief.resistance_forecast),
            "biomarker_watch_list": len(brief.biomarker_watch_list),
            "retesting_triggers": len(brief.retesting_triggers),
            "next_test_recommendations": len(brief.next_test_recommendations),
            "row_cap": _MAX_PROMPT_NARRATIVE_DECISION_ROWS,
            "notice": _PROMPT_CONTEXT_CAP_NOTICE,
        },
    }


def compact_claims_for_prompt(
    claims: Sequence[ClaimEvidenceOutput],
) -> list[dict[str, object]]:
    """Return bounded claim-evidence payloads for prompts.

    Acceptance criteria:
        1. Determinism: Claim order is preserved.
        2. No mutation: Claim models are not mutated.
        3. Provenance: Claim IDs and source artifact IDs are retained.
        4. Boundedness: Claim count and free text are capped.

    Args:
        claims: Full claim evidence records.

    Returns:
        JSON-serializable compact claim payloads.
    """
    kept_claims = claims[:_MAX_PROMPT_CLAIMS]
    return [
        {
            "claim_id": claim.claim_id,
            "claim": truncate_text(
                claim.claim,
                _MAX_PROMPT_GENERATED_TEXT_CHARS,
            ),
            "claim_class": claim.claim_class,
            "source_artifact_ids": _compact_id_list(
                claim.source_artifact_ids
            ),
            "evidence_source": truncate_text(
                claim.evidence_source,
                _MAX_PROMPT_GENERATED_TEXT_CHARS,
            ),
            "relevance": truncate_text(
                claim.relevance,
                _MAX_PROMPT_GENERATED_TEXT_CHARS,
            ),
            "limitations": truncate_text(
                claim.limitations,
                _MAX_PROMPT_GENERATED_TEXT_CHARS,
            ),
            "validation_status": claim.validation_status,
            "truncation": {
                "original_claims": len(claims),
                "kept_claims": len(kept_claims),
                "claim_cap": _MAX_PROMPT_CLAIMS,
                "notice": _PROMPT_CONTEXT_CAP_NOTICE,
            },
        }
        for claim in kept_claims
    ]


def compact_claims_for_clinical_narrative_prompt(
    claims: Sequence[ClaimEvidenceOutput],
) -> list[dict[str, object]]:
    """Return claim-evidence payloads tuned for narrative prompts.

    Acceptance criteria:
        1. Determinism: Claim order is preserved.
        2. No mutation: Claim models are not mutated.
        3. Provenance: Claim IDs and source artifact IDs are retained.
        4. Boundedness: Claim count and free text use narrative caps.
    """
    kept_claims = claims[:_MAX_PROMPT_NARRATIVE_CLAIMS]
    return [
        {
            "claim_id": claim.claim_id,
            "claim": truncate_text(
                claim.claim,
                _MAX_PROMPT_NARRATIVE_TEXT_CHARS,
            ),
            "claim_class": claim.claim_class,
            "source_artifact_ids": _compact_id_list(
                claim.source_artifact_ids
            ),
            "evidence_source": truncate_text(
                claim.evidence_source,
                _MAX_PROMPT_NARRATIVE_TEXT_CHARS,
            ),
            "relevance": truncate_text(
                claim.relevance,
                _MAX_PROMPT_NARRATIVE_TEXT_CHARS,
            ),
            "limitations": truncate_text(
                claim.limitations,
                _MAX_PROMPT_NARRATIVE_TEXT_CHARS,
            ),
            "validation_status": claim.validation_status,
        }
        for claim in kept_claims
    ]


def _compact_extraction_for_prompt(
    extraction: ReportExtractionOutput,
) -> dict[str, object]:
    findings = [
        _compact_finding_for_prompt(finding)
        for finding in extraction.molecular_findings[:_MAX_PROMPT_FINDINGS]
    ]
    return {
        "artifact_id": extraction.artifact_id,
        "report_type": extraction.report_type,
        "disease": extraction.disease,
        "specimen": extraction.specimen,
        "tumor_percentage": extraction.tumor_percentage,
        "molecular_findings": findings,
        "negative_findings": extraction.negative_findings,
        "assay_limitations": extraction.assay_limitations,
        "source_file_id": extraction.source_file_id,
        "needs_human_review": extraction.needs_human_review,
        "truncation": {
            "original_molecular_findings": len(extraction.molecular_findings),
            "kept_molecular_findings": len(findings),
        },
    }


def _compact_extraction_for_clinical_narrative_prompt(
    extraction: ReportExtractionOutput,
) -> dict[str, object]:
    """Return extraction payload tuned for clinical narrative prompts.

    Acceptance criteria:
        1. Determinism: Finding order is preserved.
        2. No mutation: The extraction model is not mutated.
        3. Provenance: Finding IDs, source chunk IDs, and source file ID are
           retained.
        4. Boundedness: Finding count and free text use narrative caps.
    """
    findings = [
        _compact_narrative_finding(finding)
        for finding in extraction.molecular_findings[
            :_MAX_PROMPT_NARRATIVE_FINDINGS
        ]
    ]
    return {
        "artifact_id": extraction.artifact_id,
        "report_type": extraction.report_type,
        "disease": truncate_text(
            extraction.disease,
            _MAX_PROMPT_NARRATIVE_TEXT_CHARS,
        ),
        "specimen": truncate_text(
            extraction.specimen,
            _MAX_PROMPT_NARRATIVE_TEXT_CHARS,
        ),
        "tumor_percentage": truncate_text(
            extraction.tumor_percentage,
            _MAX_PROMPT_NARRATIVE_TEXT_CHARS,
        ),
        "molecular_findings": findings,
        "negative_findings": _compact_narrative_texts(
            extraction.negative_findings
        ),
        "assay_limitations": _compact_narrative_texts(
            extraction.assay_limitations
        ),
        "source_file_id": extraction.source_file_id,
        "needs_human_review": extraction.needs_human_review,
        "truncation": {
            "original_molecular_findings": len(extraction.molecular_findings),
            "kept_molecular_findings": len(findings),
            "finding_cap": _MAX_PROMPT_NARRATIVE_FINDINGS,
            "notice": _PROMPT_CONTEXT_CAP_NOTICE,
        },
    }


def _compact_narrative_finding(
    finding: MolecularFinding,
) -> dict[str, object]:
    return {
        "finding_id": finding.finding_id,
        "gene": finding.gene,
        "alteration": truncate_text(
            finding.alteration,
            _MAX_PROMPT_NARRATIVE_TEXT_CHARS,
        ),
        "alteration_type": finding.alteration_type,
        "source_page": finding.source_page,
        "source_text": truncate_text(
            finding.source_text,
            _MAX_PROMPT_NARRATIVE_TEXT_CHARS,
        ),
        "source_chunk_id": finding.source_chunk_id,
        "confidence": finding.confidence,
        "needs_human_review": finding.needs_human_review,
        "research_use_only": finding.research_use_only,
    }


def _compact_finding_for_prompt(finding: MolecularFinding) -> dict[str, object]:
    return {
        "finding_id": finding.finding_id,
        "gene": finding.gene,
        "alteration": finding.alteration,
        "alteration_type": finding.alteration_type,
        "source_page": finding.source_page,
        "source_text": truncate_text(
            finding.source_text,
            _MAX_PROMPT_SOURCE_TEXT_CHARS,
        ),
        "source_chunk_id": finding.source_chunk_id,
        "confidence": finding.confidence,
        "needs_human_review": finding.needs_human_review,
        "research_use_only": finding.research_use_only,
    }


def _compact_sankey_input_finding(
    finding: Mapping[str, object],
) -> dict[str, object]:
    """Return a tighter finding payload for mechanism Sankey prompts.

    Acceptance criteria:
        1. Determinism: Same finding mapping returns the same payload.
        2. No mutation: Do not mutate caller-owned mappings.
        3. Provenance: Preserve finding ID, source chunk ID, and source page.
        4. Boundedness: Source text uses the mechanism-Sankey text cap.

    Args:
        finding: General compact finding mapping.

    Returns:
        JSON-serializable finding mapping for the mechanism Sankey prompt.
    """
    return {
        **finding,
        "source_text": truncate_text(
            str(finding.get("source_text", "")),
            _MAX_PROMPT_SANKEY_INPUT_TEXT_CHARS,
        ),
    }


def _compact_sankey_input_texts(
    values: object,
    max_items: int = _MAX_PROMPT_SANKEY_INPUT_HYPOTHESES,
) -> list[str]:
    """Return text values capped for mechanism Sankey prompts.

    Acceptance criteria:
        1. Determinism: Same input sequence returns the same output list.
        2. No mutation: Caller-owned sequences are not mutated.
        3. Validation: Non-string values are stringified explicitly.
        4. Boundedness: Item count and character count use Sankey caps.

    Args:
        values: Candidate text values.
        max_items: Maximum number of values to keep.

    Returns:
        Non-empty text values capped to the mechanism-Sankey text budget.
    """
    if not isinstance(values, Sequence) or isinstance(values, str):
        return []
    return [
        item
        for item in (
            truncate_text(str(value), _MAX_PROMPT_SANKEY_INPUT_TEXT_CHARS)
            for value in values[:max_items]
        )
        if item
    ]


def _compact_sankey_input_tool(
    tool: Mapping[str, object],
) -> dict[str, object]:
    """Return a tighter ToolUniverse payload for mechanism Sankey prompts.

    Acceptance criteria:
        1. Determinism: Same tool mapping returns the same payload.
        2. No mutation: Do not mutate caller-owned mappings.
        3. Provenance: Preserve artifact ID, workflow, and input entity IDs.
        4. Boundedness: Evidence item count and free text use Sankey caps.

    Args:
        tool: General compact ToolUniverse payload.

    Returns:
        JSON-serializable tool payload for the mechanism Sankey prompt.
    """
    payload = dict(tool)
    payload.pop("truncation", None)
    evidence_items = _mapping_sequence(tool.get("evidence_items", []))
    return {
        **payload,
        "summary": truncate_text(
            str(tool.get("summary", "")),
            _MAX_PROMPT_SANKEY_INPUT_SUMMARY_CHARS,
        ),
        "evidence_items": [
            {
                str(key): truncate_text(
                    str(value),
                    _MAX_PROMPT_SANKEY_INPUT_TEXT_CHARS,
                )
                or ""
                for key, value in item.items()
            }
            for item in evidence_items[
                :_MAX_PROMPT_SANKEY_INPUT_TOOL_EVIDENCE_ITEMS
            ]
        ],
        "warnings": _compact_sankey_input_texts(tool.get("warnings", [])),
    }


def _compact_phenotype_input_finding(
    finding: Mapping[str, object],
) -> dict[str, object]:
    """Return a bounded finding payload for phenotype prompts.

    Acceptance criteria:
        1. Determinism: Same finding mapping returns the same payload.
        2. No mutation: Do not mutate caller-owned mappings.
        3. Provenance: Preserve finding ID, source chunk ID, and source page.
        4. Boundedness: Source text uses the phenotype prompt text cap.

    Args:
        finding: General compact finding mapping.

    Returns:
        JSON-serializable finding mapping for phenotype generation.
    """
    return {
        **finding,
        "source_text": truncate_text(
            str(finding.get("source_text", "")),
            _MAX_PROMPT_PHENOTYPE_TEXT_CHARS,
        ),
    }


def _compact_phenotype_input_graph(
    graph: object,
) -> dict[str, object]:
    """Return graph evidence capped for phenotype prompts.

    Acceptance criteria:
        1. Determinism: Preserves the incoming ranked graph order.
        2. No mutation: Do not mutate caller-owned mappings.
        3. Provenance: Preserve graph, node, edge, and subgraph IDs.
        4. Boundedness: Node, edge, subgraph, warning, and missing-entity
           payloads are capped for phenotype generation.
    """
    if not isinstance(graph, Mapping):
        return {}
    nodes = _mapping_sequence(graph.get("nodes", []))[
        :_MAX_PROMPT_PHENOTYPE_GRAPH_NODES
    ]
    edges = _mapping_sequence(graph.get("edges", []))[
        :_MAX_PROMPT_PHENOTYPE_GRAPH_EDGES
    ]
    truncation = dict(graph.get("truncation", {}))
    truncation.update(
        {
            "phenotype_kept_nodes": len(nodes),
            "phenotype_kept_edges": len(edges),
            "phenotype_node_cap": _MAX_PROMPT_PHENOTYPE_GRAPH_NODES,
            "phenotype_edge_cap": _MAX_PROMPT_PHENOTYPE_GRAPH_EDGES,
            "notice": _PROMPT_CONTEXT_CAP_NOTICE,
        }
    )
    return {
        "artifact_id": graph.get("artifact_id"),
        "source_entity_ids": _compact_id_list(
            _string_sequence(graph.get("source_entity_ids", []))
        ),
        "retrieval_modes": _compact_id_list(
            _string_sequence(graph.get("retrieval_modes", [])),
            max_items=_MAX_PROMPT_PHENOTYPE_TOOL_OUTPUTS,
        ),
        "nodes": [
            _compact_phenotype_input_graph_node(node) for node in nodes
        ],
        "edges": [
            _compact_phenotype_input_graph_edge(edge) for edge in edges
        ],
        "subgraphs": [
            _compact_phenotype_input_subgraph(subgraph)
            for subgraph in _mapping_sequence(graph.get("subgraphs", []))[
                :_MAX_PROMPT_PHENOTYPE_TOOL_OUTPUTS
            ]
        ],
        "missing_entities": _compact_phenotype_input_texts(
            graph.get("missing_entities", [])
        ),
        "warnings": _compact_phenotype_input_texts(graph.get("warnings", [])),
        "truncation": truncation,
    }


def _compact_phenotype_input_graph_node(
    node: Mapping[str, object],
) -> dict[str, object]:
    return {
        "node_id": str(node.get("node_id", "")),
        "label": truncate_text(
            str(node.get("label", "")),
            _MAX_PROMPT_PHENOTYPE_TEXT_CHARS,
        ),
        "kind": truncate_text(
            str(node.get("kind", "")),
            _MAX_PROMPT_PHENOTYPE_TEXT_CHARS,
        ),
        "source": truncate_text(
            str(node.get("source", "")),
            _MAX_PROMPT_PHENOTYPE_TEXT_CHARS,
        ),
    }


def _compact_phenotype_input_graph_edge(
    edge: Mapping[str, object],
) -> dict[str, object]:
    return {
        "edge_id": str(edge.get("edge_id", "")),
        "source_node_id": str(edge.get("source_node_id", "")),
        "target_node_id": str(edge.get("target_node_id", "")),
        "relation_type": truncate_text(
            str(edge.get("relation_type", "")),
            _MAX_PROMPT_PHENOTYPE_TEXT_CHARS,
        ),
        "source": truncate_text(
            str(edge.get("source", "")),
            _MAX_PROMPT_PHENOTYPE_TEXT_CHARS,
        ),
    }


def _compact_phenotype_input_subgraph(
    subgraph: Mapping[str, object],
) -> dict[str, object]:
    return {
        "retrieval_mode": str(subgraph.get("retrieval_mode", "")),
        "query_terms": _compact_phenotype_input_texts(
            subgraph.get("query_terms", [])
        ),
        "node_ids": _compact_id_list(
            _string_sequence(subgraph.get("node_ids", [])),
            max_items=_MAX_PROMPT_PHENOTYPE_GRAPH_NODES,
        ),
        "edge_ids": _compact_id_list(
            _string_sequence(subgraph.get("edge_ids", [])),
            max_items=_MAX_PROMPT_PHENOTYPE_GRAPH_EDGES,
        ),
        "warnings": _compact_phenotype_input_texts(
            subgraph.get("warnings", [])
        ),
    }


def _compact_phenotype_input_tool(
    tool: Mapping[str, object],
) -> dict[str, object]:
    """Return a tight ToolUniverse payload for phenotype prompts.

    Acceptance criteria:
        1. Determinism: Same tool mapping returns the same payload.
        2. No mutation: Do not mutate caller-owned mappings.
        3. Provenance: Preserve artifact ID, workflow, and input entity IDs.
        4. Boundedness: Summary text and evidence rows are tightly capped.
    """
    evidence_items = _mapping_sequence(tool.get("evidence_items", []))
    return {
        "artifact_id": tool.get("artifact_id"),
        "workflow": tool.get("workflow"),
        "input_entity_ids": _compact_id_list(
            _string_sequence(tool.get("input_entity_ids", [])),
        ),
        "summary": truncate_text(
            str(tool.get("summary", "")),
            _MAX_PROMPT_PHENOTYPE_SUMMARY_CHARS,
        ),
        "evidence_items": [
            _compact_phenotype_input_evidence_item(item)
            for item in evidence_items[
                :_MAX_PROMPT_PHENOTYPE_TOOL_EVIDENCE_ITEMS
            ]
        ],
        "warnings": _compact_phenotype_input_texts(
            tool.get("warnings", [])
        ),
        "requires_human_review": tool.get("requires_human_review", True),
        "truncation": {
            "original_evidence_items": len(evidence_items),
            "kept_evidence_items": min(
                len(evidence_items),
                _MAX_PROMPT_PHENOTYPE_TOOL_EVIDENCE_ITEMS,
            ),
            "notice": _PROMPT_CONTEXT_CAP_NOTICE,
        },
    }


def _compact_phenotype_input_evidence_item(
    item: Mapping[str, object],
) -> dict[str, str]:
    return {
        str(key): truncate_text(
            str(value),
            _MAX_PROMPT_PHENOTYPE_TEXT_CHARS,
        )
        or ""
        for key, value in list(item.items())[:_MAX_PROMPT_EVIDENCE_ITEM_FIELDS]
    }


def _compact_phenotype_input_medea(
    medea: object,
) -> dict[str, object]:
    """Return Medea reasoning capped for phenotype prompts.

    Acceptance criteria:
        1. Determinism: Hypothesis order is preserved.
        2. No mutation: Do not mutate caller-owned mappings.
        3. Provenance: Preserve artifact ID and reasoning mode.
        4. Boundedness: Summary and hypothesis lists use phenotype caps.
    """
    if not isinstance(medea, Mapping):
        return {}
    supported = _string_sequence(medea.get("supported_hypotheses", []))
    weakened = _string_sequence(medea.get("weakened_hypotheses", []))
    truncation = dict(medea.get("truncation", {}))
    truncation.update(
        {
            "phenotype_kept_supported_hypotheses": min(
                len(supported),
                _MAX_PROMPT_PHENOTYPE_HYPOTHESES,
            ),
            "phenotype_kept_weakened_hypotheses": min(
                len(weakened),
                _MAX_PROMPT_PHENOTYPE_HYPOTHESES,
            ),
            "notice": _PROMPT_CONTEXT_CAP_NOTICE,
        }
    )
    return {
        "artifact_id": medea.get("artifact_id"),
        "reasoning_mode": medea.get("reasoning_mode"),
        "decision_support_role": medea.get(
            "decision_support_role",
            "hypothesis_support_only",
        ),
        "downstream_uses": _compact_phenotype_input_texts(
            medea.get("downstream_uses", [])
        ),
        "summary": truncate_text(
            str(medea.get("summary", "")),
            _MAX_PROMPT_PHENOTYPE_SUMMARY_CHARS,
        ),
        "supported_hypotheses": _compact_phenotype_input_texts(
            supported,
            max_items=_MAX_PROMPT_PHENOTYPE_HYPOTHESES,
        ),
        "weakened_hypotheses": _compact_phenotype_input_texts(
            weakened,
            max_items=_MAX_PROMPT_PHENOTYPE_HYPOTHESES,
        ),
        "warnings": _compact_phenotype_input_texts(
            medea.get("warnings", [])
        ),
        "requires_human_review": medea.get("requires_human_review", True),
        "truncation": truncation,
    }


def _compact_phenotype_input_texts(
    values: object,
    max_items: int = _MAX_PROMPT_PHENOTYPE_HYPOTHESES,
) -> list[str]:
    """Return text values capped for molecular phenotype prompts.

    Acceptance criteria:
        1. Determinism: Same input sequence returns the same output list.
        2. No mutation: Caller-owned sequences are not mutated.
        3. Validation: Non-string values are stringified explicitly.
        4. Boundedness: Item count and character count use phenotype caps.
    """
    if not isinstance(values, Sequence) or isinstance(values, str):
        return []
    return [
        item
        for item in (
            truncate_text(str(value), _MAX_PROMPT_PHENOTYPE_TEXT_CHARS)
            for value in values[:max_items]
        )
        if item
    ]


def _compact_claim_input_finding(
    finding: Mapping[str, object],
) -> dict[str, object]:
    """Return a bounded finding payload for claim evidence prompts.

    Acceptance criteria:
        1. Determinism: Same finding mapping returns the same payload.
        2. No mutation: Do not mutate caller-owned mappings.
        3. Provenance: Preserve finding ID, source chunk ID, and source page.
        4. Boundedness: Source text uses the claim-evidence prompt text cap.
    """
    return {
        **finding,
        "source_text": truncate_text(
            str(finding.get("source_text", "")),
            _MAX_PROMPT_CLAIM_INPUT_TEXT_CHARS,
        ),
    }


def _compact_claim_input_graph(graph: object) -> dict[str, object]:
    """Return graph evidence capped for claim evidence prompts.

    Acceptance criteria:
        1. Determinism: Preserves the incoming ranked graph order.
        2. No mutation: Do not mutate caller-owned mappings.
        3. Provenance: Preserve graph, node, edge, and subgraph IDs.
        4. Boundedness: Node, edge, subgraph, warning, and missing-entity
           payloads are capped for claim generation.
    """
    if not isinstance(graph, Mapping):
        return {}
    nodes = _mapping_sequence(graph.get("nodes", []))[
        :_MAX_PROMPT_CLAIM_INPUT_GRAPH_NODES
    ]
    edges = _mapping_sequence(graph.get("edges", []))[
        :_MAX_PROMPT_CLAIM_INPUT_GRAPH_EDGES
    ]
    truncation = dict(graph.get("truncation", {}))
    truncation.update(
        {
            "claim_evidence_kept_nodes": len(nodes),
            "claim_evidence_kept_edges": len(edges),
            "claim_evidence_node_cap": _MAX_PROMPT_CLAIM_INPUT_GRAPH_NODES,
            "claim_evidence_edge_cap": _MAX_PROMPT_CLAIM_INPUT_GRAPH_EDGES,
            "notice": _PROMPT_CONTEXT_CAP_NOTICE,
        }
    )
    return {
        "artifact_id": graph.get("artifact_id"),
        "source_entity_ids": _compact_id_list(
            _string_sequence(graph.get("source_entity_ids", []))
        ),
        "retrieval_modes": _compact_id_list(
            _string_sequence(graph.get("retrieval_modes", [])),
            max_items=_MAX_PROMPT_CLAIM_INPUT_TOOL_OUTPUTS,
        ),
        "nodes": [_compact_claim_input_graph_node(node) for node in nodes],
        "edges": [_compact_claim_input_graph_edge(edge) for edge in edges],
        "subgraphs": [
            _compact_claim_input_subgraph(subgraph)
            for subgraph in _mapping_sequence(graph.get("subgraphs", []))[
                :_MAX_PROMPT_CLAIM_INPUT_TOOL_OUTPUTS
            ]
        ],
        "missing_entities": _compact_claim_input_texts(
            graph.get("missing_entities", [])
        ),
        "warnings": _compact_claim_input_texts(graph.get("warnings", [])),
        "truncation": truncation,
    }


def _compact_claim_input_graph_node(
    node: Mapping[str, object],
) -> dict[str, object]:
    return {
        "node_id": str(node.get("node_id", "")),
        "label": truncate_text(
            str(node.get("label", "")),
            _MAX_PROMPT_CLAIM_INPUT_TEXT_CHARS,
        ),
        "kind": truncate_text(
            str(node.get("kind", "")),
            _MAX_PROMPT_CLAIM_INPUT_TEXT_CHARS,
        ),
        "source": truncate_text(
            str(node.get("source", "")),
            _MAX_PROMPT_CLAIM_INPUT_TEXT_CHARS,
        ),
    }


def _compact_claim_input_graph_edge(
    edge: Mapping[str, object],
) -> dict[str, object]:
    return {
        "edge_id": str(edge.get("edge_id", "")),
        "source_node_id": str(edge.get("source_node_id", "")),
        "target_node_id": str(edge.get("target_node_id", "")),
        "relation_type": truncate_text(
            str(edge.get("relation_type", "")),
            _MAX_PROMPT_CLAIM_INPUT_TEXT_CHARS,
        ),
        "source": truncate_text(
            str(edge.get("source", "")),
            _MAX_PROMPT_CLAIM_INPUT_TEXT_CHARS,
        ),
    }


def _compact_claim_input_subgraph(
    subgraph: Mapping[str, object],
) -> dict[str, object]:
    return {
        "retrieval_mode": str(subgraph.get("retrieval_mode", "")),
        "query_terms": _compact_claim_input_texts(
            subgraph.get("query_terms", [])
        ),
        "node_ids": _compact_id_list(
            _string_sequence(subgraph.get("node_ids", [])),
            max_items=_MAX_PROMPT_CLAIM_INPUT_GRAPH_NODES,
        ),
        "edge_ids": _compact_id_list(
            _string_sequence(subgraph.get("edge_ids", [])),
            max_items=_MAX_PROMPT_CLAIM_INPUT_GRAPH_EDGES,
        ),
        "warnings": _compact_claim_input_texts(subgraph.get("warnings", [])),
    }


def _compact_claim_input_tool(
    tool: Mapping[str, object],
) -> dict[str, object]:
    """Return a tight ToolUniverse payload for claim evidence prompts.

    Acceptance criteria:
        1. Determinism: Same tool mapping returns the same payload.
        2. No mutation: Do not mutate caller-owned mappings.
        3. Provenance: Preserve artifact ID, workflow, and input entity IDs.
        4. Boundedness: Summary text and evidence rows are tightly capped.
    """
    evidence_items = _mapping_sequence(tool.get("evidence_items", []))
    return {
        "artifact_id": tool.get("artifact_id"),
        "workflow": tool.get("workflow"),
        "input_entity_ids": _compact_id_list(
            _string_sequence(tool.get("input_entity_ids", [])),
        ),
        "summary": truncate_text(
            str(tool.get("summary", "")),
            _MAX_PROMPT_CLAIM_INPUT_SUMMARY_CHARS,
        ),
        "evidence_items": [
            _compact_claim_input_evidence_item(item)
            for item in evidence_items[
                :_MAX_PROMPT_CLAIM_INPUT_TOOL_EVIDENCE_ITEMS
            ]
        ],
        "warnings": _compact_claim_input_texts(tool.get("warnings", [])),
        "requires_human_review": tool.get("requires_human_review", True),
        "truncation": {
            "original_evidence_items": len(evidence_items),
            "kept_evidence_items": min(
                len(evidence_items),
                _MAX_PROMPT_CLAIM_INPUT_TOOL_EVIDENCE_ITEMS,
            ),
            "notice": _PROMPT_CONTEXT_CAP_NOTICE,
        },
    }


def _compact_claim_input_evidence_item(
    item: Mapping[str, object],
) -> dict[str, str]:
    return {
        str(key): truncate_text(
            str(value),
            _MAX_PROMPT_CLAIM_INPUT_TEXT_CHARS,
        )
        or ""
        for key, value in list(item.items())[:_MAX_PROMPT_EVIDENCE_ITEM_FIELDS]
    }


def _compact_claim_input_medea(medea: object) -> dict[str, object]:
    """Return Medea reasoning capped for claim evidence prompts.

    Acceptance criteria:
        1. Determinism: Hypothesis order is preserved.
        2. No mutation: Do not mutate caller-owned mappings.
        3. Provenance: Preserve artifact ID and reasoning mode.
        4. Boundedness: Summary and hypothesis lists use claim-evidence caps.
    """
    if not isinstance(medea, Mapping):
        return {}
    supported = _string_sequence(medea.get("supported_hypotheses", []))
    weakened = _string_sequence(medea.get("weakened_hypotheses", []))
    truncation = dict(medea.get("truncation", {}))
    truncation.update(
        {
            "claim_evidence_kept_supported_hypotheses": min(
                len(supported),
                _MAX_PROMPT_CLAIM_INPUT_HYPOTHESES,
            ),
            "claim_evidence_kept_weakened_hypotheses": min(
                len(weakened),
                _MAX_PROMPT_CLAIM_INPUT_HYPOTHESES,
            ),
            "notice": _PROMPT_CONTEXT_CAP_NOTICE,
        }
    )
    return {
        "artifact_id": medea.get("artifact_id"),
        "reasoning_mode": medea.get("reasoning_mode"),
        "decision_support_role": medea.get(
            "decision_support_role",
            "hypothesis_support_only",
        ),
        "downstream_uses": _compact_claim_input_texts(
            medea.get("downstream_uses", [])
        ),
        "summary": truncate_text(
            str(medea.get("summary", "")),
            _MAX_PROMPT_CLAIM_INPUT_SUMMARY_CHARS,
        ),
        "supported_hypotheses": _compact_claim_input_texts(
            supported,
            max_items=_MAX_PROMPT_CLAIM_INPUT_HYPOTHESES,
        ),
        "weakened_hypotheses": _compact_claim_input_texts(
            weakened,
            max_items=_MAX_PROMPT_CLAIM_INPUT_HYPOTHESES,
        ),
        "warnings": _compact_claim_input_texts(medea.get("warnings", [])),
        "requires_human_review": medea.get("requires_human_review", True),
        "truncation": truncation,
    }


def _compact_claim_input_texts(
    values: object,
    max_items: int = _MAX_PROMPT_CLAIM_INPUT_HYPOTHESES,
) -> list[str]:
    """Return text values capped for claim evidence prompts.

    Acceptance criteria:
        1. Determinism: Same input sequence returns the same output list.
        2. No mutation: Caller-owned sequences are not mutated.
        3. Validation: Non-string values are stringified explicitly.
        4. Boundedness: Item count and character count use claim caps.
    """
    if not isinstance(values, Sequence) or isinstance(values, str):
        return []
    return [
        item
        for item in (
            truncate_text(str(value), _MAX_PROMPT_CLAIM_INPUT_TEXT_CHARS)
            for value in values[:max_items]
        )
        if item
    ]


def _compact_tumor_input_finding(
    finding: Mapping[str, object],
) -> dict[str, object]:
    """Return a bounded finding payload for tumor behavior prompts.

    Acceptance criteria:
        1. Determinism: Same finding mapping returns the same payload.
        2. No mutation: Do not mutate caller-owned mappings.
        3. Provenance: Preserve finding ID, source chunk ID, and source page.
        4. Boundedness: Source text uses the tumor-behavior prompt text cap.
    """
    return {
        **finding,
        "source_text": truncate_text(
            str(finding.get("source_text", "")),
            _MAX_PROMPT_TUMOR_INPUT_TEXT_CHARS,
        ),
    }


def _compact_tumor_input_graph(graph: object) -> dict[str, object]:
    """Return graph evidence capped for tumor behavior prompts.

    Acceptance criteria:
        1. Determinism: Preserves the incoming ranked graph order.
        2. No mutation: Do not mutate caller-owned mappings.
        3. Provenance: Preserve graph, node, edge, and subgraph IDs.
        4. Boundedness: Node, edge, subgraph, warning, and missing-entity
           payloads are capped for tumor behavior generation.
    """
    if not isinstance(graph, Mapping):
        return {}
    nodes = _mapping_sequence(graph.get("nodes", []))[
        :_MAX_PROMPT_TUMOR_INPUT_GRAPH_NODES
    ]
    edges = _mapping_sequence(graph.get("edges", []))[
        :_MAX_PROMPT_TUMOR_INPUT_GRAPH_EDGES
    ]
    truncation = dict(graph.get("truncation", {}))
    truncation.update(
        {
            "tumor_behavior_kept_nodes": len(nodes),
            "tumor_behavior_kept_edges": len(edges),
            "tumor_behavior_node_cap": _MAX_PROMPT_TUMOR_INPUT_GRAPH_NODES,
            "tumor_behavior_edge_cap": _MAX_PROMPT_TUMOR_INPUT_GRAPH_EDGES,
            "notice": _PROMPT_CONTEXT_CAP_NOTICE,
        }
    )
    return {
        "artifact_id": graph.get("artifact_id"),
        "source_entity_ids": _compact_id_list(
            _string_sequence(graph.get("source_entity_ids", []))
        ),
        "retrieval_modes": _compact_id_list(
            _string_sequence(graph.get("retrieval_modes", [])),
            max_items=_MAX_PROMPT_TUMOR_INPUT_TOOL_OUTPUTS,
        ),
        "nodes": [_compact_tumor_input_graph_node(node) for node in nodes],
        "edges": [_compact_tumor_input_graph_edge(edge) for edge in edges],
        "subgraphs": [
            _compact_tumor_input_subgraph(subgraph)
            for subgraph in _mapping_sequence(graph.get("subgraphs", []))[
                :_MAX_PROMPT_TUMOR_INPUT_TOOL_OUTPUTS
            ]
        ],
        "missing_entities": _compact_tumor_input_texts(
            graph.get("missing_entities", [])
        ),
        "warnings": _compact_tumor_input_texts(graph.get("warnings", [])),
        "truncation": truncation,
    }


def _compact_tumor_input_graph_node(
    node: Mapping[str, object],
) -> dict[str, object]:
    return {
        "node_id": str(node.get("node_id", "")),
        "label": truncate_text(
            str(node.get("label", "")),
            _MAX_PROMPT_TUMOR_INPUT_TEXT_CHARS,
        ),
        "kind": truncate_text(
            str(node.get("kind", "")),
            _MAX_PROMPT_TUMOR_INPUT_TEXT_CHARS,
        ),
        "source": truncate_text(
            str(node.get("source", "")),
            _MAX_PROMPT_TUMOR_INPUT_TEXT_CHARS,
        ),
    }


def _compact_tumor_input_graph_edge(
    edge: Mapping[str, object],
) -> dict[str, object]:
    return {
        "edge_id": str(edge.get("edge_id", "")),
        "source_node_id": str(edge.get("source_node_id", "")),
        "target_node_id": str(edge.get("target_node_id", "")),
        "relation_type": truncate_text(
            str(edge.get("relation_type", "")),
            _MAX_PROMPT_TUMOR_INPUT_TEXT_CHARS,
        ),
        "source": truncate_text(
            str(edge.get("source", "")),
            _MAX_PROMPT_TUMOR_INPUT_TEXT_CHARS,
        ),
    }


def _compact_tumor_input_subgraph(
    subgraph: Mapping[str, object],
) -> dict[str, object]:
    return {
        "retrieval_mode": str(subgraph.get("retrieval_mode", "")),
        "query_terms": _compact_tumor_input_texts(
            subgraph.get("query_terms", [])
        ),
        "node_ids": _compact_id_list(
            _string_sequence(subgraph.get("node_ids", [])),
            max_items=_MAX_PROMPT_TUMOR_INPUT_GRAPH_NODES,
        ),
        "edge_ids": _compact_id_list(
            _string_sequence(subgraph.get("edge_ids", [])),
            max_items=_MAX_PROMPT_TUMOR_INPUT_GRAPH_EDGES,
        ),
        "warnings": _compact_tumor_input_texts(subgraph.get("warnings", [])),
    }


def _compact_tumor_input_tool(
    tool: Mapping[str, object],
) -> dict[str, object]:
    """Return a tight ToolUniverse payload for tumor behavior prompts.

    Acceptance criteria:
        1. Determinism: Same tool mapping returns the same payload.
        2. No mutation: Do not mutate caller-owned mappings.
        3. Provenance: Preserve artifact ID, workflow, and input entity IDs.
        4. Boundedness: Summary text and evidence rows are tightly capped.
    """
    evidence_items = _mapping_sequence(tool.get("evidence_items", []))
    return {
        "artifact_id": tool.get("artifact_id"),
        "workflow": tool.get("workflow"),
        "input_entity_ids": _compact_id_list(
            _string_sequence(tool.get("input_entity_ids", [])),
        ),
        "summary": truncate_text(
            str(tool.get("summary", "")),
            _MAX_PROMPT_TUMOR_INPUT_SUMMARY_CHARS,
        ),
        "evidence_items": [
            _compact_tumor_input_evidence_item(item)
            for item in evidence_items[
                :_MAX_PROMPT_TUMOR_INPUT_TOOL_EVIDENCE_ITEMS
            ]
        ],
        "warnings": _compact_tumor_input_texts(tool.get("warnings", [])),
        "requires_human_review": tool.get("requires_human_review", True),
        "truncation": {
            "original_evidence_items": len(evidence_items),
            "kept_evidence_items": min(
                len(evidence_items),
                _MAX_PROMPT_TUMOR_INPUT_TOOL_EVIDENCE_ITEMS,
            ),
            "notice": _PROMPT_CONTEXT_CAP_NOTICE,
        },
    }


def _compact_tumor_input_evidence_item(
    item: Mapping[str, object],
) -> dict[str, str]:
    return {
        str(key): truncate_text(
            str(value),
            _MAX_PROMPT_TUMOR_INPUT_TEXT_CHARS,
        )
        or ""
        for key, value in list(item.items())[:_MAX_PROMPT_EVIDENCE_ITEM_FIELDS]
    }


def _compact_tumor_input_medea(medea: object) -> dict[str, object]:
    """Return Medea reasoning capped for tumor behavior prompts.

    Acceptance criteria:
        1. Determinism: Hypothesis order is preserved.
        2. No mutation: Do not mutate caller-owned mappings.
        3. Provenance: Preserve artifact ID and reasoning mode.
        4. Boundedness: Summary and hypothesis lists use tumor-behavior caps.
    """
    if not isinstance(medea, Mapping):
        return {}
    supported = _string_sequence(medea.get("supported_hypotheses", []))
    weakened = _string_sequence(medea.get("weakened_hypotheses", []))
    truncation = dict(medea.get("truncation", {}))
    truncation.update(
        {
            "tumor_behavior_kept_supported_hypotheses": min(
                len(supported),
                _MAX_PROMPT_TUMOR_INPUT_HYPOTHESES,
            ),
            "tumor_behavior_kept_weakened_hypotheses": min(
                len(weakened),
                _MAX_PROMPT_TUMOR_INPUT_HYPOTHESES,
            ),
            "notice": _PROMPT_CONTEXT_CAP_NOTICE,
        }
    )
    return {
        "artifact_id": medea.get("artifact_id"),
        "reasoning_mode": medea.get("reasoning_mode"),
        "decision_support_role": medea.get(
            "decision_support_role",
            "hypothesis_support_only",
        ),
        "downstream_uses": _compact_tumor_input_texts(
            medea.get("downstream_uses", [])
        ),
        "summary": truncate_text(
            str(medea.get("summary", "")),
            _MAX_PROMPT_TUMOR_INPUT_SUMMARY_CHARS,
        ),
        "supported_hypotheses": _compact_tumor_input_texts(
            supported,
            max_items=_MAX_PROMPT_TUMOR_INPUT_HYPOTHESES,
        ),
        "weakened_hypotheses": _compact_tumor_input_texts(
            weakened,
            max_items=_MAX_PROMPT_TUMOR_INPUT_HYPOTHESES,
        ),
        "warnings": _compact_tumor_input_texts(medea.get("warnings", [])),
        "requires_human_review": medea.get("requires_human_review", True),
        "truncation": truncation,
    }


def _compact_tumor_input_texts(
    values: object,
    max_items: int = _MAX_PROMPT_TUMOR_INPUT_HYPOTHESES,
) -> list[str]:
    """Return text values capped for tumor behavior prompts.

    Acceptance criteria:
        1. Determinism: Same input sequence returns the same output list.
        2. No mutation: Caller-owned sequences are not mutated.
        3. Validation: Non-string values are stringified explicitly.
        4. Boundedness: Item count and character count use tumor caps.
    """
    if not isinstance(values, Sequence) or isinstance(values, str):
        return []
    return [
        item
        for item in (
            truncate_text(str(value), _MAX_PROMPT_TUMOR_INPUT_TEXT_CHARS)
            for value in values[:max_items]
        )
        if item
    ]


def _compact_narrative_mapping(
    value: Mapping[str, object],
) -> dict[str, object]:
    """Return a recursively bounded mapping for narrative prompts.

    Acceptance criteria:
        1. Determinism: Mapping insertion order is preserved.
        2. No mutation: Caller-owned mappings and nested values are not mutated.
        3. Provenance: IDs are retained while text values are capped.
        4. Boundedness: Nested lists and dictionaries use narrative caps.
    """
    return {
        str(key): _compact_narrative_value(item)
        for key, item in value.items()
    }


def _compact_narrative_value(value: object) -> object:
    if isinstance(value, Mapping):
        return _compact_narrative_mapping(value)
    if isinstance(value, Sequence) and not isinstance(value, str):
        if all(isinstance(item, Mapping) for item in value):
            return [
                _compact_narrative_mapping(item)
                for item in _mapping_sequence(value)[
                    :_MAX_PROMPT_NARRATIVE_DECISION_ROWS
                ]
            ]
        if all(isinstance(item, str) for item in value):
            return _compact_narrative_texts(value)
        return [
            _compact_narrative_value(item)
            for item in list(value)[:_MAX_PROMPT_NARRATIVE_DECISION_ROWS]
        ]
    if isinstance(value, str):
        return truncate_text(value, _MAX_PROMPT_NARRATIVE_TEXT_CHARS)
    return value


def _compact_narrative_texts(
    values: object,
    max_items: int = _MAX_PROMPT_NARRATIVE_DECISION_ROWS,
) -> list[str]:
    """Return text values capped for clinical narrative prompts.

    Acceptance criteria:
        1. Determinism: Same input sequence returns the same output list.
        2. No mutation: Caller-owned sequences are not mutated.
        3. Validation: Non-string values are stringified explicitly.
        4. Boundedness: Item count and character count use narrative caps.
    """
    if not isinstance(values, Sequence) or isinstance(values, str):
        return []
    return [
        item
        for item in (
            truncate_text(str(value), _MAX_PROMPT_NARRATIVE_TEXT_CHARS)
            for value in values[:max_items]
        )
        if item
    ]


def _compact_text_list(
    values: Sequence[str],
    *,
    max_items: int = _MAX_PROMPT_HYPOTHESES,
) -> list[str]:
    return [
        item
        for item in (
            truncate_text(value, _MAX_PROMPT_GENERATED_TEXT_CHARS)
            for value in values[:max_items]
        )
        if item is not None
    ]


def _compact_id_list(
    values: Sequence[str],
    *,
    max_items: int = _MAX_PROMPT_SUPPORT_IDS,
) -> list[str]:
    return [value for value in values[:max_items] if value.strip()]


def _compact_graph_node_for_prompt(node: Mapping[str, Any]) -> dict[str, object]:
    """Return a bounded graph node payload for prompts.

    Acceptance criteria:
        1. Determinism: Same node mapping returns the same payload.
        2. No mutation: Do not mutate caller-owned node mappings.
        3. Provenance: Preserve the node ID and source fields.
        4. Boundedness: Free-text fields are capped.

    Args:
        node: Graph node mapping.

    Returns:
        JSON-serializable compact graph node.
    """
    return {
        "node_id": str(node.get("node_id", "")),
        "label": truncate_text(
            str(node.get("label", "")),
            _MAX_PROMPT_MISC_TEXT_CHARS,
        ),
        "kind": truncate_text(
            str(node.get("kind", "")),
            _MAX_PROMPT_MISC_TEXT_CHARS,
        ),
        "source": truncate_text(
            str(node.get("source", "")),
            _MAX_PROMPT_MISC_TEXT_CHARS,
        ),
    }


def _compact_graph_subgraphs_for_prompt(
    subgraphs: Sequence[Mapping[str, Any]],
    *,
    kept_node_ids: set[str],
    kept_edge_ids: set[str],
) -> list[dict[str, object]]:
    """Return targeted graph slices that survived relevance compaction.

    Acceptance criteria:
        1. Keeps retrieval mode and query terms available to staged prompts.
        2. Prefers node and edge IDs retained in the compact graph payload.
        3. Preserves warnings when a targeted subgraph is present but fully
           compacted away by node/edge caps.
        4. Does not mutate caller-owned graph mappings.
    """
    compact_subgraphs = []
    for subgraph in subgraphs[:_MAX_PROMPT_TOOL_OUTPUTS]:
        raw_node_ids = _string_sequence(subgraph.get("node_ids", []))
        raw_edge_ids = _string_sequence(subgraph.get("edge_ids", []))
        node_ids = [node_id for node_id in raw_node_ids if node_id in kept_node_ids]
        edge_ids = [edge_id for edge_id in raw_edge_ids if edge_id in kept_edge_ids]
        warnings = _compact_text_list(
            _string_sequence(subgraph.get("warnings", [])),
            max_items=_MAX_PROMPT_TOOL_EVIDENCE_ITEMS,
        )
        if raw_node_ids and not node_ids:
            warnings.append("subgraph_node_ids_compacted_from_prompt_payload")
        if raw_edge_ids and not edge_ids:
            warnings.append("subgraph_edge_ids_compacted_from_prompt_payload")
        compact_subgraphs.append(
            {
                "retrieval_mode": str(subgraph.get("retrieval_mode", "")),
                "query_terms": _compact_text_list(
                    _string_sequence(subgraph.get("query_terms", [])),
                    max_items=_MAX_PROMPT_TOOL_EVIDENCE_ITEMS,
                ),
                "node_ids": _compact_id_list(node_ids),
                "edge_ids": _compact_id_list(edge_ids),
                "warnings": warnings,
            }
        )
    return compact_subgraphs


def _compact_graph_edge_for_prompt(edge: Mapping[str, Any]) -> dict[str, object]:
    """Return a bounded graph edge payload for prompts.

    Acceptance criteria:
        1. Determinism: Same edge mapping returns the same payload.
        2. No mutation: Do not mutate caller-owned edge mappings.
        3. Provenance: Preserve edge ID, endpoints, and source.
        4. Boundedness: Free-text fields are capped.

    Args:
        edge: Graph edge mapping.

    Returns:
        JSON-serializable compact graph edge.
    """
    return {
        "edge_id": str(edge.get("edge_id", "")),
        "source_node_id": _edge_source_id(edge),
        "target_node_id": _edge_target_id(edge),
        "relation_type": truncate_text(
            str(edge.get("relation_type", "")),
            _MAX_PROMPT_MISC_TEXT_CHARS,
        ),
        "source": truncate_text(
            str(edge.get("source", "")),
            _MAX_PROMPT_MISC_TEXT_CHARS,
        ),
    }


def _compact_evidence_item_for_prompt(
    item: Mapping[str, Any],
) -> dict[str, str]:
    """Return a bounded ToolUniverse evidence row for prompts.

    Acceptance criteria:
        1. Determinism: Preserve insertion order for kept fields.
        2. No mutation: Do not mutate caller-owned evidence mappings.
        3. Boundedness: Field count and value text are capped.
        4. Compatibility: Non-string values are converted to strings.

    Args:
        item: Tool evidence item mapping.

    Returns:
        JSON-serializable compact evidence item.
    """
    return {
        str(key): truncate_text(str(value), _MAX_PROMPT_MISC_TEXT_CHARS) or ""
        for key, value in list(item.items())[:_MAX_PROMPT_EVIDENCE_ITEM_FIELDS]
    }


def _string_sequence(value: object) -> list[str]:
    """Return a list of stringified values for prompt compaction.

    Acceptance criteria:
        1. Determinism: Same value returns the same list.
        2. No mutation: Do not mutate caller-owned collections.
        3. Compatibility: Scalar values become one-item lists.
        4. Filtering: Empty string values are omitted.

    Args:
        value: Unknown JSON-like value.

    Returns:
        List of non-empty string values.
    """
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, Sequence):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)] if str(value).strip() else []


def _mapping_sequence(value: object) -> list[Mapping[str, Any]]:
    """Return mapping items from an unknown JSON-like collection.

    Acceptance criteria:
        1. Determinism: Preserve source order for mapping items.
        2. No mutation: Do not mutate caller-owned collections.
        3. Filtering: Omit non-mapping values.
        4. Compatibility: Non-sequence inputs return an empty list.

    Args:
        value: Unknown JSON-like value.

    Returns:
        Ordered list of mapping values.
    """
    if not isinstance(value, Sequence) or isinstance(value, str):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _unique_nonempty_strings(values: Sequence[str | None]) -> list[str]:
    seen: set[str] = set()
    unique_values: list[str] = []
    for value in values:
        text = (value or "").strip()
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            unique_values.append(text)
    return unique_values


def _matched_graph_node_ids(
    nodes: Sequence[Mapping[str, Any]],
    entity_labels: Sequence[str],
) -> set[str]:
    return {
        str(node.get("node_id", "")).strip()
        for node in nodes
        if _graph_label_match_rank(str(node.get("label", "")), entity_labels) < 2
        and str(node.get("node_id", "")).strip()
    }


def _connected_graph_node_ids(
    edges: Sequence[Mapping[str, Any]],
    matched_node_ids: set[str],
) -> set[str]:
    connected: set[str] = set()
    for edge in edges:
        source_id = _edge_source_id(edge)
        target_id = _edge_target_id(edge)
        if source_id in matched_node_ids and target_id:
            connected.add(target_id)
        if target_id in matched_node_ids and source_id:
            connected.add(source_id)
    return connected


def _graph_node_sort_key(
    node: Mapping[str, Any],
    *,
    entity_labels: Sequence[str],
    matched_node_ids: set[str],
    connected_node_ids: set[str],
) -> tuple[int, str, str, str]:
    node_id = str(node.get("node_id", "")).strip()
    match_rank = _graph_label_match_rank(str(node.get("label", "")), entity_labels)
    if node_id in matched_node_ids:
        rank = match_rank
    elif node_id in connected_node_ids:
        rank = 2
    else:
        rank = 3
    return (
        rank,
        str(node.get("kind", "")).casefold(),
        str(node.get("label", "")).casefold(),
        node_id.casefold(),
    )


def _graph_label_match_rank(label: str, entity_labels: Sequence[str]) -> int:
    normalized_label = label.strip().casefold()
    if not normalized_label:
        return 3
    normalized_entities = [
        value.strip().casefold()
        for value in entity_labels
        if value.strip()
    ]
    if normalized_label in normalized_entities:
        return 0
    for entity in normalized_entities:
        if entity in normalized_label or normalized_label in entity:
            return 1
    return 3


def _graph_edge_sort_key(
    edge: Mapping[str, Any],
    kept_node_ids: set[str],
) -> tuple[int, str, str, str, str]:
    source_id = _edge_source_id(edge)
    target_id = _edge_target_id(edge)
    endpoint_matches = int(source_id in kept_node_ids) + int(
        target_id in kept_node_ids
    )
    rank = 0 if endpoint_matches == 2 else 1
    return (
        rank,
        str(edge.get("relation_type", "")).casefold(),
        source_id.casefold(),
        target_id.casefold(),
        str(edge.get("edge_id", "")).casefold(),
    )


def _edge_source_id(edge: Mapping[str, Any]) -> str:
    return str(edge.get("source_node_id", "")).strip()


def _edge_target_id(edge: Mapping[str, Any]) -> str:
    return str(edge.get("target_node_id", "")).strip()


async def _generate_artifact(
    *,
    prompt_name: str,
    schema_model: type[T],
    planned_artifact_id: str,
    payload: Mapping[str, Any],
    source_artifact_ids: Sequence[str],
    source_chunk_ids: Sequence[str] = (),
    source_file_id: str | None = None,
    model_provider: object,
    model_name: str,
    prompts_root: Path,
    created_at: datetime,
    artifact_validator: Callable[[T], T] | None = None,
    max_tokens: int | None = None,
    input_token_budget: int | None = None,
) -> StructuredArtifactResult[T]:
    """Generate a schema-valid artifact with one repair retry.

    Acceptance criteria:
        1. Determinism: Prompt construction is stable for identical inputs.
        2. Repair: Malformed JSON wrappers, strings, or missing artifact IDs are
           repaired deterministically when safe.
        3. Retry: One malformed structured-output attempt is retried with a
           repair prompt that names the validation failure.
        4. Safety: Unsupported certainty language remains rejected after repair.
        5. Provenance: Prompt and schema hashes reflect the successful attempt.
        6. Domain validation: An optional pure artifact validator participates
           in the same bounded repair loop.

    Args:
        prompt_name: Prompt template stem without `_system` or `_user` suffix.
        schema_model: Pydantic model expected from the provider.
        planned_artifact_id: Deterministic artifact ID required in output.
        payload: Prompt payload for the model.
        source_artifact_ids: Artifact IDs used as source evidence.
        source_chunk_ids: Source chunk IDs used as evidence.
        source_file_id: Optional source file ID for provenance.
        model_provider: Structured-output model provider boundary.
        model_name: Local model name used for provenance and provider request.
        prompts_root: Directory containing prompt templates.
        created_at: Provenance timestamp.
        artifact_validator: Optional post-schema domain validator/normalizer.

    Returns:
        Schema-validated artifact and provenance.
    """
    prompts = _load_prompt_pair(prompts_root, prompt_name)
    payload_json = json.dumps(payload, sort_keys=True, indent=2)
    user_prompt = prompts.user.format(
        planned_artifact_id=planned_artifact_id,
        payload_json=payload_json,
    )
    if input_token_budget is not None:
        await _require_prompt_within_token_budget(
            model_provider=model_provider,
            model_name=model_name,
            system_prompt=prompts.system,
            user_prompt=user_prompt,
            input_token_budget=input_token_budget,
            schema_name=schema_model.__name__,
        )
    schema = schema_model.model_json_schema()
    attempt_result = await _generate_valid_artifact_attempt(
        prompt_name=prompt_name,
        schema_model=schema_model,
        schema=schema,
        planned_artifact_id=planned_artifact_id,
        system_prompt=prompts.system,
        user_prompt=user_prompt,
        payload_json=payload_json,
        model_provider=model_provider,
        model_name=model_name,
        artifact_validator=artifact_validator,
        max_tokens=max_tokens,
    )
    provenance = build_artifact_provenance(
        artifact_type=schema_model.__name__,
        schema_name=schema_model.__name__,
        model_name=model_name,
        prompt_text=f"{prompts.system}\n\n{attempt_result.user_prompt}",
        schema_json=schema,
        source_artifact_ids=list(source_artifact_ids),
        source_chunk_ids=list(source_chunk_ids),
        created_at=created_at,
        source_file_id=source_file_id,
        generation_status=_generation_status_for_attempts(attempt_result.attempts),
        artifact_id=planned_artifact_id,
    )
    return StructuredArtifactResult(artifact=attempt_result.artifact, provenance=provenance)


async def _require_prompt_within_token_budget(
    *,
    model_provider: object,
    model_name: str,
    system_prompt: str,
    user_prompt: str,
    input_token_budget: int,
    schema_name: str,
) -> None:
    """Fail before generation when a rendered prompt exceeds its input budget."""
    if input_token_budget <= 0:
        raise ValueError("input_token_budget must be positive")
    prompt_text = f"{system_prompt}\n\n{user_prompt}"
    counter = getattr(model_provider, "count_tokens", None)
    prompt_tokens = (
        await counter(model_name=model_name, text=prompt_text)
        if callable(counter)
        else max(1, (len(prompt_text) + 3) // 4)
    )
    if prompt_tokens > input_token_budget:
        raise StructuredArtifactGenerationError(
            f"{schema_name} rendered prompt exceeds input token budget: "
            f"{prompt_tokens} > {input_token_budget}"
        )


async def _generate_valid_artifact_attempt(
    *,
    prompt_name: str,
    schema_model: type[T],
    schema: dict[str, object],
    planned_artifact_id: str,
    system_prompt: str,
    user_prompt: str,
    payload_json: str,
    model_provider: object,
    model_name: str,
    artifact_validator: Callable[[T], T] | None = None,
    max_tokens: int | None = None,
) -> _StructuredArtifactAttemptResult[T]:
    """Return a valid artifact, retrying once for malformed output.

    Acceptance criteria:
        1. Attempts are bounded by `_STRUCTURED_OUTPUT_MAX_ATTEMPTS`.
        2. Timeout-style provider failures are not retried here.
        3. Validation failures are retried with a repair-specific user prompt.
        4. The returned artifact ID equals the planned artifact ID.
        5. The function does not mutate prompts, schema, or raw outputs.

    Args:
        prompt_name: Prompt identifier for diagnostics.
        schema_model: Pydantic schema expected from the model provider.
        schema: JSON schema sent to the model provider.
        planned_artifact_id: Artifact ID required in the response.
        system_prompt: System prompt text.
        user_prompt: Original user prompt text.
        payload_json: Original serialized prompt payload.
        model_provider: Structured-output provider boundary.
        model_name: Local model identifier.
        artifact_validator: Optional post-schema domain validator/normalizer.

    Returns:
        Valid artifact plus successful user prompt and attempt count.

    Raises:
        StructuredArtifactGenerationError: If all attempts fail.
    """
    current_user_prompt = user_prompt
    last_error: BaseException | None = None
    raw_output: object | None = None
    for attempt_index in range(_STRUCTURED_OUTPUT_MAX_ATTEMPTS):
        try:
            completion_kwargs = {
                "model_name": model_name,
                "system_prompt": system_prompt,
                "user_prompt": current_user_prompt,
                "schema_name": schema_model.__name__,
                "json_schema": schema,
            }
            if max_tokens is not None:
                completion_kwargs["max_tokens"] = max_tokens
            raw_output = await model_provider.structured_completion(
                **completion_kwargs
            )
            normalized = _coerce_structured_output(
                raw_output,
                schema_name=schema_model.__name__,
                planned_artifact_id=planned_artifact_id,
            )
            artifact = schema_model.model_validate(normalized)
            _require_artifact_id(artifact, planned_artifact_id, schema_model.__name__)
            _validate_safety(artifact.model_dump_json())
            if artifact_validator is not None:
                artifact = artifact_validator(artifact)
            return _StructuredArtifactAttemptResult(
                artifact=artifact,
                user_prompt=current_user_prompt,
                attempts=attempt_index + 1,
            )
        except ModelOutputTruncatedError as error:
            if prompt_name == "report_extraction":
                raise
            raise StructuredArtifactGenerationError(
                _structured_model_failure_message(
                    prompt_name=prompt_name,
                    schema_name=schema_model.__name__,
                    system_prompt=system_prompt,
                    user_prompt=current_user_prompt,
                    payload_json=payload_json,
                    cause=error,
                )
            ) from error
        except RuntimeError as error:
            last_error = error
            if _contains_timeout_wording(error) or _is_final_attempt(attempt_index):
                raise StructuredArtifactGenerationError(
                    _structured_model_failure_message(
                        prompt_name=prompt_name,
                        schema_name=schema_model.__name__,
                        system_prompt=system_prompt,
                        user_prompt=current_user_prompt,
                        payload_json=payload_json,
                        cause=error,
                    )
                ) from error
            current_user_prompt = _build_structured_output_repair_prompt(
                original_user_prompt=user_prompt,
                schema_name=schema_model.__name__,
                planned_artifact_id=planned_artifact_id,
                raw_output=raw_output,
                error=error,
            )
        except (
            StructuredArtifactGenerationError,
            ValidationError,
            ValueError,
            TypeError,
        ) as error:
            last_error = error
            if _is_final_attempt(attempt_index):
                raise StructuredArtifactGenerationError(
                    f"{schema_model.__name__} local structured output failed "
                    f"validation after {attempt_index + 1} attempt(s): {error}"
                ) from error
            current_user_prompt = _build_structured_output_repair_prompt(
                original_user_prompt=user_prompt,
                schema_name=schema_model.__name__,
                planned_artifact_id=planned_artifact_id,
                raw_output=raw_output,
                error=error,
            )
    raise StructuredArtifactGenerationError(
        f"{schema_model.__name__} local structured output failed: {last_error}"
    )


def _is_final_attempt(attempt_index: int) -> bool:
    return attempt_index >= _STRUCTURED_OUTPUT_MAX_ATTEMPTS - 1


def _generation_status_for_attempts(attempts: int) -> str:
    if attempts <= 1:
        return "generated"
    return "generated_after_structured_output_repair"


def _coerce_structured_output(
    raw_output: object,
    *,
    schema_name: str,
    planned_artifact_id: str,
) -> dict[str, object]:
    """Return a JSON object ready for Pydantic validation.

    Acceptance criteria:
        1. Accepts provider dictionaries, JSON strings, and fenced JSON text.
        2. Unwraps common structured-output wrapper keys deterministically.
        3. Adds only the planned artifact ID when the model omitted it.
        4. Does not invent or modify clinical rows, evidence, or rationale text.
        5. Invalid output shapes raise `TypeError` or `ValueError`.

    Args:
        raw_output: Raw provider output.
        schema_name: Expected schema name.
        planned_artifact_id: Deterministic artifact ID for this artifact.

    Returns:
        Mapping suitable for `schema_model.model_validate`.
    """
    parsed = _parse_structured_output_value(raw_output)
    unwrapped = _unwrap_structured_output_payload(parsed, schema_name=schema_name)
    if not isinstance(unwrapped, Mapping):
        raise TypeError(
            f"{schema_name} structured output must be a JSON object, "
            f"got {type(unwrapped).__name__}"
        )
    result = dict(unwrapped)
    if not str(result.get("artifact_id", "")).strip():
        result["artifact_id"] = planned_artifact_id
    return result


def _parse_structured_output_value(value: object) -> object:
    if not isinstance(value, str):
        return value
    text = _strip_json_fence(value)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise
        return json.loads(text[start : end + 1])


def _strip_json_fence(value: str) -> str:
    stripped = value.strip()
    if stripped.startswith("```json"):
        return stripped.removeprefix("```json").removesuffix("```").strip()
    if stripped.startswith("```"):
        return stripped.removeprefix("```").removesuffix("```").strip()
    return stripped


def _unwrap_structured_output_payload(
    value: object,
    *,
    schema_name: str,
) -> object:
    parsed = _parse_structured_output_value(value)
    if not isinstance(parsed, Mapping):
        return parsed
    generic_keys = _generic_structured_output_wrapper_keys()
    for key in generic_keys:
        if key in parsed and _is_wrapper_candidate(parsed, key):
            return _unwrap_structured_output_payload(parsed[key], schema_name=schema_name)
    if len(parsed) == 1:
        key, nested = next(iter(parsed.items()))
        schema_keys = _schema_structured_output_wrapper_keys(schema_name)
        wrapper_keys = {item.casefold() for item in (*generic_keys, *schema_keys)}
        if key.casefold() in wrapper_keys:
            return _unwrap_structured_output_payload(nested, schema_name=schema_name)
    return parsed


def _is_wrapper_candidate(parsed: Mapping[str, object], key: str) -> bool:
    if len(parsed) == 1:
        return True
    return "artifact_id" not in parsed


def _generic_structured_output_wrapper_keys() -> tuple[str, ...]:
    return (
        "artifact",
        "payload",
        "data",
        "output",
        "response",
        "arguments",
        "content",
        "json",
    )


def _schema_structured_output_wrapper_keys(schema_name: str) -> tuple[str, ...]:
    snake_name = _camel_to_snake(schema_name)
    return (
        schema_name,
        snake_name,
    )


def _camel_to_snake(value: str) -> str:
    first_pass = re.sub("(.)([A-Z][a-z]+)", r"\1_\2", value)
    return re.sub("([a-z0-9])([A-Z])", r"\1_\2", first_pass).casefold()


def _build_structured_output_repair_prompt(
    *,
    original_user_prompt: str,
    schema_name: str,
    planned_artifact_id: str,
    raw_output: object,
    error: BaseException,
) -> str:
    """Return a repair prompt for one malformed structured-output retry.

    Acceptance criteria:
        1. Preserves the original task and payload.
        2. Requires the same planned artifact ID.
        3. Includes validation diagnostics and prior output for correction.
        4. Caps prior output text to avoid uncontrolled prompt growth.
        5. Does not add new clinical facts beyond the original payload.

    Args:
        original_user_prompt: User prompt from the original attempt.
        schema_name: Expected schema name.
        planned_artifact_id: Required artifact ID.
        raw_output: Previous malformed provider output.
        error: Validation, parsing, or provider error.

    Returns:
        User prompt for the repair attempt.
    """
    raw_text = _structured_output_to_repair_text(raw_output)
    error_text = _truncate_repair_text(f"{type(error).__name__}: {error}")
    return (
        f"{original_user_prompt}\n\n"
        "Previous structured-output attempt failed validation. "
        "Return corrected JSON only. Do not add clinical facts that are absent "
        "from the original payload. Preserve all source IDs that support each "
        "clinical row.\n\n"
        f"Expected schema: {schema_name}\n"
        f"Required artifact_id: {planned_artifact_id}\n"
        f"Validation error:\n{error_text}\n\n"
        f"Previous output:\n{raw_text}\n"
    )


def _structured_output_to_repair_text(raw_output: object) -> str:
    if raw_output is None:
        return "<unavailable>"
    if isinstance(raw_output, str):
        return _truncate_repair_text(raw_output)
    return _truncate_repair_text(
        json.dumps(raw_output, sort_keys=True, indent=2, default=str)
    )


def _truncate_repair_text(value: str) -> str:
    if len(value) <= _REPAIR_PROMPT_TEXT_CHARS:
        return value
    return value[:_REPAIR_PROMPT_TEXT_CHARS] + "\n...[truncated for repair]"



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


def _structured_model_failure_message(
    *,
    prompt_name: str,
    schema_name: str,
    system_prompt: str,
    user_prompt: str,
    payload_json: str,
    cause: RuntimeError,
) -> str:
    """Return non-PHI prompt diagnostics for model-provider failures.

    Acceptance criteria:
        1. Determinism: Same inputs return the same diagnostic string.
        2. No mutation: Do not mutate prompt or payload values.
        3. Observability: Include prompt name, schema name, and prompt sizes.
        4. Privacy: Do not include prompt text, payload text, or schema JSON.

    Args:
        prompt_name: Structured-output prompt identifier.
        schema_name: Pydantic schema name requested from vLLM.
        system_prompt: System prompt text.
        user_prompt: User prompt text.
        payload_json: Prompt payload JSON text.
        cause: Model-provider runtime failure.

    Returns:
        Diagnostic error message safe for API/log surfacing.
    """
    return (
        f"{schema_name} structured output failed for prompt {prompt_name!r}: "
        f"system_prompt_chars={len(system_prompt)}, "
        f"user_prompt_chars={len(user_prompt)}, "
        f"payload_json_chars={len(payload_json)}, "
        f"cause={type(cause).__name__}: {cause}"
    )


def _require_artifact_id(artifact: BaseModel, planned_artifact_id: str, schema_name: str) -> None:
    actual = getattr(artifact, "artifact_id", None)
    if actual != planned_artifact_id:
        raise StructuredArtifactGenerationError(
            f"{schema_name} returned artifact_id {actual!r}; expected {planned_artifact_id!r}"
        )


def _validate_safety(text: str) -> None:
    validate_safety_language(text, _BANNED_UNSUPPORTED_CERTAINTY_PHRASES)


def _artifact_id(seed: str, artifact_type: str) -> str:
    return f"artifact_{uuid5(NAMESPACE_URL, f'{seed}:{artifact_type}').hex[:16]}"


def _context_source_ids(context: EvidenceContextBundle) -> list[str]:
    return [
        context.extraction.artifact_id,
        context.graph_evidence.artifact_id,
        *[tool.artifact_id for tool in context.tool_outputs],
        context.medea_reasoning.artifact_id,
    ]


def _context_source_chunk_ids(context: EvidenceContextBundle) -> list[str]:
    return _source_chunk_ids_from_extraction(context.extraction)


def _bundle_source_chunk_ids(bundle: ClinicalArtifactBundle) -> list[str]:
    return _source_chunk_ids_from_extraction(bundle.extraction)


def _source_chunk_ids_from_extraction(extraction: ReportExtractionOutput) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for finding in extraction.molecular_findings:
        chunk_id = (finding.source_chunk_id or "").strip()
        if chunk_id and chunk_id not in seen:
            seen.add(chunk_id)
            ordered.append(chunk_id)
    return ordered




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
    if bundle.decision_brief is not None:
        source_ids.append(bundle.decision_brief.artifact_id)
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


def _segment_report_chunks_for_prompt(
    source_chunks: Sequence[RetrievedDocumentChunk],
) -> list[RetrievedDocumentChunk]:
    """Return complete prompt-sized source units without changing source IDs."""
    units: list[RetrievedDocumentChunk] = []
    for source in source_chunks:
        text = source.chunk.source_text
        if len(text) <= _REPORT_EXTRACTION_SOURCE_UNIT_CHARS:
            units.append(source)
            continue
        for start in range(0, len(text), _REPORT_EXTRACTION_SOURCE_UNIT_CHARS):
            segment = text[start : start + _REPORT_EXTRACTION_SOURCE_UNIT_CHARS]
            units.append(
                source.model_copy(
                    update={
                        "chunk": source.chunk.model_copy(
                            update={"source_text": segment}
                        )
                    }
                )
            )
    return units




_CRITICAL_REPORT_SECTION_TERMS = (
    "genomic variants",
    "variant details",
    "potentially actionable",
    "biologically relevant",
    "treatment implications",
    "clinical trials",
    "immunotherapy markers",
    "microsatellite instability",
    "tumor mutational burden",
    "gene rearrangement",
    "altered splicing",
    "rna sequencing",
    "no gene rearrangements",
    "no reportable",
    "expression details",
    "research use only",
    "assay description",
    "assay limitation",
    "disclaimer",
    "low coverage",
    "tumor / normal matched",
)


async def _plan_token_bounded_report_extraction_batches(
    retrieved_chunks: Sequence[RetrievedDocumentChunk],
    *,
    model_provider: object,
    model_name: str,
    input_token_budget: int,
    batch_max_chunks: int,
) -> list[list[RetrievedDocumentChunk]]:
    """Return ordered batches bounded by the served model's tokenizer."""
    if input_token_budget <= 0:
        raise ValueError("input_token_budget must be positive")
    ordered = sorted(retrieved_chunks, key=_retrieved_chunk_page_order)
    batches: list[list[RetrievedDocumentChunk]] = []
    current: list[RetrievedDocumentChunk] = []
    current_tokens = 0
    for item in ordered:
        payload_text = json.dumps(
            _retrieved_chunk_prompt_payload(item),
            sort_keys=True,
        )
        counter = getattr(model_provider, "count_tokens", None)
        item_tokens = (
            await counter(model_name=model_name, text=payload_text)
            if callable(counter)
            else max(1, (len(payload_text) + 3) // 4)
        )
        would_overflow = current and (
            current_tokens + item_tokens > input_token_budget
            or len(current) >= batch_max_chunks
        )
        if would_overflow:
            batches.append(current)
            current = []
            current_tokens = 0
        current.append(item)
        current_tokens += item_tokens
    if current:
        batches.append(current)
    return batches


async def _generate_report_extraction_adaptively(
    *,
    prompt_chunks: Sequence[RetrievedDocumentChunk],
    all_source_chunks: Sequence[RetrievedDocumentChunk],
    planned_artifact_id: str,
    report_type: str,
    source_file_id: str,
    model_provider: object,
    model_name: str,
    prompts_root: Path,
    created_at: datetime,
    batch_index: int,
    total_batches: int,
    initial_max_tokens: int,
    retry_max_tokens: int,
    max_split_depth: int,
    min_segment_chars: int,
    depth: int,
) -> list[ReportExtractionOutput]:
    """Generate validated leaves, recursively splitting truncated batches."""
    output_tokens = retry_max_tokens if depth > 0 and len(prompt_chunks) == 1 else initial_max_tokens
    payload = {
        "planned_artifact_id": planned_artifact_id,
        "report_type": report_type,
        "source_file_id": source_file_id,
        "source_grounding_contract": {
            "model_may_use_only_retrieved_chunks": True,
            "finding_source_text_must_quote_chunk": True,
            "unsupported_findings_must_be_low_confidence": True,
            "graph_literature_treatment_and_behavior_inference_disallowed": True,
            "extract_this_batch_only": True,
            "full_report_is_processed_across_batches": True,
        },
        "leaf_output_contract": {
            "concise_values_only": True,
            "do_not_repeat_findings_or_text": True,
            "maximum_molecular_findings": 8,
            "maximum_negative_findings": 6,
            "maximum_assay_limitations": 6,
            "backend_merges_all_leaf_outputs": True,
        },
        "batch_context": _report_extraction_batch_context(
            batch_index=batch_index,
            total_batches=total_batches,
            prompt_chunks=prompt_chunks,
        ),
        "retrieved_chunks": [
            _retrieved_chunk_prompt_payload(item) for item in prompt_chunks
        ],
        "retrieval_truncation": _retrieved_chunk_truncation_summary(
            all_source_chunks,
            prompt_chunks,
        ),
    }
    try:
        result = await _generate_artifact(
            prompt_name="report_extraction",
            schema_model=_BoundedReportExtractionOutput,
            planned_artifact_id=planned_artifact_id,
            payload=payload,
            source_artifact_ids=[item.chunk.chunk_id for item in prompt_chunks],
            source_chunk_ids=[item.chunk.chunk_id for item in prompt_chunks],
            source_file_id=source_file_id,
            model_provider=model_provider,
            model_name=model_name,
            prompts_root=prompts_root,
            created_at=created_at,
            max_tokens=output_tokens,
        )
    except ModelOutputTruncatedError as error:
        if depth >= max_split_depth:
            raise IrreducibleReportExtractionTruncationError(
                "ReportExtractionOutput remained truncated at maximum split "
                f"depth={depth}, chunks={len(prompt_chunks)}, "
                f"finish_reason={error.finish_reason!r}, "
                f"content_chars={error.content_chars}"
            ) from error
        if len(prompt_chunks) == 1 and depth == 0:
            return await _generate_report_extraction_adaptively(
                prompt_chunks=prompt_chunks,
                all_source_chunks=all_source_chunks,
                planned_artifact_id=planned_artifact_id,
                report_type=report_type,
                source_file_id=source_file_id,
                model_provider=model_provider,
                model_name=model_name,
                prompts_root=prompts_root,
                created_at=created_at,
                batch_index=batch_index,
                total_batches=total_batches,
                initial_max_tokens=initial_max_tokens,
                retry_max_tokens=retry_max_tokens,
                max_split_depth=max_split_depth,
                min_segment_chars=min_segment_chars,
                depth=1,
            )
        split_batches = _split_truncated_report_batch(
            prompt_chunks,
            min_segment_chars=min_segment_chars,
        )
        if split_batches is None:
            raise IrreducibleReportExtractionTruncationError(
                "ReportExtractionOutput remained truncated for an irreducible "
                f"source unit at depth={depth}, "
                f"finish_reason={error.finish_reason!r}, "
                f"content_chars={error.content_chars}"
            ) from error
        leaves: list[ReportExtractionOutput] = []
        for split_chunks in split_batches:
            leaves.extend(
                await _generate_report_extraction_adaptively(
                    prompt_chunks=split_chunks,
                    all_source_chunks=all_source_chunks,
                    planned_artifact_id=planned_artifact_id,
                    report_type=report_type,
                    source_file_id=source_file_id,
                    model_provider=model_provider,
                    model_name=model_name,
                    prompts_root=prompts_root,
                    created_at=created_at,
                    batch_index=batch_index,
                    total_batches=total_batches,
                    initial_max_tokens=initial_max_tokens,
                    retry_max_tokens=retry_max_tokens,
                    max_split_depth=max_split_depth,
                    min_segment_chars=min_segment_chars,
                    depth=depth + 1,
                )
            )
        return leaves
    return [
        _source_align_report_extraction(
            ReportExtractionOutput.model_validate(result.artifact.model_dump()),
            prompt_chunks,
            report_type=report_type,
            source_file_id=source_file_id,
        )
    ]


def _split_truncated_report_batch(
    prompt_chunks: Sequence[RetrievedDocumentChunk],
    *,
    min_segment_chars: int,
) -> tuple[list[RetrievedDocumentChunk], list[RetrievedDocumentChunk]] | None:
    """Split a truncated batch without losing original source identity."""
    if len(prompt_chunks) > 1:
        midpoint = len(prompt_chunks) // 2
        return list(prompt_chunks[:midpoint]), list(prompt_chunks[midpoint:])
    source = prompt_chunks[0]
    text = source.chunk.source_text
    if len(text) < min_segment_chars * 2:
        return None
    midpoint = len(text) // 2
    boundary = text.rfind("\n\n", min_segment_chars, midpoint + 1)
    if boundary < min_segment_chars:
        boundary = text.rfind(". ", min_segment_chars, midpoint + 1)
        if boundary >= min_segment_chars:
            boundary += 1
    if boundary < min_segment_chars:
        boundary = midpoint
    parts = (text[:boundary].strip(), text[boundary:].strip())
    if any(len(part) < min_segment_chars for part in parts):
        return None
    segmented = [
        source.model_copy(
            update={"chunk": source.chunk.model_copy(update={"source_text": part})}
        )
        for part in parts
    ]
    return [segmented[0]], [segmented[1]]


def _plan_report_extraction_prompt_batches(
    retrieved_chunks: Sequence[RetrievedDocumentChunk],
    *,
    batch_max_chunks: int = _REPORT_EXTRACTION_BATCH_MAX_CHUNKS,
) -> list[list[RetrievedDocumentChunk]]:
    """Return report-extraction batches that cover the full report.

    Acceptance criteria:
        1. Every retrieved source chunk appears in exactly one batch.
        2. Batch order follows report page order so long NGS reports are parsed
           from start to finish.
        3. No batch exceeds the positive local-model chunk budget.
        4. Critical NGS sections are tagged, not preferentially dropped.
        5. The function is pure and deterministic.
    """
    if batch_max_chunks <= 0:
        raise ValueError("batch_max_chunks must be positive")
    ordered = sorted(retrieved_chunks, key=_retrieved_chunk_page_order)
    batches: list[list[RetrievedDocumentChunk]] = []
    for index in range(0, len(ordered), batch_max_chunks):
        batch = ordered[index : index + batch_max_chunks]
        if batch:
            batches.append(batch)
    return batches


def _retrieved_chunk_page_order(item: RetrievedDocumentChunk) -> tuple[int, int, str]:
    return (
        item.chunk.page_start,
        item.chunk.page_end,
        item.chunk.chunk_id.casefold(),
    )


def _report_extraction_batch_context(
    *,
    batch_index: int,
    total_batches: int,
    prompt_chunks: Sequence[RetrievedDocumentChunk],
) -> dict[str, object]:
    """Return audit metadata for one report-extraction batch."""
    return {
        "batch_number": batch_index + 1,
        "total_batches": total_batches,
        "page_start": min(item.chunk.page_start for item in prompt_chunks),
        "page_end": max(item.chunk.page_end for item in prompt_chunks),
        "chunk_ids": [item.chunk.chunk_id for item in prompt_chunks],
        "critical_section_tags": _critical_section_tags(prompt_chunks),
        "instruction": (
            "Extract source-grounded findings, negative results, treatment "
            "implications, trials, RNA/xR findings, expression caveats, assay "
            "limitations, and research-use disclaimers visible in this batch. "
            "Do not infer from chunks outside this batch."
        ),
    }


def _critical_section_tags(
    prompt_chunks: Sequence[RetrievedDocumentChunk],
) -> list[str]:
    tags: list[str] = []
    for item in prompt_chunks:
        text = f"{item.chunk.section}\n{item.chunk.source_text}".casefold()
        for term in _CRITICAL_REPORT_SECTION_TERMS:
            if term in text and term not in tags:
                tags.append(term)
    return tags


def _report_extraction_planner_summary(
    source_chunks: Sequence[RetrievedDocumentChunk],
    prompt_batches: Sequence[Sequence[RetrievedDocumentChunk]],
    *,
    batch_max_chunks: int,
) -> dict[str, object]:
    """Return prompt-planner metadata for provenance and debugging."""
    return {
        "planner": "full_report_batched_extraction",
        "source_chunks": len(source_chunks),
        "batches": len(prompt_batches),
        "batch_max_chunks": batch_max_chunks,
        "pages": sorted({item.chunk.page_start for item in source_chunks}),
        "critical_section_tags": _critical_section_tags(source_chunks),
        "all_source_chunk_ids": [item.chunk.chunk_id for item in source_chunks],
        "batch_chunk_ids": [
            [item.chunk.chunk_id for item in batch] for batch in prompt_batches
        ],
    }


def _merge_report_extraction_batches(
    batch_artifacts: Sequence[ReportExtractionOutput],
    *,
    planned_artifact_id: str,
    report_type: str,
    source_file_id: str,
) -> ReportExtractionOutput:
    """Merge report-extraction batch outputs into one source-backed artifact."""
    if not batch_artifacts:
        raise StructuredArtifactGenerationError(
            "ReportExtractionOutput requires at least one batch artifact"
        )
    findings = _dedupe_molecular_findings(
        finding
        for artifact in batch_artifacts
        for finding in artifact.molecular_findings
    )
    return ReportExtractionOutput(
        artifact_id=planned_artifact_id,
        report_type=report_type,
        disease=_first_nonempty(artifact.disease for artifact in batch_artifacts),
        specimen=_first_nonempty(artifact.specimen for artifact in batch_artifacts),
        tumor_percentage=_first_nonempty(
            artifact.tumor_percentage for artifact in batch_artifacts
        ),
        molecular_findings=findings,
        negative_findings=_dedupe_text(
            value
            for artifact in batch_artifacts
            for value in artifact.negative_findings
        ),
        assay_limitations=_dedupe_text(
            value
            for artifact in batch_artifacts
            for value in artifact.assay_limitations
        ),
        source_file_id=source_file_id,
        needs_human_review=True,
    )


def _dedupe_molecular_findings(
    findings: Sequence[MolecularFinding] | object,
) -> list[MolecularFinding]:
    result: list[MolecularFinding] = []
    seen: set[str] = set()
    for finding in findings:
        if not isinstance(finding, MolecularFinding):
            continue
        key = _finding_dedupe_key(finding)
        if key in seen:
            continue
        seen.add(key)
        result.append(
            finding.model_copy(
                update={
                    "finding_id": _stable_finding_id(finding, len(result)),
                    "needs_human_review": True,
                }
            )
        )
    return result


def _finding_dedupe_key(finding: MolecularFinding) -> str:
    values = [
        finding.gene or "",
        finding.alteration,
        finding.alteration_type,
        str(finding.source_page or ""),
        finding.source_text or "",
    ]
    return "|".join(_normalize_whitespace(value).casefold() for value in values)


def _stable_finding_id(finding: MolecularFinding, index: int) -> str:
    key = _finding_dedupe_key(finding) or f"finding:{index}"
    return f"finding_{uuid5(NAMESPACE_URL, key).hex[:16]}"


def _dedupe_text(values: object) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if not text:
            continue
        key = _normalize_whitespace(text).casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


def _first_nonempty(values: object) -> str | None:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None
def _cap_retrieved_chunks_for_prompt(
    retrieved_chunks: Sequence[RetrievedDocumentChunk],
) -> list[RetrievedDocumentChunk]:
    """Return the deterministic retrieved-chunk subset sent to the model.

    Acceptance criteria:
        1. Determinism: Same retrieved chunks produce the same ordered subset.
        2. No mutation: Do not mutate caller-owned chunk records.
        3. Prompt bound: Return at most `_MAX_PROMPT_RETRIEVED_CHUNKS`.
        4. Ranking: Prefer higher retrieval scores, then earlier pages, then
           stable chunk identifiers.

    Args:
        retrieved_chunks: Source chunks returned by retrieval.

    Returns:
        Capped retrieved chunks for report-extraction prompting.
    """
    ranked = sorted(retrieved_chunks, key=_retrieved_chunk_prompt_rank)
    return ranked[:_MAX_PROMPT_RETRIEVED_CHUNKS]


def _retrieved_chunk_prompt_rank(
    item: RetrievedDocumentChunk,
) -> tuple[float, int, int, str]:
    return (
        -_retrieved_chunk_score(item),
        item.chunk.page_start,
        item.chunk.page_end,
        item.chunk.chunk_id.casefold(),
    )


def _retrieved_chunk_score(item: RetrievedDocumentChunk) -> float:
    """Return a sortable retrieval score, with missing scores ranked lowest.

    Acceptance criteria:
        1. Determinism: Same retrieved chunk returns the same score.
        2. No mutation: Do not mutate the retrieved chunk.
        3. Validation: Missing scores are treated as lower priority.
        4. Compatibility: String and numeric scores are accepted.

    Args:
        item: Retrieved document chunk.

    Returns:
        Floating-point score for deterministic prompt ranking.
    """
    if item.score is None:
        return float("-inf")
    return float(item.score)


def _retrieved_chunk_truncation_summary(
    source_chunks: Sequence[RetrievedDocumentChunk],
    prompt_chunks: Sequence[RetrievedDocumentChunk],
) -> dict[str, object]:
    """Return prompt truncation metadata for report-extraction chunks.

    Acceptance criteria:
        1. Determinism: Same source and prompt chunks return the same summary.
        2. No mutation: Do not mutate caller-owned retrieved chunks.
        3. Transparency: Preserve original and retained counts.
        4. Grounding: Identify retained chunk IDs for source review.

    Args:
        source_chunks: All retrieved source chunks.
        prompt_chunks: Chunks retained for the prompt.

    Returns:
        JSON-serializable truncation summary.
    """
    return {
        "original_chunks": len(source_chunks),
        "kept_chunks": len(prompt_chunks),
        "max_kept_chunks": _MAX_PROMPT_RETRIEVED_CHUNKS,
        "max_source_text_chars": _MAX_PROMPT_SOURCE_TEXT_CHARS,
        "kept_chunk_ids": [item.chunk.chunk_id for item in prompt_chunks],
        "notice": _PROMPT_CONTEXT_CAP_NOTICE,
    }


def _retrieved_chunk_prompt_payload(item: RetrievedDocumentChunk) -> dict[str, object]:
    """Return source-grounding payload for one retrieved chunk.

    Acceptance criteria:
        1. Determinism: Same chunk returns the same payload.
        2. No mutation: Do not mutate the retrieved chunk.
        3. Prompt bound: Source text is capped for vLLM context safety.
        4. Grounding: Preserve source IDs, page range, section, method, and
           score.
    """
    return {
        "chunk_id": item.chunk.chunk_id,
        "page_start": item.chunk.page_start,
        "page_end": item.chunk.page_end,
        "section": item.chunk.section,
        "chunk_type": item.chunk.chunk_type,
        "source_text": truncate_text(
            item.chunk.source_text,
            _MAX_PROMPT_SOURCE_TEXT_CHARS,
        ),
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



_GENERIC_TUMOR_BEHAVIOR_TERMS = {
    "adaptive",
    "artifact",
    "behavior",
    "bounded",
    "clinical",
    "context",
    "derived",
    "enrichment",
    "evidence",
    "findings",
    "generating",
    "graph",
    "hypothesis",
    "interpretation",
    "literature",
    "medea",
    "model",
    "molecular",
    "review",
    "reviewable",
    "source",
    "structured",
    "suggest",
    "suggests",
    "support",
    "supports",
    "tooluniverse",
    "transition",
    "validation",
}

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
