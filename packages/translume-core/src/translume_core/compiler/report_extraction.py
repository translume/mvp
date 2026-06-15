from __future__ import annotations

import re
from collections.abc import Sequence
from uuid import NAMESPACE_URL, uuid5

from translume_schemas.document import DocumentChunk
from translume_schemas.extraction import MolecularFinding, ReportExtractionOutput

_GENE_PATTERN = re.compile(r"\b[A-Z][A-Z0-9]{1,11}\b")
_CDOT_PATTERN = re.compile(r"c\.[A-Za-z0-9_+>\-.*]+", re.IGNORECASE)
_COPY_EVENT_PATTERN = re.compile(
    r"copy[- ]?number\s+(?P<direction>loss|gain)|deletion",
    re.IGNORECASE,
)
_EXPRESSION_EVENT_PATTERN = re.compile(
    r"(?P<direction>Overexpressed|Underexpressed)",
    re.IGNORECASE,
)
_VAF_PATTERN = re.compile(
    r"(?:VAF|variant allele fraction)?[^0-9]{0,20}(?P<vaf>[0-9]+(?:\.[0-9]+)?%)",
    re.IGNORECASE,
)
_CONTEXT_WINDOW = 180


def generate_report_extraction_from_chunks(
    chunks: Sequence[DocumentChunk],
    *,
    report_type: str,
    source_file_id: str,
) -> ReportExtractionOutput:
    """Extract source-backed report findings using deterministic text rules.

    This function is a production deterministic extractor, not a mock. It exists
    so the MVP can produce auditable extraction outputs from report text even
    before a local structured-output model is available. A local vLLM extractor
    can replace or augment this function behind the same schema contract.

    Acceptance criteria:
        1. Output identifies what the report says from source chunks only.
        2. Every molecular finding has source_page and source_text when found.
        3. Negative findings and limitations are captured.
        4. Research-use-only expression signals are labeled as such.
        5. No graph/literature inference is added at this stage.
        6. No treatment recommendation is generated.

    Args:
        chunks: Source-backed document chunks.
        report_type: User-selected report type.
        source_file_id: Source file identifier.

    Returns:
        Report extraction artifact.
    """
    artifact_id = f"artifact_{uuid5(NAMESPACE_URL, f'{source_file_id}:report_extraction').hex[:16]}"
    full_text = "\n".join(chunk.source_text for chunk in chunks)
    disease = _extract_disease(full_text)
    specimen = _extract_specimen(full_text)
    tumor_percentage = _extract_tumor_percentage(full_text)
    findings = _extract_findings(chunks)
    negative_findings = _extract_negative_findings(chunks)
    limitations = _extract_assay_limitations(chunks)
    return ReportExtractionOutput(
        artifact_id=artifact_id,
        report_type=report_type,
        disease=disease,
        specimen=specimen,
        tumor_percentage=tumor_percentage,
        molecular_findings=findings,
        negative_findings=negative_findings,
        assay_limitations=limitations,
        source_file_id=source_file_id,
        needs_human_review=True,
    )


def _extract_disease(text: str) -> str | None:
    match = re.search(
        r"Diagnosis\s+(?P<diagnosis>[^\n|]+)",
        text,
        re.IGNORECASE,
    )
    if match:
        return match.group("diagnosis").strip(" -|\n")[:160]
    return None


def _extract_specimen(text: str) -> str | None:
    match = re.search(r"Tumor specimen\s+(?P<specimen>[^\n|]+)", text, re.IGNORECASE)
    if match:
        return match.group("specimen").strip()[:160]
    return None


def _extract_tumor_percentage(text: str) -> str | None:
    match = re.search(r"Tumor Percentage:?\s*(?P<pct>[0-9]+%)", text, re.IGNORECASE)
    if match:
        return match.group("pct")
    return None


def _extract_findings(chunks: Sequence[DocumentChunk]) -> list[MolecularFinding]:
    findings: dict[str, MolecularFinding] = {}
    for chunk in chunks:
        text = chunk.source_text
        normalized = _normalize_ocr_text(text)
        if chunk.chunk_type in {"molecular_finding", "variant_detail", "unknown"}:
            _extract_variant_findings(findings, chunk, normalized)
            _extract_copy_number_findings(findings, chunk, normalized)
        if chunk.chunk_type == "rna_expression" or _contains_research_use_marker(text):
            _extract_expression_findings(findings, chunk, text)
    return list(findings.values())


def _extract_variant_findings(
    findings: dict[str, MolecularFinding],
    chunk: DocumentChunk,
    text: str,
) -> None:
    for match in _CDOT_PATTERN.finditer(text):
        gene = _nearest_gene_before(text, match.start())
        if gene is None:
            continue
        context = _context_around(text, match.start())
        vaf = _extract_vaf(context)
        effect = _variant_effect_label(context)
        alteration = " ".join(part for part in [match.group(0), effect, vaf] if part)
        _add_finding(findings, chunk, gene, alteration, "variant", 0.82)


def _extract_copy_number_findings(
    findings: dict[str, MolecularFinding],
    chunk: DocumentChunk,
    text: str,
) -> None:
    for match in _COPY_EVENT_PATTERN.finditer(text):
        gene = _nearest_gene_before(text, match.start())
        if gene is None:
            continue
        context = match.group(0).lower()
        if "gain" in context:
            _add_finding(findings, chunk, gene, "copy-number gain", "copy_number_gain", 0.84)
            continue
        _add_finding(findings, chunk, gene, "copy-number loss", "copy_number_loss", 0.84)


def _extract_expression_findings(
    findings: dict[str, MolecularFinding],
    chunk: DocumentChunk,
    text: str,
) -> None:
    normalized = _normalize_ocr_text(text)
    for match in _EXPRESSION_EVENT_PATTERN.finditer(normalized):
        gene = _nearest_gene_before(normalized, match.start())
        if gene is None:
            continue
        direction = match.group("direction").lower()
        _add_finding(
            findings,
            chunk,
            gene,
            f"RNA expression {direction}",
            "rna_expression",
            0.72,
            research_use_only=True,
        )


def _nearest_gene_before(text: str, position: int) -> str | None:
    window_start = max(0, position - _CONTEXT_WINDOW)
    window = text[window_start:position]
    matches = list(_GENE_PATTERN.finditer(window))
    for match in reversed(matches):
        gene = _normalize_gene(match.group(0))
        if _looks_like_molecular_gene(gene):
            return gene
    return None


def _context_around(text: str, position: int) -> str:
    start = max(0, position - _CONTEXT_WINDOW)
    end = min(len(text), position + _CONTEXT_WINDOW)
    return text[start:end]


def _normalize_ocr_text(text: str) -> str:
    return text.upper().replace("COKN", "CDKN")


def _normalize_gene(value: str) -> str:
    return value.upper().replace("COKN", "CDKN")


def _looks_like_molecular_gene(gene: str) -> bool:
    if len(gene) < 2 or len(gene) > 12:
        return False
    blocked_tokens = {
        "VAF",
        "DNA",
        "RNA",
        "TMB",
        "MSI",
        "HLA",
        "NCCN",
        "FDA",
        "GENOMIC",
        "VARIANTS",
        "DIAGNOSIS",
        "TUMOR",
        "SPECIMEN",
        "SOFT",
        "TISSUE",
        "CHEST",
        "WALL",
        "PERCENTAGE",
        "COPY",
        "NUMBER",
        "LOSS",
        "GAIN",
        "NORMAL",
        "SAMPLE",
        "RECEIVED",
        "EXPRESSION",
        "DETAILS",
        "RESEARCH",
        "ONLY",
    }
    if gene in blocked_tokens:
        return False
    return bool(_GENE_PATTERN.fullmatch(gene))


def _extract_vaf(context: str) -> str | None:
    matches = list(_VAF_PATTERN.finditer(context))
    if not matches:
        return None
    return f"VAF {matches[-1].group('vaf')}"


def _variant_effect_label(context: str) -> str | None:
    lowered = context.lower()
    if "loss-of-function" in lowered or "lof" in lowered:
        return "loss-of-function"
    if "splice" in lowered:
        return "splice-region variant"
    if "missense" in lowered:
        return "missense variant"
    if "frameshift" in lowered:
        return "frameshift variant"
    return None


def _contains_research_use_marker(text: str) -> bool:
    return "research use only" in text.lower()


def _add_finding(
    findings: dict[str, MolecularFinding],
    chunk: DocumentChunk,
    gene: str,
    alteration: str,
    alteration_type: str,
    confidence: float,
    *,
    research_use_only: bool = False,
) -> None:
    if alteration_type == "copy_number_loss":
        for existing in findings.values():
            if existing.gene == gene and existing.alteration_type == alteration_type:
                return
    key = f"{gene}:{alteration_type}:{alteration}".lower()
    if key in findings:
        return
    finding_id = f"finding_{uuid5(NAMESPACE_URL, f'{chunk.chunk_id}:{key}').hex[:16]}"
    findings[key] = MolecularFinding(
        finding_id=finding_id,
        gene=gene,
        alteration=alteration,
        alteration_type=alteration_type,
        source_page=chunk.page_start,
        source_text=chunk.source_text,
        source_chunk_id=chunk.chunk_id,
        confidence=confidence,
        needs_human_review=True,
        research_use_only=research_use_only,
    )


def _extract_negative_findings(chunks: Sequence[DocumentChunk]) -> list[str]:
    negative: list[str] = []
    for chunk in chunks:
        text = chunk.source_text.lower()
        if "no gene rearrangements" in text or "no reportable altered splicing" in text:
            negative.append("No reportable gene rearrangements or altered splicing events were identified from RNA sequencing.")
        if "no normal sample" in text or "normal sample was received" in text:
            negative.append("No normal sample was received; tumor/normal matched analysis was not performed.")
    return _dedupe(negative)


def _extract_assay_limitations(chunks: Sequence[DocumentChunk]) -> list[str]:
    limitations: list[str] = []
    for chunk in chunks:
        text = chunk.source_text.lower()
        if "low coverage" in text:
            limitations.append("Low coverage regions should be interpreted carefully.")
        if "research use only" in text:
            limitations.append("RNA expression profile is research-use-only and not established for clinical decision-making.")
        if "tumor only" in text or "normal sample" in text:
            limitations.append("Tumor-only interpretation can limit germline/somatic distinction and related inferences.")
    return _dedupe(limitations)


def _dedupe(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            out.append(value)
    return out
