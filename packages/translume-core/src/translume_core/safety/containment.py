from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from translume_schemas.export import (
    ClinicalArtifactBundle,
    ClinicalNarrativeCompilerOutput,
    NarrativeContainmentFinding,
    NarrativeContainmentReport,
)

_UPPERCASE_BIOMEDICAL = re.compile(r"\b[A-Z][A-Z0-9]{2,14}\b")
_SLASH_BIOMEDICAL = re.compile(r"\b[A-Za-z0-9]+(?:/[A-Za-z0-9]+)+\b")
_BIOMEDICAL_SLASH_ANCHOR = re.compile(r"[A-Z][A-Z0-9]{1,14}")
_DRUG_LIKE = re.compile(
    r"\b[A-Za-z][A-Za-z0-9-]*(?:mab|nib|tinib|ciclib|parib|rafenib|lisib|sertib|metinib)\b",
    re.IGNORECASE,
)
_ALTERATION_LIKE = re.compile(
    r"\b[A-Za-z0-9/+-]{2,30}\s+(?:loss|gain|amplification|deletion|fusion|overexpression|underexpression|mutation|variant|rearrangement|splicing)\b",
    re.IGNORECASE,
)
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_+/-]*")

_ALLOWED_UPPERCASE_TERMS = {
    "API",
    "ASGI",
    "CNV",
    "CT",
    "DNA",
    "EID",
    "FHIR",
    "FISH",
    "GPU",
    "HLA",
    "HNSW",
    "IHC",
    "JSON",
    "LOF",
    "MIMS",
    "MRI",
    "MSI",
    "MVP",
    "NGS",
    "OCR",
    "PDF",
    "PET",
    "PHI",
    "RNA",
    "ROI",
    "TMB",
    "UI",
    "VAF",
    "VCF",
    "VLLM",
    "WGS",
}

_ALLOWED_CONTEXT_TERMS = {
    "artifact",
    "artifacts",
    "axis",
    "behavior",
    "case",
    "claim",
    "claims",
    "clinical",
    "confirmatory",
    "context",
    "diagnosis",
    "disease",
    "evidence",
    "extraction",
    "finding",
    "findings",
    "graph",
    "human",
    "hypothesis",
    "hypotheses",
    "matrix",
    "mechanism",
    "molecular",
    "narrative",
    "oncology",
    "packet",
    "pathway",
    "provenance",
    "recommendation",
    "report",
    "research",
    "review",
    "reviewable",
    "safety",
    "source",
    "state",
    "structured",
    "support",
    "testing",
    "translume",
    "tumor",
    "validation",
}
_ADMINISTRATIVE_MISSING_VALUES = frozenset({
    "n/a",
    "na",
    "not applicable",
    "not available",
    "unknown",
})
_VAGUE_ALTERATION_ANCHORS = {
    "a",
    "an",
    "any",
    "described",
    "detected",
    "identified",
    "noted",
    "observed",
    "reported",
    "that",
    "the",
    "these",
    "this",
    "those",
}
_GRAMMATICAL_ALTERATION_ANCHORS = frozenset({
    "and",
    "at",
    "but",
    "by",
    "for",
    "from",
    "in",
    "of",
    "on",
    "or",
    "to",
    "with",
    "without",
})


class NarrativeContainmentError(ValueError):
    """Raised when a narrative introduces unsupported clinical content."""


@dataclass(frozen=True)
class NarrativeContainmentContext:
    """Normalized support context used to validate a narrative."""

    supported_text: str
    supported_terms: frozenset[str]
    source_artifact_ids: tuple[str, ...]


def build_narrative_containment_context(
    bundle: ClinicalArtifactBundle,
) -> NarrativeContainmentContext:
    """Build the structured source corpus that a narrative may reference.

    Acceptance criteria:
        1. Uses actual bundle artifacts, evidence, claims, and provenance.
        2. Excludes narrative markdown so a narrative cannot self-support.
        3. Preserves source artifact identifiers for audit and ledger usage.
        4. Performs no model calls, network calls, or clinical inference.
    """
    bundle_without_narrative = bundle.model_copy(
        update={"narrative": None, "narrative_containment": None}
    )
    payload = bundle_without_narrative.model_dump(mode="json")
    text_values = list(_iter_text_values(payload))
    supported_text = _normalize_text(" ".join(text_values))
    supported_terms = frozenset(_extract_supported_terms(text_values))
    source_ids = tuple(dict.fromkeys(_source_artifact_ids_from_bundle(bundle_without_narrative)))
    return NarrativeContainmentContext(
        supported_text=supported_text,
        supported_terms=supported_terms,
        source_artifact_ids=source_ids,
    )


def validate_narrative_fact_containment(
    narrative: ClinicalNarrativeCompilerOutput,
    bundle: ClinicalArtifactBundle,
) -> NarrativeContainmentReport:
    """Return deterministic containment results for a generated narrative.

    Acceptance criteria:
        1. Flags unsupported gene-like names introduced by the narrative.
        2. Flags unsupported therapy/drug-like terms introduced by the narrative.
        3. Flags unsupported alteration/signal phrases introduced by the narrative.
        4. Flags narrative source_artifact_ids absent from the source bundle.
        5. Does not mutate the narrative or bundle.
    """
    context = build_narrative_containment_context(bundle)
    findings = _unsupported_findings(narrative.markdown, context)
    findings.extend(_unsupported_source_artifact_findings(narrative, context))
    return NarrativeContainmentReport(
        artifact_id=f"{narrative.artifact_id}:containment",
        narrative_artifact_id=narrative.artifact_id,
        source_artifact_ids=list(context.source_artifact_ids),
        unsupported_findings=findings,
        passed=len(findings) == 0,
    )


def require_narrative_fact_containment(
    narrative: ClinicalNarrativeCompilerOutput,
    bundle: ClinicalArtifactBundle,
) -> NarrativeContainmentReport:
    """Require a final narrative to be contained by structured artifacts.

    Acceptance criteria:
        1. Runs after narrative generation and before packet export.
        2. Raises NarrativeContainmentError when unsupported content exists.
        3. Lists bounded unsupported content without leaking secrets.
        4. Returns the containment report when validation passes.
    """
    report = validate_narrative_fact_containment(narrative, bundle)
    if report.unsupported_findings:
        terms = ", ".join(
            finding.term for finding in report.unsupported_findings[:12]
        )
        raise NarrativeContainmentError(
            f"ClinicalNarrativeCompilerOutput introduced unsupported content: {terms}"
        )
    return report


# Backward-compatible explicit verb used by earlier tutorials/tests.
enforce_narrative_fact_containment = require_narrative_fact_containment


def _unsupported_findings(
    narrative_text: str,
    context: NarrativeContainmentContext,
) -> list[NarrativeContainmentFinding]:
    findings: list[NarrativeContainmentFinding] = []
    for term, term_type, sentence in _candidate_terms(narrative_text):
        normalized_term = _normalize_term(term)
        if _term_is_allowed(normalized_term, term, context):
            continue
        findings.append(
            NarrativeContainmentFinding(
                term=term,
                term_type=term_type,
                evidence_gap=(
                    "Term or phrase appeared in ClinicalNarrativeCompilerOutput "
                    "but was absent from source report artifacts, graph evidence, "
                    "tool outputs, Medea reasoning, claim cards, and provenance."
                ),
                sentence=_bounded_sentence(sentence),
            )
        )
    return findings


def _unsupported_source_artifact_findings(
    narrative: ClinicalNarrativeCompilerOutput,
    context: NarrativeContainmentContext,
) -> list[NarrativeContainmentFinding]:
    findings: list[NarrativeContainmentFinding] = []
    known_ids = set(context.source_artifact_ids)
    for source_id in narrative.source_artifact_ids:
        if source_id in known_ids or _normalize_text(source_id) in context.supported_text:
            continue
        findings.append(
            NarrativeContainmentFinding(
                term=source_id,
                term_type="unsupported_source_artifact_id",
                evidence_gap=(
                    "Narrative source_artifact_ids included an artifact ID that "
                    "was not present in the source clinical artifact bundle."
                ),
                sentence="source_artifact_ids",
            )
        )
    if not narrative.source_artifact_ids:
        findings.append(
            NarrativeContainmentFinding(
                term="<missing source_artifact_ids>",
                term_type="missing_source_artifact_ids",
                evidence_gap="Narrative did not declare the source artifacts used to generate it.",
                sentence="source_artifact_ids",
            )
        )
    return findings


def _candidate_terms(text: str) -> list[tuple[str, str, str]]:
    candidates: list[tuple[str, str, str]] = []
    for sentence in _sentences(text):
        candidates.extend(
            (term, "gene_or_biomedical_symbol", sentence)
            for term in _UPPERCASE_BIOMEDICAL.findall(sentence)
        )
        candidates.extend(
            (term, "slash_biomedical_term", sentence)
            for term in _SLASH_BIOMEDICAL.findall(sentence)
            if _slash_term_is_biomedical_candidate(term)
        )
        candidates.extend(
            (term, "therapy_or_drug_like_term", sentence)
            for term in _DRUG_LIKE.findall(sentence)
        )
        candidates.extend(
            (term, "alteration_or_signal_phrase", sentence)
            for term in _ALTERATION_LIKE.findall(sentence)
            if _alteration_phrase_is_specific(term)
        )
    return list(dict.fromkeys(candidates))


def _slash_term_is_biomedical_candidate(term: str) -> bool:
    """Return whether a slash-delimited term has a biomedical symbol anchor.

    Acceptance criteria:
        1. Determinism: The same term always returns the same result.
        2. No mutation: Caller-owned values are not modified.
        3. Administrative values: `N/A` is not a biomedical candidate.
        4. Ordinary notation: Lowercase prose such as `and/or` is excluded.
        5. Biomedical notation: Symbol-anchored terms such as `BRAF/MEK`
           remain containment candidates.

    Args:
        term: Slash-delimited narrative term.

    Returns:
        True when at least one segment has a biomedical-symbol shape.
    """
    if _normalize_term(term) in _ADMINISTRATIVE_MISSING_VALUES:
        return False
    return any(
        _BIOMEDICAL_SLASH_ANCHOR.fullmatch(segment) is not None
        for segment in term.split("/")
    )


def _alteration_phrase_is_specific(term: str) -> bool:
    """Return whether an alteration-like phrase has a grounded anchor.

    Acceptance criteria:
        1. Determinism: Same term returns the same result.
        2. No mutation: Caller-owned values are not mutated.
        3. Specificity: Gene-like, biomarker-like, or assay-like alteration
           phrases remain containment candidates.
        4. Fragment handling: Determiner-led, modifier-led, and
           grammar-led fragments such as `the mutation`,
           `This amplification`, `identified variant`, `to loss`, and
           `and fusion` are not treated as specific molecular claims.

    Args:
        term: Candidate alteration phrase matched from narrative text.

    Returns:
        True when the phrase should be checked against source artifacts.
    """
    tokens = _TOKEN.findall(term)
    if not tokens:
        return False
    anchor = _normalize_term(tokens[0])
    non_specific_anchors = (
        _VAGUE_ALTERATION_ANCHORS | _GRAMMATICAL_ALTERATION_ANCHORS
    )
    return anchor not in non_specific_anchors


def _term_is_allowed(
    normalized_term: str,
    original_term: str,
    context: NarrativeContainmentContext,
) -> bool:
    if not normalized_term:
        return True
    if original_term.upper() in _ALLOWED_UPPERCASE_TERMS:
        return True
    if normalized_term in _ALLOWED_CONTEXT_TERMS:
        return True
    if normalized_term in _ADMINISTRATIVE_MISSING_VALUES:
        return True
    if normalized_term in context.supported_terms:
        return True
    return normalized_term in context.supported_text


def _extract_supported_terms(text_values: Sequence[str]) -> set[str]:
    terms: set[str] = set()
    for value in text_values:
        normalized = _normalize_text(value)
        terms.add(normalized)
        for token in _TOKEN.findall(value):
            terms.add(_normalize_term(token))
        for pattern in (_UPPERCASE_BIOMEDICAL, _SLASH_BIOMEDICAL, _DRUG_LIKE, _ALTERATION_LIKE):
            for term in pattern.findall(value):
                terms.add(_normalize_term(term))
    return {term for term in terms if term}


def _source_artifact_ids_from_bundle(bundle: ClinicalArtifactBundle) -> list[str]:
    ids: list[str] = [bundle.extraction.artifact_id]
    for artifact in (
        bundle.entities,
        bundle.evidence_context,
        bundle.phenotype,
        bundle.matrix,
        bundle.sankey,
        bundle.confirmatory,
        bundle.tumor_behavior,
        bundle.decision_brief,
    ):
        artifact_id = getattr(artifact, "artifact_id", None)
        if artifact_id:
            ids.append(str(artifact_id))
    if bundle.evidence_context is not None:
        ids.append(bundle.evidence_context.graph_evidence.artifact_id)
        ids.append(bundle.evidence_context.medea_reasoning.artifact_id)
        ids.extend(tool.artifact_id for tool in bundle.evidence_context.tool_outputs)
    ids.extend(claim.claim_id for claim in bundle.claims)
    ids.extend(record.artifact_id for record in bundle.provenance)
    return ids


def _iter_text_values(value: Any) -> Iterable[str]:
    if value is None:
        return
    if isinstance(value, str):
        if value.strip():
            yield value
        return
    if isinstance(value, BaseModel):
        yield from _iter_text_values(value.model_dump(mode="json"))
        return
    if isinstance(value, dict):
        for item in value.values():
            yield from _iter_text_values(item)
        return
    if isinstance(value, (list, tuple, set)):
        for item in value:
            yield from _iter_text_values(item)
        return


def _sentences(text: str) -> list[str]:
    sentences: list[str] = []
    for block in text.splitlines():
        stripped = block.strip()
        if not stripped:
            continue
        sentences.extend(
            part.strip() for part in _SENTENCE_SPLIT.split(stripped) if part.strip()
        )
    return sentences


def _bounded_sentence(sentence: str, max_chars: int = 320) -> str:
    clean = " ".join(sentence.split())
    if len(clean) <= max_chars:
        return clean
    return clean[: max_chars - 3] + "..."


def _normalize_text(text: str) -> str:
    return " ".join(text.casefold().replace("_", " ").replace("-", " ").split())


def _normalize_term(text: str) -> str:
    return _normalize_text(text).strip()
