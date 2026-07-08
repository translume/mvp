from __future__ import annotations

from typing import Literal

from translume_schemas.base import TranslumeBaseModel


ClinicalUse = Literal[
    "approved_option",
    "guideline_supported",
    "off_label_rationale",
    "trial_option",
    "avoid_or_deprioritize",
    "insufficient_evidence",
]
ConfidenceLabel = Literal["high", "moderate", "low", "needs_review"]
PriorityLabel = Literal["high", "medium", "low", "needs_review"]
AssessmentStatus = Literal[
    "supported",
    "partially_supported",
    "weak_or_incomplete",
    "unresolved",
    "needs_validation",
]
EvidenceStrength = Literal["strong", "moderate", "weak", "unresolved", "conflicting"]
TestModality = Literal[
    "ctDNA",
    "tissue_NGS",
    "IHC",
    "FISH",
    "RNA_fusion_testing",
    "pathology_review",
    "focused_biomarker_test",
    "other",
]
TranslationalQuestionKey = Literal[
    "target_relevance",
    "biomarker_evidence",
    "resistance_mechanisms",
    "patient_population_alignment",
    "evidence_resolution",
]
EvidenceSourceType = Literal[
    "report",
    "clinical_trial",
    "tool",
    "graph",
    "medea_hypothesis",
    "assay_limitation",
    "research_use_only",
    "unresolved",
]


class EvidenceSentence(TranslumeBaseModel):
    """Human-readable evidence atom used for clinician audit.

    Evidence sentences let the UI show labels such as "Report finding" or
    "Clinical trial criterion" while the backend preserves exact provenance.
    """

    evidence_id: str
    evidence_label: str
    statement: str
    source_type: EvidenceSourceType
    quote: str = ""
    source_artifact_ids: list[str] = []
    source_chunk_ids: list[str] = []
    source_page: int | None = None
    relevance: str = ""


class CurrentTumorState(TranslumeBaseModel):
    """Current molecular behavior summarized from the uploaded report."""

    dominant_drivers: list[str]
    active_pathways: list[str]
    co_drivers: list[str] = []
    actionable_alterations: list[str] = []
    resistance_or_uncertain_alterations: list[str] = []
    immune_and_repair_context: list[str] = []
    missing_data: list[str] = []
    source_artifact_ids: list[str]
    confidence: ConfidenceLabel = "needs_review"


class ActionableBiologyItem(TranslumeBaseModel):
    """One evidence-grounded actionable or non-actionable biology item."""

    biology: str
    alteration_or_marker: str
    actionability: ClinicalUse
    evidence_level: str
    rationale: str
    uncertainty: str
    source_artifact_ids: list[str]
    confidence: ConfidenceLabel = "needs_review"


class RankedTreatmentOption(TranslumeBaseModel):
    """Treatment option category with evidence and limitations."""

    rank: int
    therapy_name_or_class: str
    clinical_use: ClinicalUse
    therapy_class: str
    matched_biomarkers: list[str]
    why_it_fits: str
    evidence_level: str
    resistance_risks: list[str]
    required_before_use_tests: list[str]
    limitations: list[str]
    source_artifact_ids: list[str]
    unresolved_evidence: list[str] = []
    confidence: ConfidenceLabel = "needs_review"


class TreatmentPressureMapRow(TranslumeBaseModel):
    """How a therapy option pressures the current tumor biology."""

    therapy_name_or_class: str
    target_or_pathway: str
    why_it_fits: str
    selective_pressure: str
    likely_escape_routes: list[str]
    biomarkers_to_watch: list[str]
    evidence_basis: list[str]
    source_artifact_ids: list[str]
    unresolved_evidence: list[str] = []
    confidence: ConfidenceLabel = "needs_review"


class ResistanceForecastItem(TranslumeBaseModel):
    """Risk-ranked escape route, not a deterministic outcome prediction."""

    escape_route: Literal[
        "bypass_signaling",
        "secondary_resistance_mutation",
        "copy_number_evolution",
        "fusion_rearrangement_evolution",
        "dna_repair_restoration",
        "immune_escape",
        "histologic_transformation",
        "resistant_subclone_expansion",
        "other",
    ]
    description: str
    associated_treatment_pressure: str
    supporting_evidence: list[str]
    biomarkers_to_monitor: list[str]
    source_artifact_ids: list[str]
    unresolved_evidence: list[str] = []
    confidence: ConfidenceLabel = "needs_review"


class BiomarkerWatchItem(TranslumeBaseModel):
    """Biomarker, pathway, or clinical signal to monitor next."""

    biomarker: str
    alteration_type: str
    why_watch: str
    associated_treatment_pressure: str
    preferred_test: TestModality
    trigger: str
    priority: PriorityLabel
    source_artifact_ids: list[str]
    unresolved_evidence: list[str] = []


class RetestingTrigger(TranslumeBaseModel):
    """Event-based re-testing rule for the next oncology decision point."""

    clinical_event: str
    recommended_test: TestModality
    rationale: str
    what_result_changes: str
    urgency: PriorityLabel
    source_artifact_ids: list[str]
    unresolved_evidence: list[str] = []


class NextTestRecommendation(TranslumeBaseModel):
    """Most relevant next biomarker or molecular test recommendation."""

    test_type: TestModality
    timing: str
    rationale: str
    biomarkers_or_questions: list[str]
    result_that_would_change_management: str
    limitations: list[str]
    source_artifact_ids: list[str]
    unresolved_evidence: list[str] = []
    priority: PriorityLabel


class EvidenceLimitation(TranslumeBaseModel):
    """Explicit uncertainty, missing evidence, or review requirement."""

    limitation: str
    impact: str
    needed_resolution: str
    source_artifact_ids: list[str] = []


class TranslationalQuestionAssessment(TranslumeBaseModel):
    """Answer one clinical-translational question from staged evidence."""

    question_key: TranslationalQuestionKey
    question: str
    answer: str
    status: AssessmentStatus
    evidence_strength: EvidenceStrength
    supporting_evidence: list[str]
    unresolved_evidence: list[str] = []
    validation_next: list[str]
    evidence_labels: list[str] = []
    evidence_sentence_ids: list[str] = []
    source_artifact_ids: list[str]
    confidence: ConfidenceLabel = "needs_review"


class TranslationalAssessmentOutput(TranslumeBaseModel):
    """Five-question tumor-behavior intelligence assessment."""

    artifact_id: str
    target_relevance: TranslationalQuestionAssessment
    biomarker_evidence: TranslationalQuestionAssessment
    resistance_mechanisms: TranslationalQuestionAssessment
    patient_population_alignment: TranslationalQuestionAssessment
    evidence_resolution: TranslationalQuestionAssessment
    unresolved_evidence: list[str] = []


class CurrentTumorStateOutput(TranslumeBaseModel):
    """Structured-output wrapper for the current tumor state stage."""

    artifact_id: str
    current_tumor_state: CurrentTumorState
    unresolved_evidence: list[str] = []


class ActionableBiologyOutput(TranslumeBaseModel):
    """Structured-output wrapper for actionable biology."""

    artifact_id: str
    actionable_biology: list[ActionableBiologyItem]
    unresolved_evidence: list[str] = []


class RankedTreatmentOptionsOutput(TranslumeBaseModel):
    """Structured-output wrapper for ranked treatment options."""

    artifact_id: str
    ranked_treatment_options: list[RankedTreatmentOption]
    unresolved_evidence: list[str] = []


class TreatmentPressureMapOutput(TranslumeBaseModel):
    """Structured-output wrapper for treatment pressure mapping."""

    artifact_id: str
    treatment_pressure_map: list[TreatmentPressureMapRow]
    unresolved_evidence: list[str] = []


class ResistanceForecastOutput(TranslumeBaseModel):
    """Structured-output wrapper for resistance and escape forecasts."""

    artifact_id: str
    resistance_forecast: list[ResistanceForecastItem]
    unresolved_evidence: list[str] = []


class BiomarkerWatchListOutput(TranslumeBaseModel):
    """Structured-output wrapper for biomarker monitoring."""

    artifact_id: str
    biomarker_watch_list: list[BiomarkerWatchItem]
    unresolved_evidence: list[str] = []


class RetestingTriggersOutput(TranslumeBaseModel):
    """Structured-output wrapper for event-based re-testing triggers."""

    artifact_id: str
    retesting_triggers: list[RetestingTrigger]
    unresolved_evidence: list[str] = []


class NextTestRecommendationsOutput(TranslumeBaseModel):
    """Structured-output wrapper for next-test recommendations."""

    artifact_id: str
    next_test_recommendations: list[NextTestRecommendation]
    unresolved_evidence: list[str] = []


class TherapyEscapeSankeyPath(TranslumeBaseModel):
    """Explicit therapy-to-escape Sankey path for clinician reporting."""

    therapy_display_name: str
    therapy_source: str
    molecular_target_or_pathway: str
    target_driver_status: str
    predicted_behavior_state: str
    escape_pathway: str
    monitoring_timing: str
    evidence_sentence_ids: list[str] = []
    source_artifact_ids: list[str]
    unresolved_evidence: list[str] = []
    confidence: ConfidenceLabel = "needs_review"


class OncologistDecisionBrief(TranslumeBaseModel):
    """Primary clinician-facing Translume decision-support artifact."""

    artifact_id: str
    clinical_decision_summary: str
    current_tumor_state: CurrentTumorState
    actionable_biology: list[ActionableBiologyItem]
    ranked_treatment_options: list[RankedTreatmentOption]
    treatment_pressure_map: list[TreatmentPressureMapRow]
    resistance_forecast: list[ResistanceForecastItem]
    biomarker_watch_list: list[BiomarkerWatchItem]
    retesting_triggers: list[RetestingTrigger]
    next_test_recommendations: list[NextTestRecommendation]
    translational_assessment: TranslationalAssessmentOutput | None = None
    therapy_escape_sankey_paths: list[TherapyEscapeSankeyPath] = []
    evidence_sentence_map: list[EvidenceSentence] = []
    evidence_limitations: list[EvidenceLimitation]
    source_artifact_ids: list[str]
    source_chunk_ids: list[str]
    validation_status: Literal["needs_review"] = "needs_review"
