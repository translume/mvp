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
}
DEFAULT_NODE_COLOR = "#64748b"


@dataclass(frozen=True)
class ClinicalPanelData:
    """Pure UI projection of one persisted ``ReviewPacketExport``."""

    status_markdown: str
    case_summary_html: str
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
    """Build a Plotly Sankey exclusively from the packet mechanism artifact."""
    sankey = packet.bundle.sankey
    if sankey is None:
        raise ClinicalPanelRenderError("MechanismSankeyOutput is unavailable")
    if not sankey.nodes:
        return _empty_figure("No case-supported mechanism nodes were returned.")

    index_by_node_id = {node.node_id: index for index, node in enumerate(sankey.nodes)}
    duplicate_count = len(sankey.nodes) - len(index_by_node_id)
    if duplicate_count:
        raise ClinicalPanelRenderError("Mechanism Sankey contains duplicate node IDs")

    source_indexes: list[int] = []
    target_indexes: list[int] = []
    values: list[float] = []
    customdata: list[list[str]] = []
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
        source_indexes.append(index_by_node_id[link.source_node_id])
        target_indexes.append(index_by_node_id[link.target_node_id])
        values.append(link.value)
        customdata.append(
            [
                link.claim_class,
                "yes" if link.validation_required else "no",
                ", ".join(link.source_artifact_ids),
            ]
        )

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
                    "customdata": [
                        [node.kind, node.evidence_class, node.node_id]
                        for node in sankey.nodes
                    ],
                    "hovertemplate": (
                        "%{label}<br>Type: %{customdata[0]}"
                        "<br>Evidence: %{customdata[1]}"
                        "<br>ID: %{customdata[2]}<extra></extra>"
                    ),
                    "pad": 22,
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
                        "Claim class: %{customdata[0]}"
                        "<br>Validation required: %{customdata[1]}"
                        "<br>Source artifacts: %{customdata[2]}"
                        "<br>Artifact value: %{value}<extra></extra>"
                    ),
                },
            )
        ]
    )
    figure.update_layout(
        title={
            "text": (
                "Finding → Mechanism → Molecular Fit → Validation Test"
                "<br><sup>Link width reflects the structured artifact value; "
                "it is not a calibrated biological probability.</sup>"
            ),
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


def _status_markdown(packet: ReviewPacketExport) -> str:
    statuses = [claim.validation_status for claim in packet.bundle.claims]
    validated = statuses.count("validated")
    rejected = statuses.count("rejected")
    needs_review = statuses.count("needs_review")
    return (
        '<div class="translume-status">'
        f"Persisted review packet loaded for case <strong>{html.escape(packet.case_id)}</strong>. "
        f"Claims: {validated} validated, {rejected} rejected, {needs_review} need review."
        "</div>"
    )


def _case_summary_html(packet: ReviewPacketExport) -> str:
    extraction = packet.bundle.extraction
    summary_items = [
        ("Case", packet.case_id),
        ("Session", packet.session_id),
        ("Report type", extraction.report_type),
        ("Disease context", extraction.disease or "Not stated in report"),
        ("Specimen", extraction.specimen or "Not stated in report"),
        ("Tumor percentage", extraction.tumor_percentage or "Not stated in report"),
        ("Molecular findings", str(len(extraction.molecular_findings))),
        ("Source chunks", str(len(packet.chunks))),
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
        "This output supports translational research review. It is not a diagnosis "
        "or treatment recommendation, and every clinically meaningful claim requires human validation."
        "</div>"
    )


def _finding_rows(packet: ReviewPacketExport) -> list[list[Any]]:
    return [
        [
            finding.gene or "",
            finding.alteration,
            finding.alteration_type,
            finding.source_page if finding.source_page is not None else "",
            round(finding.confidence, 4),
            finding.research_use_only,
            finding.needs_human_review,
            finding.source_text or "",
            finding.finding_id,
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
            entity.source_finding_id or "",
            entity.needs_human_review,
            entity.entity_id,
        ]
        for entity in entities.entities
    ]


def _phenotype_rows(packet: ReviewPacketExport) -> list[list[Any]]:
    phenotype = packet.bundle.phenotype
    assert phenotype is not None
    return [
        [
            axis.label,
            ", ".join(axis.supporting_finding_ids),
            axis.evidence_class,
            axis.uncertainty,
            axis.validation_needed,
            axis.axis_id,
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
            row.not_a_recommendation,
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
            ", ".join(test.source_claim_ids),
            test.test_id,
        ]
        for test in confirmatory.tests
    ]


def _tumor_state_rows(packet: ReviewPacketExport) -> list[list[Any]]:
    tumor_behavior = packet.bundle.tumor_behavior
    assert tumor_behavior is not None
    return [
        [
            state.state_label,
            ", ".join(state.supporting_findings),
            ", ".join(state.graph_support),
            ", ".join(state.tool_support),
            ", ".join(state.medea_support),
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
            ", ".join(transition.supporting_artifacts),
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
        [node.label, node.kind, node.source, node.node_id]
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
            edge.edge_id,
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
            tool.artifact_id,
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
                    json.dumps(item, sort_keys=True),
                    item_index,
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
            claim.claim_id,
            claim.validation_status,
            claim.claim_class,
            claim.claim,
            claim.evidence_source,
            claim.relevance,
            claim.limitations,
            ", ".join(claim.source_artifact_ids),
        ]
        for claim in packet.bundle.claims
    ]


def _validation_rows(packet: ReviewPacketExport) -> list[list[Any]]:
    return [
        [
            decision.status,
            decision.claim_id,
            decision.reviewer_id or "",
            decision.reviewer_note or "",
            decision.created_at.isoformat(),
            decision.decision_id,
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
            ", ".join(provenance.source_artifact_ids),
            provenance.prompt_hash or "",
            provenance.schema_hash or "",
            provenance.artifact_id,
        ]
        for provenance in packet.bundle.provenance
    ]


def _ledger_rows(packet: ReviewPacketExport) -> list[list[Any]]:
    return [
        [
            event.created_at.isoformat(),
            event.event_type,
            event.artifact_id or "",
            json.dumps(event.details, sort_keys=True),
            event.event_id,
        ]
        for event in packet.bundle.ledger_events
    ]


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
