from __future__ import annotations

from typing import Literal

from translume_schemas.base import TranslumeBaseModel


EvaluationSection = Literal[
    "extraction",
    "clinical_decision_summary",
    "current_tumor_state",
    "actionable_biology",
    "ranked_treatment_options",
    "treatment_pressure_map",
    "resistance_forecast",
    "biomarker_watch_list",
    "retesting_triggers",
    "next_test_recommendations",
    "evidence_limitations",
    "all",
]
EvaluationCategory = Literal[
    "report_finding",
    "treatment_option",
    "resistance_route",
    "biomarker",
    "test_modality",
    "clinical_event",
]
EvaluationSeverity = Literal["error", "warning"]


class ExpectedClinicalSignal(TranslumeBaseModel):
    """Expected clinical signal for decision-brief evaluation."""

    signal_id: str
    term: str
    category: EvaluationCategory
    aliases: list[str] = []
    sections: list[EvaluationSection] = ["all"]
    required: bool = True


class ForbiddenClinicalSignal(TranslumeBaseModel):
    """Clinical term that should not appear in the generated brief."""

    signal_id: str
    term: str
    aliases: list[str] = []
    reason: str
    severity: EvaluationSeverity = "error"


class DecisionBriefEvaluationThresholds(TranslumeBaseModel):
    """Pass/fail thresholds for deterministic decision-brief evaluation."""

    minimum_expected_signal_recall: float = 0.90
    minimum_evidence_coverage: float = 1.0
    minimum_clinical_usefulness: float = 0.80
    allow_forbidden_warnings: bool = True


class DecisionBriefEvaluationFixture(TranslumeBaseModel):
    """Fixture describing expected NGS decision-brief behavior."""

    fixture_id: str
    description: str
    tumor_type: str | None = None
    report_type: str = "NGS"
    expected_signals: list[ExpectedClinicalSignal]
    forbidden_signals: list[ForbiddenClinicalSignal] = []
    allowed_terms: list[str] = []
    thresholds: DecisionBriefEvaluationThresholds = (
        DecisionBriefEvaluationThresholds()
    )


class SignalEvaluationResult(TranslumeBaseModel):
    """Result for one expected or forbidden clinical signal."""

    signal_id: str
    term: str
    category: str
    matched: bool
    matched_sections: list[str]
    missing_sections: list[str] = []
    reason: str | None = None


class ForbiddenSignalHit(TranslumeBaseModel):
    """Forbidden term detected in a generated clinical artifact."""

    signal_id: str
    term: str
    matched_sections: list[str]
    reason: str
    severity: EvaluationSeverity


class UnsupportedCertaintyHit(TranslumeBaseModel):
    """Unsupported certainty phrase detected during evaluation."""

    phrase: str
    matched_sections: list[str]


class UngroundedDecisionRow(TranslumeBaseModel):
    """Decision row that lacks both provenance and unresolved evidence."""

    section: str
    row_index: int
    field_name: str
    summary: str


class DecisionBriefEvaluationMetrics(TranslumeBaseModel):
    """Numerical metrics for decision-brief quality gates."""

    expected_signal_recall: float
    evidence_coverage: float
    clinical_usefulness: float
    expected_signal_count: int
    matched_expected_signal_count: int
    grounded_row_count: int
    total_row_count: int
    populated_required_section_count: int
    required_section_count: int


class DecisionBriefEvaluationReport(TranslumeBaseModel):
    """Deterministic evaluation report for a decision brief or review packet."""

    fixture_id: str
    passed: bool
    metrics: DecisionBriefEvaluationMetrics
    expected_signal_results: list[SignalEvaluationResult]
    forbidden_signal_hits: list[ForbiddenSignalHit]
    unsupported_certainty_hits: list[UnsupportedCertaintyHit]
    ungrounded_rows: list[UngroundedDecisionRow]
    failure_reasons: list[str]
