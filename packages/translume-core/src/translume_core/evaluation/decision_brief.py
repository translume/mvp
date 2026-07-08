from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Final

from translume_schemas.decision_brief import OncologistDecisionBrief
from translume_schemas.evaluation import (
    DecisionBriefEvaluationFixture,
    DecisionBriefEvaluationMetrics,
    DecisionBriefEvaluationReport,
    ForbiddenClinicalSignal,
    ForbiddenSignalHit,
    SignalEvaluationResult,
    UngroundedDecisionRow,
    UnsupportedCertaintyHit,
)
from translume_schemas.export import ReviewPacketExport


DECISION_BRIEF_UNSUPPORTED_CERTAINTY_PHRASES: Final[tuple[str, ...]] = (
    "will respond",
    "will be cured",
    "guaranteed",
    "definitive cure",
    "100%",
)
_REQUIRED_DECISION_SECTIONS: Final[tuple[str, ...]] = (
    "clinical_decision_summary",
    "current_tumor_state",
    "ranked_treatment_options",
    "treatment_pressure_map",
    "resistance_forecast",
    "biomarker_watch_list",
    "retesting_triggers",
    "next_test_recommendations",
    "translational_assessment",
)
_WORD_SEPARATOR_PATTERN: Final[re.Pattern[str]] = re.compile(r"[^a-z0-9]+")


def load_decision_brief_evaluation_fixture(
    data: Mapping[str, object],
) -> DecisionBriefEvaluationFixture:
    """Return a validated decision-brief evaluation fixture.

    Acceptance criteria:
        1. Determinism: Same mapping returns the same fixture model.
        2. No mutation: Caller-owned mapping is not modified.
        3. Validation: Pydantic rejects unknown or malformed fields.
        4. Utility: The fixture is ready for deterministic evaluation.

    Args:
        data: JSON-like fixture mapping.

    Returns:
        Validated evaluation fixture.
    """
    return DecisionBriefEvaluationFixture.model_validate(dict(data))


def evaluate_review_packet_against_fixture(
    *,
    packet: ReviewPacketExport,
    fixture: DecisionBriefEvaluationFixture,
) -> DecisionBriefEvaluationReport:
    """Evaluate a review packet's decision brief against an NGS fixture.

    Acceptance criteria:
        1. Requires a first-class decision brief in the packet.
        2. Includes extraction text when checking expected report findings.
        3. Applies the same row grounding and safety checks as brief-only eval.
        4. Returns a serializable evaluation report.
        5. Does not mutate the packet or fixture.

    Args:
        packet: Full Translume review packet.
        fixture: Expected clinical signals and thresholds.

    Returns:
        Deterministic evaluation report.

    Raises:
        ValueError: If the packet does not contain a decision brief.
    """
    brief = packet.bundle.decision_brief
    if brief is None:
        raise ValueError("ReviewPacketExport is missing bundle.decision_brief")
    return _evaluate_brief_sections_against_fixture(
        brief=brief,
        fixture=fixture,
        sections={
            **decision_brief_text_sections(brief),
            "extraction": _extraction_text_from_packet(packet),
        },
    )


def evaluate_decision_brief_against_fixture(
    *,
    brief: OncologistDecisionBrief,
    fixture: DecisionBriefEvaluationFixture,
) -> DecisionBriefEvaluationReport:
    """Evaluate a decision brief against an expected NGS behavior fixture.

    Acceptance criteria:
        1. Measures expected-signal recall across requested sections.
        2. Flags forbidden and unsupported-certainty terms.
        3. Measures row-level evidence or unresolved-evidence coverage.
        4. Measures whether required clinician-facing sections are populated.
        5. Returns pass/fail using fixture thresholds without side effects.

    Args:
        brief: Generated oncologist decision brief.
        fixture: Expected clinical signals and thresholds.

    Returns:
        Deterministic evaluation report.
    """
    return _evaluate_brief_sections_against_fixture(
        brief=brief,
        fixture=fixture,
        sections=decision_brief_text_sections(brief),
    )


def decision_brief_text_sections(
    brief: OncologistDecisionBrief,
) -> dict[str, str]:
    """Return searchable text by decision-brief section.

    Acceptance criteria:
        1. Determinism: Same brief returns the same section text.
        2. Coverage: Includes every clinician-facing decision section.
        3. Safety: Uses model fields only; does not infer extra facts.
        4. No mutation: The brief is read-only.

    Args:
        brief: Decision brief to index for evaluation.

    Returns:
        Mapping of section name to normalized-source text corpus.
    """
    sections = {
        "clinical_decision_summary": brief.clinical_decision_summary,
        "current_tumor_state": _join_nested_text(
            brief.current_tumor_state.model_dump(mode="json")
        ),
        "actionable_biology": _join_nested_text(
            [item.model_dump(mode="json") for item in brief.actionable_biology]
        ),
        "ranked_treatment_options": _join_nested_text(
            [
                item.model_dump(mode="json")
                for item in brief.ranked_treatment_options
            ]
        ),
        "treatment_pressure_map": _join_nested_text(
            [item.model_dump(mode="json") for item in brief.treatment_pressure_map]
        ),
        "resistance_forecast": _join_nested_text(
            [item.model_dump(mode="json") for item in brief.resistance_forecast]
        ),
        "biomarker_watch_list": _join_nested_text(
            [item.model_dump(mode="json") for item in brief.biomarker_watch_list]
        ),
        "retesting_triggers": _join_nested_text(
            [item.model_dump(mode="json") for item in brief.retesting_triggers]
        ),
        "next_test_recommendations": _join_nested_text(
            [
                item.model_dump(mode="json")
                for item in brief.next_test_recommendations
            ]
        ),
        "evidence_limitations": _join_nested_text(
            [item.model_dump(mode="json") for item in brief.evidence_limitations]
        ),
        "translational_assessment": (
            _join_nested_text(brief.translational_assessment.model_dump(mode="json"))
            if brief.translational_assessment is not None
            else ""
        ),
    }
    sections["all"] = "\n".join(sections.values())
    return sections


def _evaluate_brief_sections_against_fixture(
    *,
    brief: OncologistDecisionBrief,
    fixture: DecisionBriefEvaluationFixture,
    sections: Mapping[str, str],
) -> DecisionBriefEvaluationReport:
    expected_results = [
        _evaluate_expected_signal(sections, signal)
        for signal in fixture.expected_signals
    ]
    decision_sections = _decision_only_sections(sections)
    forbidden_hits = _forbidden_signal_hits(
        sections=decision_sections,
        forbidden_signals=fixture.forbidden_signals,
    )
    certainty_hits = _unsupported_certainty_hits(decision_sections)
    ungrounded_rows = _ungrounded_decision_rows(brief)
    metrics = _evaluation_metrics(
        brief=brief,
        expected_results=expected_results,
        ungrounded_rows=ungrounded_rows,
    )
    failure_reasons = _failure_reasons(
        fixture=fixture,
        metrics=metrics,
        expected_results=expected_results,
        forbidden_hits=forbidden_hits,
        certainty_hits=certainty_hits,
        ungrounded_rows=ungrounded_rows,
    )
    return DecisionBriefEvaluationReport(
        fixture_id=fixture.fixture_id,
        passed=not failure_reasons,
        metrics=metrics,
        expected_signal_results=expected_results,
        forbidden_signal_hits=forbidden_hits,
        unsupported_certainty_hits=certainty_hits,
        ungrounded_rows=ungrounded_rows,
        failure_reasons=failure_reasons,
    )


def _evaluate_expected_signal(
    sections: Mapping[str, str],
    signal: object,
) -> SignalEvaluationResult:
    requested_sections = _available_requested_sections(
        requested=_requested_sections(signal.sections),
        available=sections,
    )
    matched_sections = [
        section
        for section in requested_sections
        if _any_term_in_text(_signal_terms(signal.term, signal.aliases), sections.get(section, ""))
    ]
    missing_sections = [
        section for section in requested_sections if section not in matched_sections
    ]
    return SignalEvaluationResult(
        signal_id=signal.signal_id,
        term=signal.term,
        category=signal.category,
        matched=bool(matched_sections),
        matched_sections=matched_sections,
        missing_sections=missing_sections if signal.required else [],
        reason=None if matched_sections else "expected signal was not found",
    )




def _decision_only_sections(sections: Mapping[str, str]) -> dict[str, str]:
    return {
        section: text
        for section, text in sections.items()
        if section != "extraction"
    }


def _available_requested_sections(
    *,
    requested: Sequence[str],
    available: Mapping[str, str],
) -> list[str]:
    selected = [section for section in requested if section in available]
    if selected:
        return selected
    return ["all"]

def _forbidden_signal_hits(
    *,
    sections: Mapping[str, str],
    forbidden_signals: Sequence[ForbiddenClinicalSignal],
) -> list[ForbiddenSignalHit]:
    return [
        ForbiddenSignalHit(
            signal_id=signal.signal_id,
            term=signal.term,
            matched_sections=matched_sections,
            reason=signal.reason,
            severity=signal.severity,
        )
        for signal in forbidden_signals
        for matched_sections in [
            _sections_matching_terms(
                sections=sections,
                terms=_signal_terms(signal.term, signal.aliases),
            )
        ]
        if matched_sections
    ]


def _unsupported_certainty_hits(
    sections: Mapping[str, str],
) -> list[UnsupportedCertaintyHit]:
    return [
        UnsupportedCertaintyHit(phrase=phrase, matched_sections=matched_sections)
        for phrase in DECISION_BRIEF_UNSUPPORTED_CERTAINTY_PHRASES
        for matched_sections in [
            _sections_matching_terms(sections=sections, terms=[phrase])
        ]
        if matched_sections
    ]


def _sections_matching_terms(
    *,
    sections: Mapping[str, str],
    terms: Sequence[str],
) -> list[str]:
    return [
        section
        for section, text in sections.items()
        if section != "all" and _any_term_in_text(terms, text)
    ]


def _evaluation_metrics(
    *,
    brief: OncologistDecisionBrief,
    expected_results: Sequence[SignalEvaluationResult],
    ungrounded_rows: Sequence[UngroundedDecisionRow],
) -> DecisionBriefEvaluationMetrics:
    expected_count = len(expected_results)
    matched_count = sum(1 for item in expected_results if item.matched)
    total_rows = _decision_row_count(brief)
    grounded_rows = max(total_rows - len(ungrounded_rows), 0)
    populated_required_sections = _populated_required_section_count(brief)
    required_section_count = len(_REQUIRED_DECISION_SECTIONS)
    return DecisionBriefEvaluationMetrics(
        expected_signal_recall=_safe_ratio(matched_count, expected_count),
        evidence_coverage=_safe_ratio(grounded_rows, total_rows),
        clinical_usefulness=_safe_ratio(
            populated_required_sections,
            required_section_count,
        ),
        expected_signal_count=expected_count,
        matched_expected_signal_count=matched_count,
        grounded_row_count=grounded_rows,
        total_row_count=total_rows,
        populated_required_section_count=populated_required_sections,
        required_section_count=required_section_count,
    )


def _failure_reasons(
    *,
    fixture: DecisionBriefEvaluationFixture,
    metrics: DecisionBriefEvaluationMetrics,
    expected_results: Sequence[SignalEvaluationResult],
    forbidden_hits: Sequence[ForbiddenSignalHit],
    certainty_hits: Sequence[UnsupportedCertaintyHit],
    ungrounded_rows: Sequence[UngroundedDecisionRow],
) -> list[str]:
    threshold_failures = _threshold_failure_reasons(fixture, metrics)
    missing_required = [
        f"missing required signal {item.signal_id}: {item.term}"
        for item in expected_results
        if item.missing_sections
    ]
    forbidden_errors = [
        f"forbidden signal {item.signal_id}: {item.term}"
        for item in forbidden_hits
        if item.severity == "error"
        or not fixture.thresholds.allow_forbidden_warnings
    ]
    certainty_errors = [
        f"unsupported certainty phrase: {item.phrase}"
        for item in certainty_hits
    ]
    row_errors = [
        f"ungrounded row {item.section}[{item.row_index}]"
        for item in ungrounded_rows
    ]
    return [
        *threshold_failures,
        *missing_required,
        *forbidden_errors,
        *certainty_errors,
        *row_errors,
    ]


def _threshold_failure_reasons(
    fixture: DecisionBriefEvaluationFixture,
    metrics: DecisionBriefEvaluationMetrics,
) -> list[str]:
    thresholds = fixture.thresholds
    checks = [
        (
            metrics.expected_signal_recall,
            thresholds.minimum_expected_signal_recall,
            "expected signal recall",
        ),
        (
            metrics.evidence_coverage,
            thresholds.minimum_evidence_coverage,
            "evidence coverage",
        ),
        (
            metrics.clinical_usefulness,
            thresholds.minimum_clinical_usefulness,
            "clinical usefulness",
        ),
    ]
    return [
        f"{label} {actual:.3f} below threshold {minimum:.3f}"
        for actual, minimum, label in checks
        if actual < minimum
    ]


def _ungrounded_decision_rows(
    brief: OncologistDecisionBrief,
) -> list[UngroundedDecisionRow]:
    row_groups = [
        ("ranked_treatment_options", brief.ranked_treatment_options),
        ("treatment_pressure_map", brief.treatment_pressure_map),
        ("resistance_forecast", brief.resistance_forecast),
        ("biomarker_watch_list", brief.biomarker_watch_list),
        ("retesting_triggers", brief.retesting_triggers),
        ("next_test_recommendations", brief.next_test_recommendations),
    ]
    return [
        UngroundedDecisionRow(
            section=section,
            row_index=index,
            field_name="source_artifact_ids",
            summary=_row_summary(row),
        )
        for section, rows in row_groups
        for index, row in enumerate(rows)
        if not _row_has_evidence_or_unresolved(row)
    ]


def _row_has_evidence_or_unresolved(row: object) -> bool:
    source_ids = getattr(row, "source_artifact_ids", [])
    unresolved = getattr(row, "unresolved_evidence", [])
    return _has_text(source_ids) or _has_text(unresolved)


def _row_summary(row: object) -> str:
    dumped = row.model_dump(mode="json") if hasattr(row, "model_dump") else row
    if isinstance(dumped, Mapping):
        for key in (
            "therapy_name_or_class",
            "description",
            "biomarker",
            "clinical_event",
            "test_type",
            "target_or_pathway",
        ):
            value = dumped.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return _join_nested_text(dumped)[:120]


def _decision_row_count(brief: OncologistDecisionBrief) -> int:
    return sum(
        len(rows)
        for rows in (
            brief.ranked_treatment_options,
            brief.treatment_pressure_map,
            brief.resistance_forecast,
            brief.biomarker_watch_list,
            brief.retesting_triggers,
            brief.next_test_recommendations,
        )
    )


def _populated_required_section_count(brief: OncologistDecisionBrief) -> int:
    sections = decision_brief_text_sections(brief)
    return sum(
        1
        for section in _REQUIRED_DECISION_SECTIONS
        if sections.get(section, "").strip()
    )


def _extraction_text_from_packet(packet: ReviewPacketExport) -> str:
    extraction = packet.bundle.extraction
    findings = [
        " ".join(
            value
            for value in (
                finding.gene or "",
                finding.alteration,
                finding.alteration_type,
                finding.source_text or "",
            )
            if value.strip()
        )
        for finding in extraction.molecular_findings
    ]
    return _join_nested_text(
        {
            "report_type": extraction.report_type,
            "disease": extraction.disease,
            "specimen": extraction.specimen,
            "tumor_percentage": extraction.tumor_percentage,
            "molecular_findings": findings,
            "negative_findings": extraction.negative_findings,
            "assay_limitations": extraction.assay_limitations,
        }
    )


def _requested_sections(sections: Sequence[str]) -> list[str]:
    if not sections:
        return ["all"]
    return list(dict.fromkeys(section for section in sections if section.strip()))


def _signal_terms(term: str, aliases: Sequence[str]) -> list[str]:
    return [value for value in [term, *aliases] if value.strip()]


def _any_term_in_text(terms: Sequence[str], text: str) -> bool:
    normalized_text = _normalize_for_match(text)
    return any(_normalize_for_match(term) in normalized_text for term in terms)


def _normalize_for_match(value: str) -> str:
    return _WORD_SEPARATOR_PATTERN.sub(" ", value.casefold()).strip()


def _join_nested_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        return " ".join(_join_nested_text(item) for item in value.values())
    if isinstance(value, Iterable):
        return " ".join(_join_nested_text(item) for item in value)
    return str(value)


def _has_text(values: Sequence[str]) -> bool:
    return any(str(value).strip() for value in values)


def _safe_ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 1.0
    return numerator / denominator
