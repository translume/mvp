from __future__ import annotations

from uuid import uuid5, NAMESPACE_URL

from translume_schemas.evidence import EvidenceContextBundle
from translume_schemas.tumor_behavior import (
    STATE_LABELS,
    TransitionHypothesis,
    TumorBehaviorModelOutput,
    TumorStateEvidence,
)


def generate_tumor_behavior_model_from_context(
    context: EvidenceContextBundle,
) -> TumorBehaviorModelOutput:
    """Build a hypothesis-generating tumor behavior model.

    Acceptance criteria:
        1. Every state has supporting evidence or explicit missing evidence.
        2. Every transition has from_state and to_state.
        3. Every transition references supporting artifacts.
        4. Every transition is marked hypothesis-generating.
        5. No transition probability or outcome prediction is generated.
        6. Function is deterministic and pure.

    Args:
        context: Combined evidence context.

    Returns:
        Tumor behavior model output.
    """
    finding_ids = [finding.finding_id for finding in context.extraction.molecular_findings]
    state_evidence = [
        TumorStateEvidence(
            state_label="proliferative",
            supporting_findings=finding_ids,
            graph_support=[edge.edge_id for edge in context.graph_evidence.edges],
            tool_support=[tool.artifact_id for tool in context.tool_outputs],
            medea_support=[context.medea_reasoning.artifact_id],
            evidence_class="hypothesis_generating",
            uncertainty="state is inferred from structured evidence context and requires review",
            validation_needed=True,
        )
    ]
    transitions = [
        TransitionHypothesis(
            from_state="proliferative",
            to_state="stress_adapted_survival",
            rationale="Structured findings and enrichment context suggest a reviewable adaptive-stress hypothesis; no probability is assigned.",
            supporting_artifacts=[
                context.extraction.artifact_id,
                context.graph_evidence.artifact_id,
                context.medea_reasoning.artifact_id,
            ],
            confidence_label="requires_validation",
            validation_status="needs_review",
        )
    ]
    missing_states = [state for state in STATE_LABELS if state not in {"proliferative"}]
    artifact_id = f"artifact_{uuid5(NAMESPACE_URL, f'{context.artifact_id}:tumor_behavior').hex[:16]}"
    return TumorBehaviorModelOutput(
        artifact_id=artifact_id,
        state_evidence=state_evidence,
        transition_hypotheses=transitions,
        limitations=[
            "Hypothesis-generating only; not an outcome prediction.",
            "No transition probabilities are produced in the MVP.",
            f"No direct evidence generated for states: {', '.join(missing_states)}.",
        ],
    )
