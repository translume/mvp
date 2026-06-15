from __future__ import annotations

from uuid import uuid5, NAMESPACE_URL

from translume_schemas.claims import ClaimEvidenceOutput
from translume_schemas.evidence import EvidenceContextBundle


def classify_evidence_strength(context: EvidenceContextBundle) -> list[ClaimEvidenceOutput]:
    """Classify report and enrichment statements into reviewable claims.

    Acceptance criteria:
        1. Every claim has claim_id.
        2. Every claim has claim_class and source artifact IDs.
        3. Unsupported claims are never marked as fact.
        4. Every claim starts with validation_status=needs_review.
        5. Function is deterministic and pure.

    Args:
        context: Combined evidence context.

    Returns:
        Claim evidence outputs.
    """
    claims: list[ClaimEvidenceOutput] = []
    for finding in context.extraction.molecular_findings:
        claim = f"Report states {finding.gene or 'an alteration'}: {finding.alteration}."
        claim_id = f"claim_{uuid5(NAMESPACE_URL, finding.finding_id).hex[:16]}"
        claims.append(
            ClaimEvidenceOutput(
                claim_id=claim_id,
                claim=claim,
                claim_class="patient_specific_finding",
                source_artifact_ids=[context.extraction.artifact_id],
                evidence_source="source_report",
                relevance="patient-specific molecular finding from report extraction",
                limitations="requires human review against source text",
            )
        )
    for edge in context.graph_evidence.edges:
        claim_id = f"claim_{uuid5(NAMESPACE_URL, edge.edge_id).hex[:16]}"
        claims.append(
            ClaimEvidenceOutput(
                claim_id=claim_id,
                claim=f"Graph context contains relation {edge.relation_type}.",
                claim_class="graph_supported_context",
                source_artifact_ids=[context.graph_evidence.artifact_id],
                evidence_source=edge.source,
                relevance="biomedical graph context for interpretation",
                limitations="graph relationship is context, not clinical truth",
            )
        )
    for output in context.tool_outputs:
        claim_id = f"claim_{uuid5(NAMESPACE_URL, output.artifact_id).hex[:16]}"
        claims.append(
            ClaimEvidenceOutput(
                claim_id=claim_id,
                claim=output.summary,
                claim_class="tool_supported_context",
                source_artifact_ids=[output.artifact_id],
                evidence_source=output.workflow,
                relevance="governed scientific workflow output",
                limitations="requires human review",
            )
        )
    if context.medea_reasoning.summary:
        claim_id = f"claim_{uuid5(NAMESPACE_URL, context.medea_reasoning.artifact_id).hex[:16]}"
        claims.append(
            ClaimEvidenceOutput(
                claim_id=claim_id,
                claim=context.medea_reasoning.summary,
                claim_class="medea_supported_reasoning",
                source_artifact_ids=[context.medea_reasoning.artifact_id],
                evidence_source="medea_bounded_reasoning",
                relevance="structured omics/literature reasoning support",
                limitations="model-supported reasoning; requires human review",
            )
        )
    return claims
