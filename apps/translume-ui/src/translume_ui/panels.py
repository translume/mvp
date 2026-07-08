from __future__ import annotations

import html
import json
from dataclasses import dataclass
from typing import Any

import plotly.graph_objects as go

from translume_schemas.export import ReviewPacketExport


class ClinicalPanelRenderError(ValueError):
    """Raised when an API packet cannot be rendered safely as clinical panels."""


REQUIRED_BUNDLE_ARTIFACTS = (
    "entities",
    "evidence_context",
    "phenotype",
    "matrix",
    "sankey",
    "confirmatory",
    "tumor_behavior",
    "decision_brief",
    "narrative",
    "narrative_containment",
)

NODE_KIND_COLORS = {
    "finding": "#6d28d9",
    "report_finding": "#6d28d9",
    "mechanism": "#4f46e5",
    "pathway": "#2563eb",
    "molecular_fit": "#0891b2",
    "validation": "#0d9488",
    "validation_test": "#0d9488",
    "therapy_or_drug": "#0891b2",
    "molecular_target": "#2563eb",
    "predicted_disease_state": "#7c3aed",
    "escape_or_recombination_pathway": "#dc2626",
    "when_to_watch": "#0f766e",
}
DEFAULT_NODE_COLOR = "#64748b"


@dataclass(frozen=True)
class ClinicalPanelData:
    """Pure UI projection of one persisted ``ReviewPacketExport``."""

    status_markdown: str
    case_summary_html: str
    decision_snapshot_html: str
    decision_summary_markdown: str
    translational_check_rows: list[list[Any]]
    evidence_sentence_rows: list[list[Any]]
    actionable_biology_rows: list[list[Any]]
    ranked_treatment_option_rows: list[list[Any]]
    treatment_pressure_rows: list[list[Any]]
    resistance_forecast_rows: list[list[Any]]
    biomarker_watch_rows: list[list[Any]]
    retesting_trigger_rows: list[list[Any]]
    next_test_rows: list[list[Any]]
    decision_limitations_rows: list[list[Any]]
    findings_rows: list[list[Any]]
    entity_rows: list[list[Any]]
    phenotype_rows: list[list[Any]]
    matrix_rows: list[list[Any]]
    sankey_figure: go.Figure
    confirmatory_rows: list[list[Any]]
    tumor_state_rows: list[list[Any]]
    transition_rows: list[list[Any]]
    graph_node_rows: list[list[Any]]
    graph_edge_rows: list[list[Any]]
    tool_run_rows: list[list[Any]]
    tool_evidence_rows: list[list[Any]]
    medea_markdown: str
    evidence_gaps_markdown: str
    narrative_markdown: str
    containment_markdown: str
    claim_rows: list[list[Any]]
    claim_choices: list[str]
    validation_rows: list[list[Any]]
    provenance_rows: list[list[Any]]
    ledger_rows: list[list[Any]]
    raw_json: str


def build_clinical_panel_data(packet: ReviewPacketExport) -> ClinicalPanelData:
    """Project a persisted packet into clinician-facing panels.

    The function performs no network or storage I/O. It never invents clinical
    content; all rows, summaries, and visual links originate from the validated
    API packet.
    """
    require_renderable_review_packet(packet)
    return ClinicalPanelData(
        status_markdown=_status_markdown(packet),
        case_summary_html=_case_summary_html(packet),
        decision_snapshot_html=_decision_snapshot_html(packet),
        decision_summary_markdown=_decision_summary_markdown(packet),
        translational_check_rows=_translational_check_rows(packet),
        evidence_sentence_rows=_evidence_sentence_rows(packet),
        actionable_biology_rows=_actionable_biology_rows(packet),
        ranked_treatment_option_rows=_ranked_treatment_option_rows(packet),
        treatment_pressure_rows=_treatment_pressure_rows(packet),
        resistance_forecast_rows=_resistance_forecast_rows(packet),
        biomarker_watch_rows=_biomarker_watch_rows(packet),
        retesting_trigger_rows=_retesting_trigger_rows(packet),
        next_test_rows=_next_test_rows(packet),
        decision_limitations_rows=_decision_limitations_rows(packet),
        findings_rows=_finding_rows(packet),
        entity_rows=_entity_rows(packet),
        phenotype_rows=_phenotype_rows(packet),
        matrix_rows=_matrix_rows(packet),
        sankey_figure=build_mechanism_sankey_figure(packet),
        confirmatory_rows=_confirmatory_rows(packet),
        tumor_state_rows=_tumor_state_rows(packet),
        transition_rows=_transition_rows(packet),
        graph_node_rows=_graph_node_rows(packet),
        graph_edge_rows=_graph_edge_rows(packet),
        tool_run_rows=_tool_run_rows(packet),
        tool_evidence_rows=_tool_evidence_rows(packet),
        medea_markdown=_medea_markdown(packet),
        evidence_gaps_markdown=_evidence_gaps_markdown(packet),
        narrative_markdown=_narrative_markdown(packet),
        containment_markdown=_containment_markdown(packet),
        claim_rows=_claim_rows(packet),
        claim_choices=[claim.claim_id for claim in packet.bundle.claims],
        validation_rows=_validation_rows(packet),
        provenance_rows=_provenance_rows(packet),
        ledger_rows=_ledger_rows(packet),
        raw_json=json.dumps(packet.model_dump(mode="json"), indent=2),
    )


def require_renderable_review_packet(packet: ReviewPacketExport) -> None:
    """Fail if required persisted artifacts are missing or containment failed."""
    missing = [
        artifact_name
        for artifact_name in REQUIRED_BUNDLE_ARTIFACTS
        if getattr(packet.bundle, artifact_name) is None
    ]
    if missing:
        raise ClinicalPanelRenderError(
            "Persisted review packet is missing required artifacts: "
            + ", ".join(sorted(missing))
        )
    containment = packet.bundle.narrative_containment
    if containment is None or not containment.passed:
        raise ClinicalPanelRenderError(
            "Narrative containment did not pass; clinician-facing narrative rendering is blocked"
        )
    if not packet.bundle.provenance:
        raise ClinicalPanelRenderError(
            "Persisted review packet has no artifact provenance; rendering is blocked"
        )


def build_mechanism_sankey_figure(packet: ReviewPacketExport) -> go.Figure:
    """Build therapy → target biology → disease state → escape pathway flow.

    The old artifact-level Sankey is intentionally not rendered in the report UI.
    This figure is derived from the persisted decision brief so it tells the
    clinical story: which therapy class hits which target/pathway, how that
    connects to the tumor state, and which escape/recombination paths need
    monitoring.
    """
    sankey = packet.bundle.sankey
    brief = packet.bundle.decision_brief
    if brief is None:
        raise ClinicalPanelRenderError("OncologistDecisionBrief is unavailable")
    if brief.translational_assessment is None and sankey is not None:
        _validate_legacy_sankey_references(sankey)
        return _legacy_mechanism_sankey_figure(sankey)
    if brief.therapy_escape_sankey_paths:
        return _therapy_escape_path_sankey_figure(brief.therapy_escape_sankey_paths)
    if not brief.treatment_pressure_map and not brief.resistance_forecast:
        return _empty_figure("No therapy-to-escape pathway flow was surfaced.")

    labels: list[str] = []
    kinds: list[str] = []
    index_by_key: dict[tuple[str, str], int] = {}

    def node(kind: str, label: str) -> int:
        clean = label.strip() or "Not resolved"
        key = (kind, clean.casefold())
        if key not in index_by_key:
            index_by_key[key] = len(labels)
            labels.append(clean)
            kinds.append(kind)
        return index_by_key[key]

    disease_state_label = _joined_or_fallback(
        [
            *brief.current_tumor_state.dominant_drivers,
            *brief.current_tumor_state.active_pathways,
        ],
        fallback="Tumor behavior state requires review",
    )
    disease_state_index = node("predicted_disease_state", disease_state_label)
    source_indexes: list[int] = []
    target_indexes: list[int] = []
    values: list[float] = []
    customdata: list[list[str]] = []

    for row in brief.treatment_pressure_map:
        therapy_index = node("therapy_or_drug", row.therapy_name_or_class)
        target_index = node("molecular_target", row.target_or_pathway)
        width = _confidence_width(row.confidence)
        _add_sankey_link(
            source_indexes,
            target_indexes,
            values,
            customdata,
            therapy_index,
            target_index,
            width,
            "therapy/drug → molecular target",
            row.why_it_fits,
        )
        _add_sankey_link(
            source_indexes,
            target_indexes,
            values,
            customdata,
            target_index,
            disease_state_index,
            width,
            "target biology → tumor behavior",
            row.selective_pressure,
        )
        for route in row.likely_escape_routes:
            escape_index = node("escape_or_recombination_pathway", route)
            _add_sankey_link(
                source_indexes,
                target_indexes,
                values,
                customdata,
                disease_state_index,
                escape_index,
                max(width * 0.85, 0.5),
                "tumor behavior → possible escape/recombination pathway",
                "Monitor after treatment pressure or at progression.",
            )

    for forecast in brief.resistance_forecast:
        escape_index = node("escape_or_recombination_pathway", forecast.escape_route)
        timing_label = _escape_timing_label(forecast.associated_treatment_pressure)
        timing_index = node("when_to_watch", timing_label)
        _add_sankey_link(
            source_indexes,
            target_indexes,
            values,
            customdata,
            disease_state_index,
            escape_index,
            _confidence_width(forecast.confidence),
            "tumor behavior → forecast escape route",
            forecast.description,
        )
        _add_sankey_link(
            source_indexes,
            target_indexes,
            values,
            customdata,
            escape_index,
            timing_index,
            _confidence_width(forecast.confidence),
            "escape route → when to watch",
            _joined_or_fallback(
                forecast.biomarkers_to_monitor,
                fallback="biomarker watch item requires review",
            ),
        )

    figure = go.Figure(
        data=[
            go.Sankey(
                arrangement="snap",
                node={
                    "label": labels,
                    "color": [
                        NODE_KIND_COLORS.get(kind.casefold(), DEFAULT_NODE_COLOR)
                        for kind in kinds
                    ],
                    "customdata": [[_humanize(kind)] for kind in kinds],
                    "hovertemplate": "%{label}<br>%{customdata[0]}<extra></extra>",
                    "pad": 24,
                    "thickness": 18,
                    "line": {"color": "#dbe4ef", "width": 1},
                },
                link={
                    "source": source_indexes,
                    "target": target_indexes,
                    "value": values,
                    "color": "rgba(79, 70, 229, 0.24)",
                    "customdata": customdata,
                    "hovertemplate": (
                        "%{customdata[0]}<br>%{customdata[1]}"
                        "<br>Relative evidence weight: %{value}<extra></extra>"
                    ),
                },
            )
        ]
    )
    figure.update_layout(
        title={
            "text": (
                "Therapy → Target biology → Tumor behavior → Escape / recombination pathway"
                "<br><sup>Widths reflect evidence confidence in the staged brief, not calibrated probability.</sup>"
            ),
            "x": 0.01,
            "xanchor": "left",
        },
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        font={"family": "Avenir Next, Segoe UI, sans-serif", "color": "#172033"},
        margin={"l": 20, "r": 20, "t": 92, "b": 20},
        height=max(460, 60 * len(labels)),
    )
    return figure






def _legacy_mechanism_sankey_figure(sankey: Any) -> go.Figure:
    """Render legacy Sankey packets while new packets use therapy-to-escape flow."""
    if not sankey.nodes:
        return _empty_figure("No case-supported mechanism nodes were returned.")
    index_by_node_id = {node.node_id: index for index, node in enumerate(sankey.nodes)}
    source_indexes = [index_by_node_id[link.source_node_id] for link in sankey.links]
    target_indexes = [index_by_node_id[link.target_node_id] for link in sankey.links]
    values = [link.value for link in sankey.links]
    figure = go.Figure(
        data=[
            go.Sankey(
                arrangement="snap",
                node={
                    "label": [node.label for node in sankey.nodes],
                    "color": [
                        NODE_KIND_COLORS.get(node.kind.casefold(), DEFAULT_NODE_COLOR)
                        for node in sankey.nodes
                    ],
                    "customdata": [[_humanize(node.kind), node.evidence_class] for node in sankey.nodes],
                    "hovertemplate": "%{label}<br>%{customdata[0]}<br>Evidence: %{customdata[1]}<extra></extra>",
                    "pad": 22,
                    "thickness": 18,
                    "line": {"color": "#dbe4ef", "width": 1},
                },
                link={
                    "source": source_indexes,
                    "target": target_indexes,
                    "value": values,
                    "color": "rgba(79, 70, 229, 0.24)",
                    "hovertemplate": "Legacy mechanism link<br>Relative value: %{value}<extra></extra>",
                },
            )
        ]
    )
    figure.update_layout(
        title={
            "text": "Mechanism Sankey: source-backed biological interpretation",
            "x": 0.01,
            "xanchor": "left",
        },
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        font={"family": "Avenir Next, Segoe UI, sans-serif", "color": "#172033"},
        margin={"l": 20, "r": 20, "t": 82, "b": 20},
        height=max(420, 64 * len(sankey.nodes)),
    )
    return figure

def _validate_legacy_sankey_references(sankey: Any) -> None:
    index_by_node_id = {node.node_id for node in sankey.nodes}
    if len(index_by_node_id) != len(sankey.nodes):
        raise ClinicalPanelRenderError("Mechanism Sankey contains duplicate node IDs")
    for link in sankey.links:
        if link.source_node_id not in index_by_node_id:
            raise ClinicalPanelRenderError(
                f"Sankey link references unknown source node: {link.source_node_id}"
            )
        if link.target_node_id not in index_by_node_id:
            raise ClinicalPanelRenderError(
                f"Sankey link references unknown target node: {link.target_node_id}"
            )
        if link.value <= 0:
            raise ClinicalPanelRenderError(
                "Sankey link values must be positive; zero/negative widths cannot be rendered"
            )

def _add_sankey_link(
    source_indexes: list[int],
    target_indexes: list[int],
    values: list[float],
    customdata: list[list[str]],
    source: int,
    target: int,
    value: float,
    link_type: str,
    rationale: str,
) -> None:
    if source == target:
        return
    source_indexes.append(source)
    target_indexes.append(target)
    values.append(max(value, 0.5))
    customdata.append([link_type, rationale.strip() or "Requires clinician review."])


def _confidence_width(confidence: str) -> float:
    return {
        "high": 4.0,
        "moderate": 3.0,
        "low": 2.0,
        "needs_review": 1.0,
    }.get(confidence, 1.0)


def _escape_timing_label(pressure: str) -> str:
    clean = pressure.strip()
    if not clean:
        return "Watch at progression or therapy switch"
    return f"Watch after {clean}"

def _status_markdown(packet: ReviewPacketExport) -> str:
    statuses = [claim.validation_status for claim in packet.bundle.claims]
    validated = statuses.count("validated")
    rejected = statuses.count("rejected")
    needs_review = statuses.count("needs_review")
    return (
        '<div class="translume-status">'
        "Translume tumor-behavior report loaded. "
        f"Evidence claims: {validated} validated, {rejected} rejected, {needs_review} need review."
        "</div>"
    )


def _case_summary_html(packet: ReviewPacketExport) -> str:
    extraction = packet.bundle.extraction
    summary_items = [
        ("Report type", extraction.report_type),
        ("Disease context", extraction.disease or "Not stated in report"),
        ("Specimen", extraction.specimen or "Not stated in report"),
        ("Tumor percentage", extraction.tumor_percentage or "Not stated in report"),
        ("Molecular findings", str(len(extraction.molecular_findings))),
    ]
    grid = "".join(
        (
            '<div class="translume-summary-item">'
            f'<span class="translume-summary-label">{html.escape(label)}</span>'
            f'<span class="translume-summary-value">{html.escape(value)}</span>'
            "</div>"
        )
        for label, value in summary_items
    )
    negatives = _html_list("Report negative findings", extraction.negative_findings)
    limitations = _html_list("Report limitations", extraction.assay_limitations)
    return (
        f'<div class="translume-summary-grid">{grid}</div>'
        f"{negatives}{limitations}"
        '<div class="translume-safety-note">'
        "This output is clinician decision-support and requires oncology review. "
        "It does not claim certain response, cure, survival benefit, or deterministic outcome."
        "</div>"
    )





def _therapy_escape_path_sankey_figure(paths: Sequence[Any]) -> go.Figure:
    """Render explicit therapy → target → behavior → escape → timing paths."""
    labels: list[str] = []
    kinds: list[str] = []
    index_by_key: dict[tuple[str, str], int] = {}

    def node(kind: str, label: str) -> int:
        clean = str(label).strip() or "Not resolved"
        key = (kind, clean.casefold())
        if key not in index_by_key:
            index_by_key[key] = len(labels)
            labels.append(clean)
            kinds.append(kind)
        return index_by_key[key]

    source_indexes: list[int] = []
    target_indexes: list[int] = []
    values: list[float] = []
    customdata: list[list[str]] = []
    for path in paths:
        therapy_index = node("therapy_or_drug", path.therapy_display_name)
        target_index = node("molecular_target", path.molecular_target_or_pathway)
        state_index = node("predicted_disease_state", path.predicted_behavior_state)
        escape_index = node("escape_or_recombination_pathway", path.escape_pathway)
        timing_index = node("when_to_watch", path.monitoring_timing)
        width = _confidence_width(path.confidence)
        _add_sankey_link(
            source_indexes,
            target_indexes,
            values,
            customdata,
            therapy_index,
            target_index,
            width,
            "therapy/drug → molecular target",
            path.target_driver_status,
        )
        _add_sankey_link(
            source_indexes,
            target_indexes,
            values,
            customdata,
            target_index,
            state_index,
            width,
            "target biology → predicted disease state",
            path.target_driver_status,
        )
        _add_sankey_link(
            source_indexes,
            target_indexes,
            values,
            customdata,
            state_index,
            escape_index,
            width,
            "predicted disease state → recombination/escape pathway",
            path.escape_pathway,
        )
        _add_sankey_link(
            source_indexes,
            target_indexes,
            values,
            customdata,
            escape_index,
            timing_index,
            width,
            "escape pathway → when to monitor",
            path.monitoring_timing,
        )
    if not source_indexes:
        return _empty_figure("No therapy-to-escape pathway flow was surfaced.")
    return go.Figure(
        data=[
            go.Sankey(
                arrangement="snap",
                node={
                    "label": labels,
                    "color": [NODE_KIND_COLORS.get(kind, DEFAULT_NODE_COLOR) for kind in kinds],
                    "pad": 18,
                    "thickness": 16,
                },
                link={
                    "source": source_indexes,
                    "target": target_indexes,
                    "value": values,
                    "customdata": customdata,
                    "hovertemplate": "%{customdata[0]}<br>%{customdata[1]}<extra></extra>",
                },
            )
        ],
        layout={
            "title": "Therapy/drug → target biology → predicted disease state → recombination/escape pathway → monitoring timing",
            "font": {"size": 12},
            "margin": {"l": 10, "r": 10, "t": 50, "b": 10},
        },
    )


def _decision_snapshot_html(packet: ReviewPacketExport) -> str:
    """Render the five MVP translational questions as the top report view."""
    brief = packet.bundle.decision_brief
    assert brief is not None
    assessment = brief.translational_assessment
    if assessment is not None:
        top_treatment = _top_ranked_treatment(packet)
        cards = [
            _decision_card("Treat now", _treatment_snapshot_value(top_treatment)),
            *(
                _decision_card(
                    _short_question_label(item.question_key),
                    f"{item.status}: {item.answer}",
                )
                for item in _assessment_questions(assessment)
            ),
        ]
        return '<div class="translume-decision-grid">' + "".join(cards) + "</div>"
    top_treatment = _top_ranked_treatment(packet)
    top_resistance = brief.resistance_forecast[0] if brief.resistance_forecast else None
    top_biomarker = brief.biomarker_watch_list[0] if brief.biomarker_watch_list else None
    top_trigger = brief.retesting_triggers[0] if brief.retesting_triggers else None
    top_test = (
        brief.next_test_recommendations[0]
        if brief.next_test_recommendations
        else None
    )
    cards = [
        _decision_card("Treat now", _treatment_snapshot_value(top_treatment)),
        _decision_card("Target relevance", _treatment_snapshot_value(top_treatment)),
        _decision_card("Biomarker actionability", top_treatment.why_it_fits if top_treatment is not None else ""),
        _decision_card("Resistance readiness", top_resistance.description if top_resistance is not None else ""),
        _decision_card("Biomarker monitoring", _biomarker_snapshot_value(top_biomarker)),
        _decision_card("Re-test trigger / next validation", f"{_trigger_snapshot_value(top_trigger)}; {_next_test_snapshot_value(top_test)}"),
    ]
    return '<div class="translume-decision-grid">' + "".join(cards) + "</div>"


def _short_question_label(question_key: str) -> str:
    return {
        "target_relevance": "Target relevance",
        "biomarker_evidence": "Biomarker evidence",
        "resistance_mechanisms": "Resistance / escape readiness",
        "patient_population_alignment": "Population fit",
        "evidence_resolution": "Evidence + validation",
    }.get(question_key, _humanize(question_key))

def _top_ranked_treatment(packet: ReviewPacketExport) -> Any | None:
    brief = packet.bundle.decision_brief
    assert brief is not None
    if not brief.ranked_treatment_options:
        return None
    return sorted(brief.ranked_treatment_options, key=lambda item: item.rank)[0]


def _treatment_snapshot_value(treatment: Any | None) -> str:
    if treatment is None:
        return "No treatment option was surfaced in the persisted brief."
    return f"{treatment.therapy_name_or_class} ({treatment.clinical_use})"


def _biomarker_snapshot_value(item: Any | None) -> str:
    if item is None:
        return "No biomarker watch item was surfaced in the persisted brief."
    return f"{item.biomarker} via {item.preferred_test}"


def _trigger_snapshot_value(item: Any | None) -> str:
    if item is None:
        return "No event-based re-testing trigger was surfaced."
    return f"{item.clinical_event} → {item.recommended_test}"


def _next_test_snapshot_value(item: Any | None) -> str:
    if item is None:
        return "No next-test recommendation was surfaced."
    return f"{item.test_type}: {item.timing}"


def _decision_card(label: str, value: str) -> str:
    rendered_value = value.strip() or "Not surfaced in the persisted brief."
    return (
        '<div class="translume-decision-card">'
        f'<span class="translume-decision-label">{html.escape(label)}</span>'
        f'<span class="translume-decision-value">{html.escape(rendered_value)}</span>'
        "</div>"
    )


def _decision_summary_markdown(packet: ReviewPacketExport) -> str:
    brief = packet.bundle.decision_brief
    assert brief is not None
    state = brief.current_tumor_state
    sections = [
        brief.clinical_decision_summary,
        _translational_summary_markdown(brief),
        _markdown_list("Dominant drivers", state.dominant_drivers),
        _markdown_list("Active pathways", state.active_pathways),
        _markdown_list("Missing data", state.missing_data),
        f"**Validation status:** `{brief.validation_status}`",
    ]
    return "\n\n".join(section for section in sections if section)




def _translational_check_rows(packet: ReviewPacketExport) -> list[list[Any]]:
    brief = packet.bundle.decision_brief
    assert brief is not None
    assessment = brief.translational_assessment
    if assessment is None:
        return [[
            "Translational checks",
            "unresolved",
            "Five-question assessment was not generated in this packet.",
            "unresolved",
            "Unresolved evidence",
            "Regenerate the report with translational checks enabled.",
        ]]
    return [
        [
            item.question,
            item.status,
            item.answer,
            item.evidence_strength,
            _joined_or_fallback(item.evidence_labels, fallback="Evidence label requires review."),
            _joined_or_fallback(item.validation_next, fallback="Clinician review required."),
        ]
        for item in _assessment_questions(assessment)
    ]


def _assessment_questions(assessment: Any) -> list[Any]:
    return [
        assessment.target_relevance,
        assessment.biomarker_evidence,
        assessment.resistance_mechanisms,
        assessment.patient_population_alignment,
        assessment.evidence_resolution,
    ]



def _translational_summary_markdown(brief: Any) -> str:
    assessment = brief.translational_assessment
    if assessment is None:
        return ""
    return "**Five translational checks**\n" + "\n".join(
        f"- **{item.question}** {item.answer} _(status: {item.status})_"
        for item in _assessment_questions(assessment)
    )



def _evidence_sentence_rows(packet: ReviewPacketExport) -> list[list[Any]]:
    """Return clinician-readable evidence labels without internal IDs."""
    brief = packet.bundle.decision_brief
    assert brief is not None
    return [
        [
            item.evidence_label,
            item.statement,
            item.quote,
            item.relevance,
        ]
        for item in brief.evidence_sentence_map
    ]


def _actionable_biology_rows(packet: ReviewPacketExport) -> list[list[Any]]:
    brief = packet.bundle.decision_brief
    assert brief is not None
    return [
        [
            item.biology,
            item.alteration_or_marker,
            item.actionability,
            item.evidence_level,
            item.rationale,
            item.uncertainty,
            item.confidence,
        ]
        for item in brief.actionable_biology
    ]


def _ranked_treatment_option_rows(packet: ReviewPacketExport) -> list[list[Any]]:
    brief = packet.bundle.decision_brief
    assert brief is not None
    return [
        [
            item.rank,
            item.therapy_name_or_class,
            item.clinical_use,
            item.therapy_class,
            ", ".join(item.matched_biomarkers),
            item.why_it_fits,
            item.evidence_level,
            "; ".join(item.resistance_risks),
            "; ".join(item.required_before_use_tests),
            "; ".join(item.limitations),
            item.confidence,
        ]
        for item in brief.ranked_treatment_options
    ]


def _treatment_pressure_rows(packet: ReviewPacketExport) -> list[list[Any]]:
    brief = packet.bundle.decision_brief
    assert brief is not None
    return [
        [
            item.therapy_name_or_class,
            item.target_or_pathway,
            item.why_it_fits,
            item.selective_pressure,
            "; ".join(item.likely_escape_routes),
            "; ".join(item.biomarkers_to_watch),
            "; ".join(item.evidence_basis),
            item.confidence,
        ]
        for item in brief.treatment_pressure_map
    ]


def _resistance_forecast_rows(packet: ReviewPacketExport) -> list[list[Any]]:
    brief = packet.bundle.decision_brief
    assert brief is not None
    return [
        [
            item.escape_route,
            item.description,
            item.associated_treatment_pressure,
            "; ".join(item.supporting_evidence),
            "; ".join(item.biomarkers_to_monitor),
            item.confidence,
        ]
        for item in brief.resistance_forecast
    ]


def _biomarker_watch_rows(packet: ReviewPacketExport) -> list[list[Any]]:
    brief = packet.bundle.decision_brief
    assert brief is not None
    return [
        [
            item.priority,
            item.biomarker,
            item.alteration_type,
            item.why_watch,
            item.associated_treatment_pressure,
            item.preferred_test,
            item.trigger,
        ]
        for item in brief.biomarker_watch_list
    ]


def _retesting_trigger_rows(packet: ReviewPacketExport) -> list[list[Any]]:
    brief = packet.bundle.decision_brief
    assert brief is not None
    return [
        [
            item.urgency,
            item.clinical_event,
            item.recommended_test,
            item.rationale,
            item.what_result_changes,
        ]
        for item in brief.retesting_triggers
    ]


def _next_test_rows(packet: ReviewPacketExport) -> list[list[Any]]:
    brief = packet.bundle.decision_brief
    assert brief is not None
    return [
        [
            item.priority,
            item.test_type,
            item.timing,
            item.rationale,
            "; ".join(item.biomarkers_or_questions),
            item.result_that_would_change_management,
            "; ".join(item.limitations),
        ]
        for item in brief.next_test_recommendations
    ]


def _decision_limitations_rows(packet: ReviewPacketExport) -> list[list[Any]]:
    brief = packet.bundle.decision_brief
    assert brief is not None
    return [
        [
            item.limitation,
            item.impact,
            item.needed_resolution,
        ]
        for item in brief.evidence_limitations
    ]


def _finding_rows(packet: ReviewPacketExport) -> list[list[Any]]:
    return [
        [
            finding.gene or "",
            finding.alteration,
            finding.alteration_type,
            finding.source_page if finding.source_page is not None else "",
            round(finding.confidence, 4),
            finding.source_text or "",
        ]
        for finding in packet.bundle.extraction.molecular_findings
    ]


def _entity_rows(packet: ReviewPacketExport) -> list[list[Any]]:
    entities = packet.bundle.entities
    assert entities is not None
    return [
        [
            entity.entity_type,
            entity.original_text,
            entity.normalized_label,
            entity.needs_human_review,
        ]
        for entity in entities.entities
    ]


def _phenotype_rows(packet: ReviewPacketExport) -> list[list[Any]]:
    phenotype = packet.bundle.phenotype
    assert phenotype is not None
    return [
        [
            axis.label,
            str(len(axis.supporting_finding_ids)),
            axis.evidence_class,
            axis.uncertainty,
            axis.validation_needed,
        ]
        for axis in phenotype.axes
    ]


def _matrix_rows(packet: ReviewPacketExport) -> list[list[Any]]:
    matrix = packet.bundle.matrix
    assert matrix is not None
    return [
        [
            row.rank,
            row.molecular_fit,
            row.fit_label,
            row.why_from_omics,
            row.evidence_basis,
            row.required_validation,
            row.limitations,
            row.clinical_use,
            row.therapy_class,
            ", ".join(row.matched_biomarkers),
            "; ".join(row.resistance_risks),
            "; ".join(row.required_before_use_tests),
            row.confidence,
            row.evidence_level,
        ]
        for row in matrix.rows
    ]


def _confirmatory_rows(packet: ReviewPacketExport) -> list[list[Any]]:
    confirmatory = packet.bundle.confirmatory
    assert confirmatory is not None
    return [
        [
            test.priority,
            test.question,
            test.why_it_matters,
            test.positive_interpretation,
            test.negative_interpretation,
            test.evidence_gap,
        ]
        for test in confirmatory.tests
    ]


def _tumor_state_rows(packet: ReviewPacketExport) -> list[list[Any]]:
    tumor_behavior = packet.bundle.tumor_behavior
    assert tumor_behavior is not None
    return [
        [
            state.state_label,
            str(len(state.supporting_findings)),
            str(len(state.graph_support)),
            str(len(state.tool_support)),
            str(len(state.medea_support)),
            state.evidence_class,
            state.uncertainty,
            state.validation_needed,
        ]
        for state in tumor_behavior.state_evidence
    ]


def _transition_rows(packet: ReviewPacketExport) -> list[list[Any]]:
    tumor_behavior = packet.bundle.tumor_behavior
    assert tumor_behavior is not None
    return [
        [
            transition.from_state,
            transition.to_state,
            transition.rationale,
            transition.confidence_label,
            transition.validation_status,
            transition.hypothesis_generating,
        ]
        for transition in tumor_behavior.transition_hypotheses
    ]


def _graph_node_rows(packet: ReviewPacketExport) -> list[list[Any]]:
    context = packet.bundle.evidence_context
    assert context is not None
    return [
        [node.label, node.kind, node.source]
        for node in context.graph_evidence.nodes
    ]


def _graph_edge_rows(packet: ReviewPacketExport) -> list[list[Any]]:
    context = packet.bundle.evidence_context
    assert context is not None
    label_by_id = {
        node.node_id: node.label for node in context.graph_evidence.nodes
    }
    return [
        [
            label_by_id.get(edge.source_node_id, edge.source_node_id),
            edge.relation_type,
            label_by_id.get(edge.target_node_id, edge.target_node_id),
            edge.source,
        ]
        for edge in context.graph_evidence.edges
    ]


def _tool_run_rows(packet: ReviewPacketExport) -> list[list[Any]]:
    context = packet.bundle.evidence_context
    assert context is not None
    return [
        [
            tool.workflow,
            tool.summary,
            len(tool.evidence_items),
            "; ".join(tool.warnings),
            tool.requires_human_review,
        ]
        for tool in context.tool_outputs
    ]


def _tool_evidence_rows(packet: ReviewPacketExport) -> list[list[Any]]:
    context = packet.bundle.evidence_context
    assert context is not None
    rows: list[list[Any]] = []
    for tool in context.tool_outputs:
        for item_index, item in enumerate(tool.evidence_items, start=1):
            rows.append(
                [
                    tool.workflow,
                    _first_item_value(item, ("source", "provider", "database")),
                    _first_item_value(item, ("title", "name", "label")),
                    _first_item_value(item, ("pmid", "doi", "identifier", "id")),
                    _first_item_value(item, ("summary", "finding", "relevance", "text")),
                ]
            )
    return rows


def _medea_markdown(packet: ReviewPacketExport) -> str:
    context = packet.bundle.evidence_context
    assert context is not None
    medea = context.medea_reasoning
    sections = [
        f"**Reasoning mode:** `{medea.reasoning_mode}`",
        medea.summary or "No Medea summary was returned.",
        _markdown_list("Supported hypotheses", medea.supported_hypotheses),
        _markdown_list("Weakened hypotheses", medea.weakened_hypotheses),
        _markdown_list("Warnings", medea.warnings),
    ]
    return "\n\n".join(section for section in sections if section)


def _evidence_gaps_markdown(packet: ReviewPacketExport) -> str:
    context = packet.bundle.evidence_context
    assert context is not None
    graph = context.graph_evidence
    sections = [
        _markdown_list("Missing evidence", context.missing_evidence),
        _markdown_list("Conflicting evidence", context.conflicting_evidence),
        _markdown_list("Graph entities without matches", graph.missing_entities),
        _markdown_list("Graph warnings", graph.warnings),
    ]
    rendered = "\n\n".join(section for section in sections if section)
    return rendered or "No evidence gaps were recorded in the persisted packet."


def _narrative_markdown(packet: ReviewPacketExport) -> str:
    narrative = packet.bundle.narrative
    assert narrative is not None
    return f"{narrative.markdown}\n\n> **Safety note:** {narrative.safety_note}"


def _containment_markdown(packet: ReviewPacketExport) -> str:
    containment = packet.bundle.narrative_containment
    assert containment is not None
    if containment.passed:
        return (
            "**Narrative containment:** passed. The persisted narrative did not "
            "introduce unsupported terms according to the production containment gate."
        )
    details = [
        f"- `{finding.term}` ({finding.term_type}): {finding.evidence_gap}"
        for finding in containment.unsupported_findings
    ]
    return "**Narrative containment:** failed.\n\n" + "\n".join(details)


def _claim_rows(packet: ReviewPacketExport) -> list[list[Any]]:
    return [
        [
            claim.validation_status,
            claim.claim_class,
            claim.claim,
            claim.evidence_source,
            claim.relevance,
            claim.limitations,
        ]
        for claim in packet.bundle.claims
    ]


def _validation_rows(packet: ReviewPacketExport) -> list[list[Any]]:
    return [
        [
            decision.status,
            decision.reviewer_id or "",
            decision.reviewer_note or "",
            decision.created_at.isoformat(),
        ]
        for decision in packet.bundle.validation_decisions
    ]


def _provenance_rows(packet: ReviewPacketExport) -> list[list[Any]]:
    return [
        [
            provenance.artifact_type,
            provenance.schema_name,
            provenance.model_name or "",
            provenance.generation_status,
            provenance.validation_status,
            len(provenance.source_chunk_ids),
        ]
        for provenance in packet.bundle.provenance
    ]


def _ledger_rows(packet: ReviewPacketExport) -> list[list[Any]]:
    return [
        [
            event.created_at.isoformat(),
            event.event_type,
            json.dumps(event.details, sort_keys=True),
        ]
        for event in packet.bundle.ledger_events
    ]




def _joined_or_fallback(values: list[str] | tuple[str, ...], *, fallback: str) -> str:
    cleaned = [value.strip() for value in values if value.strip()]
    if not cleaned:
        return fallback
    return "; ".join(cleaned)


def _humanize(value: str) -> str:
    return value.replace("_", " ").strip().capitalize()

def _html_list(title: str, values: list[str]) -> str:
    if not values:
        return ""
    items = "".join(f"<li>{html.escape(value)}</li>" for value in values)
    return f"<strong>{html.escape(title)}</strong><ul class=\"translume-summary-list\">{items}</ul>"


def _markdown_list(title: str, values: list[str]) -> str:
    if not values:
        return ""
    return f"**{title}**\n" + "\n".join(f"- {value}" for value in values)


def _first_item_value(item: dict[str, str], keys: tuple[str, ...]) -> str:
    normalized = {str(key).casefold(): str(value) for key, value in item.items()}
    for key in keys:
        value = normalized.get(key.casefold(), "").strip()
        if value:
            return value
    return ""


def _empty_figure(message: str) -> go.Figure:
    figure = go.Figure()
    figure.add_annotation(
        text=message,
        x=0.5,
        y=0.5,
        xref="paper",
        yref="paper",
        showarrow=False,
        font={"color": "#5f6b7a", "size": 15},
    )
    figure.update_layout(
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        xaxis={"visible": False},
        yaxis={"visible": False},
        height=320,
        margin={"l": 20, "r": 20, "t": 20, "b": 20},
    )
    return figure


def empty_mechanism_figure(message: str = "No review packet loaded.") -> go.Figure:
    """Return a truthful empty-state figure for an unloaded or failed UI state."""
    return _empty_figure(message)
