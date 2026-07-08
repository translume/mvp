from __future__ import annotations

from uuid import NAMESPACE_URL, uuid5

from translume_schemas.export import ClinicalArtifactBundle, ClinicalNarrativeCompilerOutput


def generate_clinical_narrative_from_bundle(
    bundle: ClinicalArtifactBundle,
) -> ClinicalNarrativeCompilerOutput:
    """Render readable narrative from structured artifacts only.

    Acceptance criteria:
        1. Narrative uses only structured artifacts.
        2. Narrative leads with the decision brief when present.
        3. Narrative introduces no unsupported genes, therapies, mechanisms, or
           claims.
        4. Narrative remains clinician-review decision support and rejects
           unsupported certainty rather than treatment logic.

    Args:
        bundle: Clinical artifact bundle.

    Returns:
        Clinical narrative artifact.
    """
    artifact_id = (
        f"artifact_{uuid5(NAMESPACE_URL, f'{bundle.session_id}:narrative').hex[:16]}"
    )
    lines = [
        "# Translume Tumor Behavior Intelligence Brief",
        "",
        (
            "This output is clinician decision-support. It requires oncology "
            "review and does not claim certain response, cure, survival "
            "benefit, or deterministic outcome."
        ),
    ]
    if bundle.decision_brief is not None:
        _append_decision_brief(lines, bundle)
    lines.extend(["", "## Report findings"])
    for finding in bundle.extraction.molecular_findings:
        gene = finding.gene or "Alteration"
        page = finding.source_page if finding.source_page is not None else "unknown"
        lines.append(
            f"- {gene}: {finding.alteration} ({finding.alteration_type}); "
            f"source page {page}."
        )
    if bundle.phenotype:
        lines.extend(["", "## Biological axes"])
        for axis in bundle.phenotype.axes:
            lines.append(
                f"- {axis.label}: {axis.evidence_class}; "
                f"validation needed: {axis.validation_needed}."
            )
    if bundle.matrix:
        lines.extend(["", "## Molecular-fit review matrix"])
        for row in bundle.matrix.rows:
            lines.append(
                f"- Rank {row.rank}: {row.molecular_fit}. "
                f"Clinical use: {row.clinical_use}. "
                f"Why from omics: {row.why_from_omics}"
            )
    if bundle.confirmatory:
        lines.extend(["", "## Confirmatory testing questions"])
        for test in bundle.confirmatory.tests:
            lines.append(f"- {test.question} Evidence gap: {test.evidence_gap}")
    if bundle.tumor_behavior:
        lines.extend(["", "## Tumor-behavior hypothesis"])
        for state in bundle.tumor_behavior.state_evidence:
            lines.append(
                f"- State context {state.state_label}: "
                f"{state.evidence_class}; {state.uncertainty}"
            )
        for transition in bundle.tumor_behavior.transition_hypotheses:
            lines.append(
                f"- Transition hypothesis {transition.from_state} → "
                f"{transition.to_state}: {transition.rationale}"
            )
    lines.extend(["", "## Claims requiring review"])
    for claim in bundle.claims:
        lines.append(
            f"- [{claim.claim_class}] {claim.claim} "
            f"Status: {claim.validation_status}."
        )
    return ClinicalNarrativeCompilerOutput(
        artifact_id=artifact_id,
        markdown="\n".join(lines),
        source_artifact_ids=_source_artifact_ids(bundle),
        safety_note=(
            "Clinician decision-support only; no certain response, cure, "
            "survival benefit, or deterministic outcome is generated."
        ),
    )


def _append_decision_brief(lines: list[str], bundle: ClinicalArtifactBundle) -> None:
    brief = bundle.decision_brief
    if brief is None:
        return
    lines.extend(
        [
            "",
            "## Clinical decision summary",
            brief.clinical_decision_summary,
        ]
    )
    if brief.translational_assessment is not None:
        lines.extend(["", "## Five translational checks"])
        for question in _translational_questions(brief.translational_assessment):
            lines.append(
                f"- {question.question} {question.answer} "
                f"Status: {question.status}; evidence strength: {question.evidence_strength}."
            )
    lines.extend(["", "## Treatable biology"])
    for item in brief.actionable_biology:
        lines.append(
            f"- {item.biology} ({item.alteration_or_marker}): "
            f"{item.actionability}; {item.rationale}"
        )
    lines.extend(["", "## Ranked treatment options"])
    for option in brief.ranked_treatment_options:
        lines.append(
            f"- Rank {option.rank}: {option.therapy_name_or_class} "
            f"({option.clinical_use}). Why it fits: {option.why_it_fits}"
        )
    lines.extend(["", "## Treatment pressure and escape routes"])
    for row in brief.treatment_pressure_map:
        routes = ", ".join(row.likely_escape_routes)
        lines.append(
            f"- {row.therapy_name_or_class} targets {row.target_or_pathway}; "
            f"watch: {routes or 'not specified'}."
        )
    lines.extend(["", "## Biomarker watch list"])
    for item in brief.biomarker_watch_list:
        lines.append(
            f"- {item.biomarker}: {item.why_watch} "
            f"Preferred test: {item.preferred_test}; trigger: {item.trigger}."
        )
    lines.extend(["", "## Re-testing triggers"])
    for trigger in brief.retesting_triggers:
        lines.append(
            f"- {trigger.clinical_event}: {trigger.recommended_test}; "
            f"{trigger.rationale}"
        )
    lines.extend(["", "## Next test recommendations"])
    for test in brief.next_test_recommendations:
        lines.append(f"- {test.test_type} at {test.timing}: {test.rationale}")
    lines.extend(["", "## Evidence limitations"])
    for limitation in brief.evidence_limitations:
        lines.append(
            f"- {limitation.limitation}: {limitation.impact}; "
            f"needed resolution: {limitation.needed_resolution}"
        )




def _translational_questions(assessment) -> list[object]:
    return [
        assessment.target_relevance,
        assessment.biomarker_evidence,
        assessment.resistance_mechanisms,
        assessment.patient_population_alignment,
        assessment.evidence_resolution,
    ]

def _source_artifact_ids(bundle: ClinicalArtifactBundle) -> list[str]:
    ids = [bundle.extraction.artifact_id]
    artifacts = [
        bundle.entities,
        bundle.evidence_context,
        bundle.phenotype,
        bundle.matrix,
        bundle.sankey,
        bundle.confirmatory,
        bundle.tumor_behavior,
        bundle.decision_brief,
    ]
    for artifact in artifacts:
        if artifact is not None:
            ids.append(artifact.artifact_id)
    ids.extend(claim.claim_id for claim in bundle.claims)
    return ids
