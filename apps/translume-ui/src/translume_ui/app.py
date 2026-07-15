from __future__ import annotations

import html
import logging
import os
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import gradio as gr

from translume_schemas.downstream import DownstreamAnalysisResult

from translume_ui.api_client import (
    TranslumeAPIClient,
    TranslumeAPIClientConfig,
    TranslumeUIAPIError,
    write_persisted_decision_brief,
    write_persisted_review_packet,
)
from translume_ui.panels import (
    ClinicalPanelData,
    ClinicalPanelRenderError,
    build_clinical_panel_data,
    empty_mechanism_figure,
)
from translume_ui.styles import TRANSLUME_CSS, header_html


DEFAULT_API_BASE_URL = "http://translume-api:8080"
DEFAULT_UI_HOST = "0.0.0.0"
DEFAULT_UI_PORT = 7860
DEFAULT_REQUEST_TIMEOUT_SECONDS = 120.0
DEFAULT_PROCESS_TIMEOUT_SECONDS = 3600.0

logger = logging.getLogger(__name__)


class TranslumeUIConfigError(ValueError):
    """Raised when Gradio UI runtime configuration is invalid."""


@dataclass(frozen=True)
class UIServerConfig:
    """Represent Gradio server launch configuration."""

    host: str
    port: int


def api_base_url_from_environment(environment: Mapping[str, str]) -> str:
    """Return the normalized FastAPI base URL used by the Gradio UI."""
    raw_value = environment.get("TRANSLUME_API_BASE_URL", DEFAULT_API_BASE_URL)
    value = raw_value.strip().rstrip("/")
    if not value:
        raise TranslumeUIConfigError("TRANSLUME_API_BASE_URL must not be empty")
    if not value.startswith(("http://", "https://")):
        raise TranslumeUIConfigError(
            "TRANSLUME_API_BASE_URL must start with http:// or https://"
        )
    return value


def ui_server_config_from_environment(environment: Mapping[str, str]) -> UIServerConfig:
    """Return Gradio launch configuration from environment variables."""
    host = environment.get("TRANSLUME_UI_HOST", DEFAULT_UI_HOST).strip()
    raw_port = environment.get("TRANSLUME_UI_PORT", str(DEFAULT_UI_PORT)).strip()
    if not host:
        raise TranslumeUIConfigError("TRANSLUME_UI_HOST must not be empty")
    try:
        port = int(raw_port)
    except ValueError as error:
        raise TranslumeUIConfigError(
            "TRANSLUME_UI_PORT must be an integer"
        ) from error
    if port <= 0:
        raise TranslumeUIConfigError("TRANSLUME_UI_PORT must be positive")
    return UIServerConfig(host=host, port=port)


def build_api_client(environment: Mapping[str, str]) -> TranslumeAPIClient:
    """Build the real FastAPI client from UI runtime configuration."""
    return TranslumeAPIClient(
        TranslumeAPIClientConfig(
            base_url=api_base_url_from_environment(environment),
            request_timeout_seconds=_positive_float_from_environment(
                environment,
                "TRANSLUME_UI_API_TIMEOUT_SECONDS",
                DEFAULT_REQUEST_TIMEOUT_SECONDS,
            ),
            process_timeout_seconds=_positive_float_from_environment(
                environment,
                "TRANSLUME_UI_PROCESS_TIMEOUT_SECONDS",
                DEFAULT_PROCESS_TIMEOUT_SECONDS,
            ),
            downstream_timeout_seconds=_positive_float_from_environment(
                environment,
                "TRANSLUME_UI_DOWNSTREAM_TIMEOUT_SECONDS",
                7200.0,
            ),
        )
    )


def export_root_from_environment(environment: Mapping[str, str]) -> Path:
    """Return the local directory used only for user-requested packet downloads."""
    configured = environment.get("TRANSLUME_UI_EXPORT_DIR", "").strip()
    if configured:
        return Path(configured)
    return Path(tempfile.gettempdir()) / "translume-ui-exports"


def process_pdf(
    file_path: str | None,
    report_type: str,
    diagnosis: str,
) -> tuple[Any, ...]:
    """Run the persisted review and downstream pathway workflows.

    The UI intentionally performs a second API read through the persisted export
    endpoint after processing. It then requests the downstream services through
    FastAPI, never by invoking Docker or local pipeline commands.
    """
    if not file_path:
        return _empty_process_outputs("Upload a PDF before processing.")
    if not diagnosis.strip():
        return _empty_process_outputs("Enter a diagnosis before processing.")
    try:
        client = build_api_client(os.environ)
        processed_packet = client.process_report(Path(file_path), report_type)
        persisted_packet = client.fetch_review_packet(processed_packet.session_id)
        if persisted_packet.case_id != processed_packet.case_id:
            raise TranslumeUIAPIError(
                "Persisted packet case ID does not match the processing response"
            )
        panels = build_clinical_panel_data(persisted_packet)
    except (
        OSError,
        TranslumeUIAPIError,
        TranslumeUIConfigError,
        ClinicalPanelRenderError,
        ValueError,
    ) as error:
        logger.exception("Report processing could not be rendered in the cockpit")
        return _empty_process_outputs(str(error))
    try:
        downstream = client.run_downstream_analysis(
            persisted_packet.session_id,
            diagnosis,
        )
    except (OSError, TranslumeUIAPIError, TranslumeUIConfigError, ValueError) as error:
        logger.exception("Downstream pathway analysis could not be rendered")
        return _process_outputs(
            persisted_packet.session_id,
            panels,
            None,
            _error_html(f"Downstream pathway analysis failed: {error}"),
        )
    return _process_outputs(persisted_packet.session_id, panels, downstream, "")


def submit_validation(
    session_id: str,
    claim_id: str,
    status: str,
    reviewer_id: str,
    reviewer_note: str,
) -> tuple[Any, ...]:
    """Persist a human review decision and refresh affected panels from API."""
    try:
        client = build_api_client(os.environ)
        response = client.validate_claim(
            session_id=session_id,
            claim_id=claim_id,
            status=status,
            reviewer_id=reviewer_id,
            reviewer_note=reviewer_note,
        )
        persisted_packet = client.fetch_review_packet(session_id)
        panels = build_clinical_panel_data(persisted_packet)
        decision = response.get("decision")
        decision_id = ""
        if isinstance(decision, dict):
            decision_id = str(decision.get("decision_id", ""))
        status_html = (
            '<div class="translume-status">'
            f"Validation decision <strong>{html.escape(status)}</strong> was persisted "
            f"for claim <strong>{html.escape(claim_id)}</strong>. "
            f"Decision ID: {html.escape(decision_id)}"
            "</div>"
        )
    except (
        OSError,
        TranslumeUIAPIError,
        TranslumeUIConfigError,
        ClinicalPanelRenderError,
        ValueError,
    ) as error:
        logger.exception("Claim validation could not be persisted or reloaded")
        return (
            _error_html(str(error)),
            gr.update(),
            gr.update(),
            gr.update(),
            gr.update(),
            gr.update(),
        )
    return (
        status_html,
        panels.claim_rows,
        gr.update(
            choices=panels.claim_choices,
            value=claim_id if claim_id in panels.claim_choices else None,
        ),
        panels.validation_rows,
        panels.ledger_rows,
        panels.raw_json,
    )


def download_persisted_export(session_id: str) -> tuple[str | None, str]:
    """Fetch the exact persisted packet and expose it as a JSON download."""
    if not session_id.strip():
        return None, _error_html("No processed review packet session is available.")
    try:
        client = build_api_client(os.environ)
        packet = client.fetch_review_packet(session_id)
        output_path = write_persisted_review_packet(
            packet,
            export_root_from_environment(os.environ),
        )
    except (
        OSError,
        TranslumeUIAPIError,
        TranslumeUIConfigError,
        ValueError,
    ) as error:
        logger.exception("Persisted review packet export could not be fetched")
        return None, _error_html(str(error))
    return (
        str(output_path),
        '<div class="translume-status">Persisted review packet export is ready.</div>',
    )



def download_persisted_decision_brief(session_id: str) -> tuple[str | None, str]:
    """Fetch the focused persisted decision brief and expose it as JSON.

    Acceptance criteria:
        1. Requires a processed session ID.
        2. Calls the dedicated decision-brief API endpoint.
        3. Writes only the decision-brief artifact to the download file.
        4. Does not reconstruct the brief from the full packet locally.
    """
    if not session_id.strip():
        return None, _error_html("No processed decision brief session is available.")
    try:
        client = build_api_client(os.environ)
        brief = client.fetch_decision_brief(session_id)
        output_path = write_persisted_decision_brief(
            brief,
            export_root_from_environment(os.environ),
        )
    except (
        OSError,
        TranslumeUIAPIError,
        TranslumeUIConfigError,
        ValueError,
    ) as error:
        logger.exception("Persisted decision brief export could not be fetched")
        return None, _error_html(str(error))
    return (
        str(output_path),
        '<div class="translume-status">Persisted decision brief export is ready.</div>',
    )


def build_app() -> gr.Blocks:
    """Build the clinician-facing cockpit from live API-returned artifacts only."""
    with gr.Blocks(
        title="Translume Oncologist Cockpit",
        fill_width=True,
    ) as demo:
        gr.HTML(header_html())
        session_state = gr.State("")

        with gr.Row(equal_height=False):
            with gr.Column(scale=3, min_width=300):
                report = gr.File(
                    label="Oncology report PDF",
                    file_types=[".pdf"],
                    type="filepath",
                    elem_classes=["translume-panel"],
                )
                report_type = gr.Dropdown(
                    choices=["NGS", "WGS", "FISH", "IHC", "RESEARCH_PDF", "XT", "XR", "RNA"],
                    value="NGS",
                    label="Report type",
                )
                diagnosis = gr.Textbox(
                    label="Diagnosis",
                    placeholder="e.g. dedifferentiated chondrosarcoma",
                )
                run = gr.Button(
                    "Generate report and pathway analysis",
                    variant="primary",
                )
            with gr.Column(scale=9):
                with gr.Tabs():
                    with gr.Tab("Pathway analysis"):
                        pathway_analysis_markdown = gr.Markdown(
                            "",
                            label="Pathway analysis",
                            sanitize_html=True,
                        )
                        research_memo_markdown = gr.Markdown(
                            "",
                            label="Research memo",
                            sanitize_html=True,
                        )
                        tumor_board_summary_markdown = gr.Markdown(
                            "",
                            label="Tumor board causal summary",
                            sanitize_html=True,
                        )

                    with gr.Tab("Clinical review"):
                        with gr.Accordion("1. Oncologist decision brief", open=True):
                            decision_snapshot = gr.HTML(
                                '<div class="translume-safety-note">No decision brief is loaded.</div>',
                                label="Fast decision snapshot",
                            )
                            decision_summary = gr.Markdown("")
                            translational_checks_table = gr.Dataframe(
                                headers=[
                                    "Question",
                                    "Status",
                                    "Answer",
                                    "Evidence strength",
                                    "Evidence labels",
                                    "Validation needed",
                                ],
                                interactive=False,
                                wrap=True,
                                label="Five translational checks",
                            )
                            evidence_sentence_table = gr.Dataframe(
                                headers=[
                                    "Evidence label",
                                    "Evidence statement",
                                    "Source excerpt",
                                    "Why it matters",
                                ],
                                interactive=False,
                                wrap=True,
                                label="Evidence sentence map",
                            )
                            actionable_biology_table = gr.Dataframe(
                                headers=[
                                    "Biology",
                                    "Alteration / marker",
                                    "Actionability",
                                    "Evidence level",
                                    "Rationale",
                                    "Uncertainty",
                                    "Confidence",
                                ],
                                interactive=False,
                                wrap=True,
                                label="Treatable biology",
                            )
                            ranked_treatment_options_table = gr.Dataframe(
                                headers=[
                                    "Rank",
                                    "Therapy",
                                    "Clinical use",
                                    "Class",
                                    "Matched biomarkers",
                                    "Why it fits",
                                    "Evidence",
                                    "Resistance risks",
                                    "Required before-use tests",
                                    "Limitations",
                                    "Confidence",
                                ],
                                interactive=False,
                                wrap=True,
                                label="Ranked treatment options",
                            )
                            treatment_pressure_table = gr.Dataframe(
                                headers=[
                                    "Therapy",
                                    "Target / pathway",
                                    "Why it fits",
                                    "Selective pressure",
                                    "Likely escape routes",
                                    "Biomarkers to watch",
                                    "Evidence basis",
                                    "Confidence",
                                ],
                                interactive=False,
                                wrap=True,
                                label="Treatment pressure map",
                            )
                            resistance_forecast_table = gr.Dataframe(
                                headers=[
                                    "Escape route",
                                    "Description",
                                    "Treatment pressure",
                                    "Supporting evidence",
                                    "Biomarkers",
                                    "Confidence",
                                ],
                                interactive=False,
                                wrap=True,
                                label="Resistance forecast",
                            )
                            biomarker_watch_table = gr.Dataframe(
                                headers=[
                                    "Priority",
                                    "Biomarker",
                                    "Alteration type",
                                    "Why watch",
                                    "Treatment pressure",
                                    "Preferred test",
                                    "Trigger",
                                ],
                                interactive=False,
                                wrap=True,
                                label="Biomarker watch list",
                            )
                            retesting_triggers_table = gr.Dataframe(
                                headers=[
                                    "Urgency",
                                    "Clinical event",
                                    "Recommended test",
                                    "Rationale",
                                    "What result changes",
                                ],
                                interactive=False,
                                wrap=True,
                                label="Re-testing triggers",
                            )
                            next_tests_table = gr.Dataframe(
                                headers=[
                                    "Priority",
                                    "Test type",
                                    "Timing",
                                    "Rationale",
                                    "Biomarkers / questions",
                                    "Result that changes management",
                                    "Limitations",
                                ],
                                interactive=False,
                                wrap=True,
                                label="Next test recommendations",
                            )
                            decision_limitations_table = gr.Dataframe(
                                headers=[
                                    "Limitation",
                                    "Impact",
                                    "Needed resolution",
                                ],
                                interactive=False,
                                wrap=True,
                                label="Evidence limitations",
                            )
                            decision_export_button = gr.Button(
                                "Fetch decision brief JSON",
                                variant="secondary",
                            )
                            decision_export_file = gr.File(
                                label="Decision brief JSON download",
                                interactive=False,
                            )
                            decision_export_status = gr.HTML("")

                        with gr.Accordion("2. Source-backed report findings", open=False):
                            findings_table = gr.Dataframe(
                                headers=[
                                    "Gene",
                                    "Alteration",
                                    "Type",
                                    "Page",
                                    "Confidence",
                                    "Source text",
                                ],
                                interactive=False,
                                wrap=True,
                            )
                            entities_table = gr.Dataframe(
                                headers=[
                                    "Entity type",
                                    "Original text",
                                    "Normalized label",
                                    "Needs review",
                                ],
                                interactive=False,
                                wrap=True,
                                label="Normalized biomedical entities",
                            )

                        with gr.Accordion("3. Biological interpretation", open=False):
                            phenotype_table = gr.Dataframe(
                                headers=[
                                    "Biological axis",
                                    "Supporting finding count",
                                    "Evidence class",
                                    "Uncertainty",
                                    "Validation needed",
                                ],
                                interactive=False,
                                wrap=True,
                                label="Molecular phenotype",
                            )
                            matrix_table = gr.Dataframe(
                                headers=[
                                    "Rank",
                                    "Molecular fit",
                                    "Fit label",
                                    "Why from omics",
                                    "Evidence basis",
                                    "Required validation",
                                    "Limitations",
                                    "Clinical use",
                                    "Therapy class",
                                    "Matched biomarkers",
                                    "Resistance risks",
                                    "Required before-use tests",
                                    "Confidence",
                                    "Evidence level",
                                ],
                                interactive=False,
                                wrap=True,
                                label="Molecular-fit review matrix",
                            )

                        with gr.Accordion("4. Mechanism Sankey: Therapy-to-escape flow", open=True):
                            sankey_plot = gr.Plot(
                                value=empty_mechanism_figure(),
                                label="Mechanism Sankey: Therapy-to-escape flow",
                                show_label=False,
                            )

                        with gr.Accordion("5. Confirmatory validation path", open=False):
                            confirmatory_table = gr.Dataframe(
                                headers=[
                                    "Priority",
                                    "Question",
                                    "Why it matters",
                                    "Positive interpretation",
                                    "Negative interpretation",
                                    "Evidence gap",
                                ],
                                interactive=False,
                                wrap=True,
                            )

                        with gr.Accordion("6. Tumor-behavior hypotheses", open=False):
                            tumor_states_table = gr.Dataframe(
                                headers=[
                                    "State",
                                    "Supporting finding count",
                                    "Graph support",
                                    "Tool support",
                                    "Medea support",
                                    "Evidence class",
                                    "Uncertainty",
                                    "Validation needed",
                                ],
                                interactive=False,
                                wrap=True,
                                label="Case-derived state evidence",
                            )
                            transitions_table = gr.Dataframe(
                                headers=[
                                    "From state",
                                    "To state",
                                    "Rationale",
                                    "Confidence label",
                                    "Validation status",
                                    "Hypothesis-generating",
                                ],
                                interactive=False,
                                wrap=True,
                                label="Transition hypotheses",
                            )

                        with gr.Accordion("7. Clinical-translational narrative", open=False):
                            narrative_markdown = gr.Markdown("")
                            containment_markdown = gr.Markdown("")

                    with gr.Tab("Evidence details"):
                        with gr.Accordion("OptimusKG graph context", open=True):
                            graph_nodes_table = gr.Dataframe(
                                headers=["Node", "Kind", "Source"],
                                interactive=False,
                                wrap=True,
                            )
                            graph_edges_table = gr.Dataframe(
                                headers=["Source node", "Relation", "Target node", "Source"],
                                interactive=False,
                                wrap=True,
                            )

                        with gr.Accordion("ToolUniverse evidence", open=True):
                            tool_runs_table = gr.Dataframe(
                                headers=[
                                    "Workflow",
                                    "Summary",
                                    "Evidence items",
                                    "Warnings",
                                    "Needs review",
                                ],
                                interactive=False,
                                wrap=True,
                            )
                            tool_evidence_table = gr.Dataframe(
                                headers=[
                                    "Workflow",
                                    "Source",
                                    "Title",
                                    "Identifier",
                                    "Finding / relevance",
                                ],
                                interactive=False,
                                wrap=True,
                            )

                        with gr.Accordion("Medea bounded reasoning", open=True):
                            medea_markdown = gr.Markdown("")

                        with gr.Accordion("Evidence gaps and conflicts", open=True):
                            evidence_gaps_markdown = gr.Markdown("")

                        with gr.Accordion("Human claim validation", open=True):
                            claims_table = gr.Dataframe(
                                headers=[
                                    "Status",
                                    "Class",
                                    "Claim",
                                    "Evidence source",
                                    "Relevance",
                                    "Limitations",
                                ],
                                interactive=False,
                                wrap=True,
                            )
                            claim_selector = gr.Dropdown(
                                choices=[],
                                label="Claim to validate",
                            )
                            with gr.Row():
                                validation_status = gr.Dropdown(
                                    choices=["validated", "rejected", "needs_review"],
                                    value="needs_review",
                                    label="Validation decision",
                                )
                                reviewer_id = gr.Textbox(label="Reviewer ID")
                            reviewer_note = gr.Textbox(
                                label="Reviewer note",
                                lines=3,
                            )
                            validate_button = gr.Button(
                                "Persist validation decision",
                                variant="secondary",
                            )
                            validation_status_message = gr.HTML("")

                    with gr.Tab("Technical audit"):
                        validation_decisions_table = gr.Dataframe(
                            headers=[
                                "Status",
                                "Reviewer",
                                "Reviewer note",
                                "Created at",
                            ],
                            interactive=False,
                            wrap=True,
                            label="Human validation decisions",
                        )
                        provenance_table = gr.Dataframe(
                            headers=[
                                "Artifact type",
                                "Schema",
                                "Model / provider",
                                "Generation status",
                                "Validation status",
                                "Source chunks",
                            ],
                            interactive=False,
                            wrap=True,
                            label="Artifact provenance",
                        )
                        ledger_table = gr.Dataframe(
                            headers=[
                                "Created at",
                                "Event",
                                "Details",
                            ],
                            interactive=False,
                            wrap=True,
                            label="Discovery ledger",
                        )
                        export_button = gr.Button(
                            "Fetch technical packet export",
                            variant="secondary",
                        )
                        export_file = gr.File(
                            label="Technical packet JSON download",
                            interactive=False,
                        )
                        export_status = gr.HTML("")

                    with gr.Tab("Raw packet"):
                        raw_packet = gr.Code(
                            label="Exact persisted review packet JSON",
                            language="json",
                        )

        process_outputs = [
            session_state,
            decision_snapshot,
            decision_summary,
            translational_checks_table,
            evidence_sentence_table,
            actionable_biology_table,
            ranked_treatment_options_table,
            treatment_pressure_table,
            resistance_forecast_table,
            biomarker_watch_table,
            retesting_triggers_table,
            next_tests_table,
            decision_limitations_table,
            findings_table,
            entities_table,
            phenotype_table,
            matrix_table,
            sankey_plot,
            confirmatory_table,
            tumor_states_table,
            transitions_table,
            graph_nodes_table,
            graph_edges_table,
            tool_runs_table,
            tool_evidence_table,
            medea_markdown,
            evidence_gaps_markdown,
            narrative_markdown,
            containment_markdown,
            claims_table,
            claim_selector,
            validation_decisions_table,
            provenance_table,
            ledger_table,
            raw_packet,
            pathway_analysis_markdown,
            research_memo_markdown,
            tumor_board_summary_markdown,
        ]
        run.click(
            process_pdf,
            inputs=[report, report_type, diagnosis],
            outputs=process_outputs,
        )
        validate_button.click(
            submit_validation,
            inputs=[
                session_state,
                claim_selector,
                validation_status,
                reviewer_id,
                reviewer_note,
            ],
            outputs=[
                validation_status_message,
                claims_table,
                claim_selector,
                validation_decisions_table,
                ledger_table,
                raw_packet,
            ],
        )
        decision_export_button.click(
            download_persisted_decision_brief,
            inputs=[session_state],
            outputs=[decision_export_file, decision_export_status],
        )
        export_button.click(
            download_persisted_export,
            inputs=[session_state],
            outputs=[export_file, export_status],
        )
    return demo


def main() -> int:
    """Launch the production Gradio application directly."""
    api_base_url_from_environment(os.environ)
    server_config = ui_server_config_from_environment(os.environ)
    export_root = export_root_from_environment(os.environ)
    export_root.mkdir(parents=True, exist_ok=True)
    build_app().launch(
        server_name=server_config.host,
        server_port=server_config.port,
        css=TRANSLUME_CSS,
        allowed_paths=[str(export_root)],
    )
    return 0


def _process_outputs(
    session_id: str,
    panels: ClinicalPanelData,
    downstream: DownstreamAnalysisResult | None,
    downstream_status: str,
) -> tuple[Any, ...]:
    return (
        session_id,
        panels.decision_snapshot_html,
        panels.decision_summary_markdown,
        panels.translational_check_rows,
        panels.evidence_sentence_rows,
        panels.actionable_biology_rows,
        panels.ranked_treatment_option_rows,
        panels.treatment_pressure_rows,
        panels.resistance_forecast_rows,
        panels.biomarker_watch_rows,
        panels.retesting_trigger_rows,
        panels.next_test_rows,
        panels.decision_limitations_rows,
        panels.findings_rows,
        panels.entity_rows,
        panels.phenotype_rows,
        panels.matrix_rows,
        panels.sankey_figure,
        panels.confirmatory_rows,
        panels.tumor_state_rows,
        panels.transition_rows,
        panels.graph_node_rows,
        panels.graph_edge_rows,
        panels.tool_run_rows,
        panels.tool_evidence_rows,
        panels.medea_markdown,
        panels.evidence_gaps_markdown,
        panels.narrative_markdown,
        panels.containment_markdown,
        panels.claim_rows,
        gr.update(
            choices=panels.claim_choices,
            value=panels.claim_choices[0] if panels.claim_choices else None,
        ),
        panels.validation_rows,
        panels.provenance_rows,
        panels.ledger_rows,
        panels.raw_json,
        (
            downstream_status
            if downstream is None
            else downstream.pathway_analysis_markdown
        ),
        "" if downstream is None else downstream.research_memo_markdown,
        "" if downstream is None else downstream.tumor_board_summary_markdown,
    )


def _empty_process_outputs(error_message: str) -> tuple[Any, ...]:
    empty_tables = [[] for _ in range(25)]
    return (
        "",
        _error_html(error_message),
        "",
        empty_tables[0],
        empty_tables[1],
        empty_tables[2],
        empty_tables[3],
        empty_tables[4],
        empty_tables[5],
        empty_tables[6],
        empty_tables[7],
        empty_tables[8],
        empty_tables[9],
        empty_tables[10],
        empty_tables[11],
        empty_tables[12],
        empty_tables[13],
        empty_mechanism_figure("No mechanism artifact is available."),
        empty_tables[14],
        empty_tables[15],
        empty_tables[16],
        empty_tables[17],
        empty_tables[18],
        empty_tables[19],
        empty_tables[20],
        "",
        "",
        "",
        "",
        empty_tables[21],
        gr.update(choices=[], value=None),
        empty_tables[22],
        empty_tables[23],
        empty_tables[24],
        json_error_payload(error_message),
        "",
        "",
        "",
    )


def json_error_payload(error_message: str) -> str:
    """Return a JSON error object for the technical packet panel."""
    import json

    return json.dumps({"error": error_message}, indent=2)


def _error_html(message: str) -> str:
    return f'<div class="translume-error">{html.escape(message)}</div>'


def _positive_float_from_environment(
    environment: Mapping[str, str],
    key: str,
    default: float,
) -> float:
    raw_value = environment.get(key, str(default)).strip()
    try:
        value = float(raw_value)
    except ValueError as error:
        raise TranslumeUIConfigError(f"{key} must be a number") from error
    if value <= 0:
        raise TranslumeUIConfigError(f"{key} must be positive")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
