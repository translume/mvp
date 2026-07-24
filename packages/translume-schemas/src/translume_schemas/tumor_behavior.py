from __future__ import annotations

from translume_schemas.base import TranslumeBaseModel


STATE_LABELS = [
    "driver_dependency",
    "bypass_signaling_risk",
    "secondary_resistance_mutation_risk",
    "copy_number_evolution_risk",
    "fusion_rearrangement_risk",
    "dna_repair_restoration_risk",
    "immune_escape_risk",
    "histologic_transformation_risk",
    "resistant_subclone_expansion_risk",
    "proliferative",
    "stress_adapted_survival",
    "plastic_dedifferentiated",
    "dormant_quiescent",
    "apoptotic_eliminated",
]


class TumorStateEvidence(TranslumeBaseModel):
    state_label: str
    supporting_findings: list[str]
    graph_support: list[str] = []
    tool_support: list[str] = []
    medea_support: list[str] = []
    evidence_class: str
    uncertainty: str
    validation_needed: bool


class TransitionHypothesis(TranslumeBaseModel):
    from_state: str
    to_state: str
    rationale: str
    supporting_artifacts: list[str]
    confidence_label: str
    validation_status: str
    hypothesis_generating: bool = True


class TumorBehaviorModelOutput(TranslumeBaseModel):
    artifact_id: str
    state_evidence: list[TumorStateEvidence]
    transition_hypotheses: list[TransitionHypothesis]
    limitations: list[str] = []
