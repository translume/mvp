from __future__ import annotations

from uuid import uuid5, NAMESPACE_URL

from translume_schemas.entities import NormalizedEntity, NormalizedEntitySet
from translume_schemas.extraction import ReportExtractionOutput


def normalize_report_entities(
    extraction: ReportExtractionOutput,
    *,
    case_id: str,
    session_id: str,
) -> NormalizedEntitySet:
    """Normalize report findings into computable biomedical entities.

    Acceptance criteria:
        1. Every normalized entity links to a source finding.
        2. Every entity has entity_type, original_text, and normalized_label.
        3. Ambiguous normalization is marked needs_human_review.
        4. No clinical inference is performed.
        5. Entity normalization failure does not erase source findings.

    Args:
        extraction: Structured report extraction.
        case_id: Current case ID.
        session_id: Current session ID.

    Returns:
        Normalized entity set.
    """
    entities: list[NormalizedEntity] = []
    if extraction.disease:
        disease_id = f"entity_{uuid5(NAMESPACE_URL, extraction.disease).hex[:16]}"
        entities.append(
            NormalizedEntity(
                entity_id=disease_id,
                entity_type="disease",
                original_text=extraction.disease,
                normalized_label=extraction.disease.strip().lower(),
                source_artifact_id=extraction.artifact_id,
            )
        )
    for finding in extraction.molecular_findings:
        if finding.gene:
            gene_label = finding.gene.strip().upper()
            entity_id = f"entity_{uuid5(NAMESPACE_URL, f'{finding.finding_id}:{gene_label}').hex[:16]}"
            entities.append(
                NormalizedEntity(
                    entity_id=entity_id,
                    entity_type="gene",
                    original_text=finding.gene,
                    normalized_label=gene_label,
                    source_finding_id=finding.finding_id,
                    source_artifact_id=extraction.artifact_id,
                )
            )
        alteration_label = finding.alteration.strip()
        alteration_id = f"entity_{uuid5(NAMESPACE_URL, f'{finding.finding_id}:{alteration_label}').hex[:16]}"
        entities.append(
            NormalizedEntity(
                entity_id=alteration_id,
                entity_type=finding.alteration_type,
                original_text=finding.alteration,
                normalized_label=alteration_label,
                source_finding_id=finding.finding_id,
                source_artifact_id=extraction.artifact_id,
                needs_human_review=finding.needs_human_review,
            )
        )
    artifact_id = f"artifact_{uuid5(NAMESPACE_URL, f'{extraction.artifact_id}:entities').hex[:16]}"
    return NormalizedEntitySet(
        artifact_id=artifact_id,
        case_id=case_id,
        session_id=session_id,
        entities=entities,
    )
