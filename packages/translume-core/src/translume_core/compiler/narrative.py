from __future__ import annotations

from uuid import NAMESPACE_URL, uuid5

from translume_schemas.export import ClinicalArtifactBundle, ClinicalNarrativeCompilerOutput


def generate_clinical_narrative_from_bundle(
    bundle: ClinicalArtifactBundle,
) -> ClinicalNarrativeCompilerOutput:
    """Render readable narrative from structured artifacts only.

    Acceptance criteria:
        1. Narrative uses only structured artifacts.
        2. Narrative includes extracted findings, biological axes, matrix,
           mechanism, validation, tumor-behavior hypotheses, and uncertainty.
        3. Narrative introduces no unsupported genes, therapies, mechanisms, or
           claims.
        4. No treatment recommendation is generated.

    Args:
        bundle: Clinical artifact bundle.

    Returns:
        Clinical narrative artifact.
    """
    artifact_id = f"artifact_{uuid5(NAMESPACE_URL, f'{bundle.session_id}:narrative').hex[:16]}"
    lines = [
        "# Translume Review Packet",
        "",
        "This output is for research-support review. It is not a treatment recommendation.",
        "",
        "## Report findings",
    ]
    for finding in bundle.extraction.molecular_findings:
        lines.append(f"- {finding.gene or 'Alteration'}: {finding.alteration} ({finding.alteration_type}); source page {finding.source_page or 'unknown'}.")
    if bundle.phenotype:
        lines.extend(["", "## Biological axes"])
        for axis in bundle.phenotype.axes:
            lines.append(f"- {axis.label}: {axis.evidence_class}; validation needed: {axis.validation_needed}.")
    if bundle.matrix:
        lines.extend(["", "## Molecular-fit review matrix"])
        for row in bundle.matrix.rows:
            lines.append(f"- Rank {row.rank}: {row.molecular_fit}. Why from omics: {row.why_from_omics}")
    if bundle.confirmatory:
        lines.extend(["", "## Confirmatory testing questions"])
        for test in bundle.confirmatory.tests:
            lines.append(f"- {test.question} Evidence gap: {test.evidence_gap}")
    if bundle.tumor_behavior:
        lines.extend(["", "## Tumor-behavior hypothesis"])
        for state in bundle.tumor_behavior.state_evidence:
            lines.append(f"- State context {state.state_label}: {state.evidence_class}; {state.uncertainty}")
        for transition in bundle.tumor_behavior.transition_hypotheses:
            lines.append(f"- Transition hypothesis {transition.from_state} → {transition.to_state}: {transition.rationale}")
    lines.extend(["", "## Claims requiring review"])
    for claim in bundle.claims:
        lines.append(f"- [{claim.claim_class}] {claim.claim} Status: {claim.validation_status}.")
    return ClinicalNarrativeCompilerOutput(
        artifact_id=artifact_id,
        markdown="\n".join(lines),
        source_artifact_ids=_source_artifact_ids(bundle),
        safety_note="Research-support only; no treatment recommendation, outcome prediction, or transition probability is generated.",
    )


def _source_artifact_ids(bundle: ClinicalArtifactBundle) -> list[str]:
    ids = [bundle.extraction.artifact_id]
    for artifact in [bundle.entities, bundle.phenotype, bundle.matrix, bundle.sankey, bundle.confirmatory, bundle.tumor_behavior]:
        if artifact is not None:
            ids.append(artifact.artifact_id)
    if bundle.evidence_context is not None:
        ids.append(bundle.evidence_context.artifact_id)
    ids.extend(claim.claim_id for claim in bundle.claims)
    return ids
