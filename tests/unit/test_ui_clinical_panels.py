from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

from translume_schemas.export import ReviewPacketExport
from translume_schemas.downstream import DownstreamAnalysisResult
from translume_ui.api_client import (
    TranslumeAPIClient,
    TranslumeAPIClientConfig,
    write_persisted_decision_brief,
    write_persisted_review_packet,
)
from translume_ui.app import build_api_client, build_app
from translume_ui.panels import (
    ClinicalPanelRenderError,
    build_clinical_panel_data,
    build_mechanism_sankey_figure,
)


def _packet() -> ReviewPacketExport:
    now = datetime(2026, 6, 18, tzinfo=timezone.utc).isoformat()
    return ReviewPacketExport.model_validate(
        {
            "case_id": "case-ui",
            "session_id": "session-ui",
            "source_file_id": "source-ui",
            "chunks": [
                {
                    "chunk_id": "chunk-1",
                    "case_id": "case-ui",
                    "session_id": "session-ui",
                    "source_file_id": "source-ui",
                    "report_type": "NGS",
                    "page_start": 1,
                    "page_end": 1,
                    "section": "genomic_variants",
                    "chunk_type": "molecular_finding",
                    "source_text": "GENE1 copy-number loss",
                    "source_block_ids": ["block-1"],
                    "needs_human_review": True,
                }
            ],
            "bundle": {
                "case_id": "case-ui",
                "session_id": "session-ui",
                "extraction": {
                    "artifact_id": "artifact-extraction",
                    "report_type": "NGS",
                    "disease": "Example sarcoma",
                    "specimen": "Soft tissue",
                    "tumor_percentage": "70%",
                    "molecular_findings": [
                        {
                            "finding_id": "finding-1",
                            "gene": "GENE1",
                            "alteration": "copy-number loss",
                            "alteration_type": "copy_number_loss",
                            "source_page": 1,
                            "source_text": "GENE1 copy-number loss",
                            "source_chunk_id": "chunk-1",
                            "confidence": 0.92,
                            "needs_human_review": True,
                            "research_use_only": False,
                        }
                    ],
                    "negative_findings": ["No fusion was reported."],
                    "assay_limitations": ["No matched normal was provided."],
                    "source_file_id": "source-ui",
                    "needs_human_review": True,
                },
                "entities": {
                    "artifact_id": "artifact-entities",
                    "case_id": "case-ui",
                    "session_id": "session-ui",
                    "entities": [
                        {
                            "entity_id": "entity-1",
                            "entity_type": "gene",
                            "original_text": "GENE1",
                            "normalized_label": "GENE1",
                            "source_finding_id": "finding-1",
                            "source_artifact_id": "artifact-extraction",
                            "needs_human_review": True,
                        }
                    ],
                },
                "evidence_context": {
                    "artifact_id": "artifact-context",
                    "extraction": {
                        "artifact_id": "artifact-extraction",
                        "report_type": "NGS",
                        "disease": "Example sarcoma",
                        "specimen": "Soft tissue",
                        "tumor_percentage": "70%",
                        "molecular_findings": [
                            {
                                "finding_id": "finding-1",
                                "gene": "GENE1",
                                "alteration": "copy-number loss",
                                "alteration_type": "copy_number_loss",
                                "source_page": 1,
                                "source_text": "GENE1 copy-number loss",
                                "source_chunk_id": "chunk-1",
                                "confidence": 0.92,
                                "needs_human_review": True,
                                "research_use_only": False,
                            }
                        ],
                        "negative_findings": ["No fusion was reported."],
                        "assay_limitations": ["No matched normal was provided."],
                        "source_file_id": "source-ui",
                        "needs_human_review": True,
                    },
                    "graph_evidence": {
                        "artifact_id": "artifact-graph",
                        "source_entity_ids": ["entity-1"],
                        "nodes": [
                            {
                                "node_id": "node-finding",
                                "label": "GENE1 loss",
                                "kind": "finding",
                                "source": "optimuskg",
                                "provenance": {"dataset": "gold"},
                            },
                            {
                                "node_id": "node-mechanism",
                                "label": "Checkpoint disruption",
                                "kind": "mechanism",
                                "source": "optimuskg",
                                "provenance": {"dataset": "gold"},
                            },
                        ],
                        "edges": [
                            {
                                "edge_id": "edge-1",
                                "source_node_id": "node-finding",
                                "target_node_id": "node-mechanism",
                                "relation_type": "associated_with",
                                "source": "optimuskg",
                                "provenance": {"dataset": "gold"},
                            }
                        ],
                        "missing_entities": [],
                        "warnings": [],
                    },
                    "tool_outputs": [
                        {
                            "artifact_id": "artifact-tool",
                            "workflow": "literature_validation",
                            "input_entity_ids": ["entity-1"],
                            "summary": "One reviewable paper was returned.",
                            "evidence_items": [
                                {
                                    "source": "PubMed",
                                    "title": "Evidence title",
                                    "pmid": "12345678",
                                    "finding": "Mechanism context requires review.",
                                }
                            ],
                            "warnings": [],
                            "requires_human_review": True,
                        }
                    ],
                    "medea_reasoning": {
                        "artifact_id": "artifact-medea",
                        "reasoning_mode": "bounded_review_support",
                        "summary": "The mechanism is plausible but unvalidated.",
                        "supported_hypotheses": ["Checkpoint-state pressure"],
                        "weakened_hypotheses": [],
                        "warnings": [],
                        "requires_human_review": True,
                    },
                    "missing_evidence": ["Protein-level confirmation is missing."],
                    "conflicting_evidence": [],
                },
                "phenotype": {
                    "artifact_id": "artifact-phenotype",
                    "axes": [
                        {
                            "axis_id": "axis-1",
                            "label": "Cell-cycle control review",
                            "supporting_finding_ids": ["finding-1"],
                            "evidence_class": "patient_specific_with_graph_context",
                            "uncertainty": "Protein state is unknown.",
                            "validation_needed": True,
                        }
                    ],
                    "limitations": ["Hypothesis-generating only."],
                },
                "matrix": {
                    "artifact_id": "artifact-matrix",
                    "rows": [
                        {
                            "rank": 1,
                            "molecular_fit": "Checkpoint-axis review",
                            "fit_label": "conditional",
                            "why_from_omics": "The report contains a source-backed loss event.",
                            "evidence_basis": "report plus graph and literature context",
                            "limitations": "Requires clinician validation before use.",
                            "required_validation": "Confirm downstream protein state.",
                            "clinical_use": "insufficient_evidence",
                            "therapy_class": "cell-cycle pathway context",
                            "matched_biomarkers": ["GENE1"],
                            "resistance_risks": ["Bypass signaling should be watched if this pathway is targeted."],
                            "required_before_use_tests": ["Confirm downstream protein state."],
                            "confidence": "needs_review",
                            "evidence_level": "source-backed hypothesis requiring review",
                        }
                    ],
                },
                "sankey": {
                    "artifact_id": "artifact-sankey",
                    "nodes": [
                        {
                            "node_id": "finding-node",
                            "label": "GENE1 loss",
                            "kind": "finding",
                            "evidence_class": "patient_specific_finding",
                        },
                        {
                            "node_id": "mechanism-node",
                            "label": "Checkpoint disruption",
                            "kind": "mechanism",
                            "evidence_class": "graph_supported_context",
                        },
                        {
                            "node_id": "validation-node",
                            "label": "Protein confirmation",
                            "kind": "validation_test",
                            "evidence_class": "needs_review",
                        },
                    ],
                    "links": [
                        {
                            "source_node_id": "finding-node",
                            "target_node_id": "mechanism-node",
                            "value": 1.0,
                            "claim_class": "graph_supported_context",
                            "validation_required": True,
                            "source_artifact_ids": ["artifact-extraction", "artifact-graph"],
                        },
                        {
                            "source_node_id": "mechanism-node",
                            "target_node_id": "validation-node",
                            "value": 1.0,
                            "claim_class": "speculative_requires_validation",
                            "validation_required": True,
                            "source_artifact_ids": ["artifact-tool"],
                        },
                    ],
                },
                "confirmatory": {
                    "artifact_id": "artifact-confirmatory",
                    "tests": [
                        {
                            "test_id": "test-1",
                            "question": "Is downstream protein activity altered?",
                            "why_it_matters": "It determines whether the mechanism is active.",
                            "positive_interpretation": "Supports the conditional mechanism.",
                            "negative_interpretation": "Weakens the conditional mechanism.",
                            "priority": "high",
                            "evidence_gap": "Protein status is absent.",
                            "source_claim_ids": ["claim-1"],
                        }
                    ],
                    "must_not_assume": ["Do not infer pathway activity from copy number alone."],
                },
                "tumor_behavior": {
                    "artifact_id": "artifact-tumor",
                    "state_evidence": [
                        {
                            "state_label": "proliferative",
                            "supporting_findings": ["finding-1"],
                            "graph_support": ["edge-1"],
                            "tool_support": ["artifact-tool"],
                            "medea_support": ["artifact-medea"],
                            "evidence_class": "model_derived_hypothesis",
                            "uncertainty": "No longitudinal sample is available.",
                            "validation_needed": True,
                        }
                    ],
                    "transition_hypotheses": [
                        {
                            "from_state": "proliferative",
                            "to_state": "stress_adapted_survival",
                            "rationale": "The case evidence supports a reviewable stress-survival hypothesis.",
                            "supporting_artifacts": ["artifact-extraction", "artifact-tool"],
                            "confidence_label": "low",
                            "validation_status": "needs_review",
                            "hypothesis_generating": True,
                        }
                    ],
                    "limitations": ["No transition probability is estimated."],
                },
                "decision_brief": {
                    "artifact_id": "artifact-decision-brief",
                    "clinical_decision_summary": "GENE1 loss supports a reviewable tumor behavior signal; treatment logic requires clinician validation and additional biomarker confirmation.",
                    "current_tumor_state": {
                        "dominant_drivers": ["GENE1 copy-number loss"],
                        "active_pathways": ["cell-cycle checkpoint context"],
                        "co_drivers": [],
                        "actionable_alterations": ["GENE1 copy-number loss"],
                        "resistance_or_uncertain_alterations": [],
                        "immune_and_repair_context": [],
                        "missing_data": ["protein-level confirmation"],
                        "source_artifact_ids": ["artifact-extraction", "artifact-graph"],
                        "confidence": "needs_review",
                    },
                    "actionable_biology": [
                        {
                            "biology": "cell-cycle checkpoint context",
                            "alteration_or_marker": "GENE1 copy-number loss",
                            "actionability": "insufficient_evidence",
                            "evidence_level": "source-backed hypothesis requiring review",
                            "rationale": "The uploaded report contains a GENE1 loss event with graph context.",
                            "uncertainty": "Protein-level confirmation is absent.",
                            "source_artifact_ids": ["artifact-extraction", "artifact-graph"],
                            "confidence": "needs_review",
                        }
                    ],
                    "ranked_treatment_options": [
                        {
                            "rank": 1,
                            "therapy_name_or_class": "cell-cycle pathway clinical trial category",
                            "clinical_use": "trial_option",
                            "therapy_class": "cell-cycle pathway context",
                            "matched_biomarkers": ["GENE1"],
                            "why_it_fits": "It maps to the report-backed pathway context but needs validation.",
                            "evidence_level": "trial-context hypothesis requiring review",
                            "resistance_risks": ["bypass signaling"],
                            "required_before_use_tests": ["IHC", "tissue_NGS"],
                            "limitations": ["No guideline-supported therapy is asserted from this fixture."],
                            "source_artifact_ids": ["artifact-matrix", "artifact-tool"],
                            "confidence": "needs_review",
                        }
                    ],
                    "treatment_pressure_map": [
                        {
                            "therapy_name_or_class": "cell-cycle pathway clinical trial category",
                            "target_or_pathway": "cell-cycle checkpoint context",
                            "why_it_fits": "The pathway is connected to the source-backed finding.",
                            "selective_pressure": "Potential pathway-directed pressure could select for bypass signaling.",
                            "likely_escape_routes": ["bypass signaling"],
                            "biomarkers_to_watch": ["GENE1", "downstream protein state"],
                            "evidence_basis": ["artifact-matrix", "artifact-sankey"],
                            "source_artifact_ids": ["artifact-matrix", "artifact-sankey"],
                            "confidence": "needs_review",
                        }
                    ],
                    "resistance_forecast": [
                        {
                            "escape_route": "bypass_signaling",
                            "description": "Monitor for bypass pathway activation if treatment pressure targets the pathway context.",
                            "associated_treatment_pressure": "cell-cycle pathway pressure",
                            "supporting_evidence": ["artifact-sankey", "artifact-tumor"],
                            "biomarkers_to_monitor": ["GENE1", "protein activity"],
                            "source_artifact_ids": ["artifact-sankey", "artifact-tumor"],
                            "confidence": "needs_review",
                        }
                    ],
                    "biomarker_watch_list": [
                        {
                            "biomarker": "GENE1",
                            "alteration_type": "copy_number_loss",
                            "why_watch": "It anchors the current pathway hypothesis.",
                            "associated_treatment_pressure": "cell-cycle pathway pressure",
                            "preferred_test": "tissue_NGS",
                            "trigger": "before switching systemic therapy or at progression",
                            "priority": "high",
                            "source_artifact_ids": ["artifact-extraction"],
                        }
                    ],
                    "retesting_triggers": [
                        {
                            "clinical_event": "radiographic progression",
                            "recommended_test": "tissue_NGS",
                            "rationale": "Progression can change molecular context and reveal resistant subclones.",
                            "what_result_changes": "A new driver, CNV, fusion, or transformation signal would change review priorities.",
                            "urgency": "high",
                            "source_artifact_ids": ["artifact-confirmatory", "artifact-tumor"],
                        }
                    ],
                    "next_test_recommendations": [
                        {
                            "test_type": "IHC",
                            "timing": "before using the pathway hypothesis for a clinical decision",
                            "rationale": "Protein-level confirmation is the main missing evidence.",
                            "biomarkers_or_questions": ["downstream protein state"],
                            "result_that_would_change_management": "Confirmed protein activity would increase confidence in the pathway review.",
                            "limitations": ["IHC does not replace full molecular re-profiling at progression."],
                            "source_artifact_ids": ["artifact-confirmatory"],
                            "priority": "high",
                        }
                    ],
                    "translational_assessment": {
                        "artifact_id": "artifact-translational-assessment",
                        "target_relevance": {
                            "question_key": "target_relevance",
                            "question": "Is the target actually relevant to this tumor's behavior?",
                            "answer": "GENE1 loss is tied to the staged checkpoint behavior hypothesis, but protein confirmation is needed.",
                            "status": "partially_supported",
                            "evidence_strength": "moderate",
                            "supporting_evidence": ["GENE1 loss maps to checkpoint context in the staged brief."],
                            "unresolved_evidence": ["Protein-level confirmation is missing."],
                            "validation_next": ["Confirm downstream protein state."],
                            "source_artifact_ids": ["artifact-extraction", "artifact-graph"],
                            "confidence": "needs_review"
                        },
                        "biomarker_evidence": {
                            "question_key": "biomarker_evidence",
                            "question": "Does the biomarker evidence support action, or is it weak/incomplete?",
                            "answer": "The evidence supports trial-category review only; it is not a guideline-supported treatment claim in this fixture.",
                            "status": "weak_or_incomplete",
                            "evidence_strength": "weak",
                            "supporting_evidence": ["Ranked treatment option is trial_option."],
                            "unresolved_evidence": ["No guideline-supported therapy is asserted."],
                            "validation_next": ["Resolve confirmatory protein and pathway evidence."],
                            "source_artifact_ids": ["artifact-matrix", "artifact-tool"],
                            "confidence": "needs_review"
                        },
                        "resistance_mechanisms": {
                            "question_key": "resistance_mechanisms",
                            "question": "Are resistance mechanisms already present or likely to emerge?",
                            "answer": "Bypass signaling is a likely watch item under pathway pressure.",
                            "status": "supported",
                            "evidence_strength": "moderate",
                            "supporting_evidence": ["Resistance forecast surfaces bypass signaling."],
                            "unresolved_evidence": [],
                            "validation_next": ["Monitor GENE1 and downstream protein activity at progression."],
                            "source_artifact_ids": ["artifact-sankey", "artifact-tumor"],
                            "confidence": "needs_review"
                        },
                        "patient_population_alignment": {
                            "question_key": "patient_population_alignment",
                            "question": "Is the patient population aligned with the evidence behind the treatment?",
                            "answer": "Population alignment is unresolved from the uploaded NGS-derived fixture alone.",
                            "status": "unresolved",
                            "evidence_strength": "unresolved",
                            "supporting_evidence": [],
                            "unresolved_evidence": ["Stage, line of therapy, prior treatments, and cohort/label context are missing."],
                            "validation_next": ["Confirm disease setting, line of therapy, and evidence cohort fit."],
                            "source_artifact_ids": [],
                            "confidence": "needs_review"
                        },
                        "evidence_resolution": {
                            "question_key": "evidence_resolution",
                            "question": "What evidence is strong, what is unresolved, and what needs validation next?",
                            "answer": "The strongest evidence is report-backed GENE1 loss; protein state and population fit remain unresolved.",
                            "status": "needs_validation",
                            "evidence_strength": "moderate",
                            "supporting_evidence": ["Report-backed finding and confirmatory test plan are present."],
                            "unresolved_evidence": ["Protein-level confirmation and population fit are missing."],
                            "validation_next": ["Run IHC or another appropriate protein/pathway assay before clinical use."],
                            "source_artifact_ids": ["artifact-extraction", "artifact-confirmatory"],
                            "confidence": "needs_review"
                        },
                        "unresolved_evidence": ["Population alignment and protein-level confirmation remain unresolved."]
                    },
                    "evidence_limitations": [
                        {
                            "limitation": "Protein-level confirmation is missing.",
                            "impact": "Treatment fit remains review-only.",
                            "needed_resolution": "Run IHC or another appropriate biomarker assay.",
                            "source_artifact_ids": ["artifact-confirmatory"],
                        }
                    ],
                    "source_artifact_ids": ["artifact-extraction", "artifact-context", "artifact-matrix", "artifact-tumor"],
                    "source_chunk_ids": ["chunk-1"],
                    "validation_status": "needs_review",
                },
                "claims": [
                    {
                        "claim_id": "claim-1",
                        "claim": "GENE1 loss supports a checkpoint-disruption hypothesis.",
                        "claim_class": "model_derived_hypothesis",
                        "source_artifact_ids": ["artifact-extraction", "artifact-graph"],
                        "evidence_source": "report plus OptimusKG",
                        "relevance": "Explains a reviewable biological axis.",
                        "limitations": "Requires protein confirmation.",
                        "validation_status": "needs_review",
                    }
                ],
                "narrative": {
                    "artifact_id": "artifact-narrative",
                    "markdown": "The report supports a source-backed checkpoint-disruption hypothesis.",
                    "source_artifact_ids": ["artifact-extraction", "artifact-tumor"],
                    "safety_note": "Research support only; human validation is required.",
                },
                "narrative_containment": {
                    "artifact_id": "artifact-containment",
                    "narrative_artifact_id": "artifact-narrative",
                    "source_artifact_ids": ["artifact-extraction", "artifact-tumor"],
                    "unsupported_findings": [],
                    "passed": True,
                },
                "validation_decisions": [],
                "provenance": [
                    {
                        "artifact_id": "artifact-extraction",
                        "artifact_type": "ReportExtractionOutput",
                        "schema_name": "ReportExtractionOutput",
                        "model_name": "local-model",
                        "prompt_hash": "prompt-hash",
                        "schema_hash": "schema-hash",
                        "source_file_id": "source-ui",
                        "source_chunk_ids": ["chunk-1"],
                        "source_artifact_ids": [],
                        "created_at": now,
                        "validation_status": "needs_review",
                        "generation_status": "generated",
                    }
                ],
                "ledger_events": [
                    {
                        "event_id": "event-1",
                        "event_type": "report_extraction_succeeded",
                        "case_id": "case-ui",
                        "session_id": "session-ui",
                        "artifact_id": "artifact-extraction",
                        "source_file_id": "source-ui",
                        "created_at": now,
                        "details": {"stage": "report_extraction", "status": "succeeded"},
                    }
                ],
            },
        }
    )


def test_build_clinical_panels_uses_persisted_packet_content() -> None:
    panels = build_clinical_panel_data(_packet())
    assert panels.findings_rows[0][0] == "GENE1"
    assert panels.entity_rows[0][2] == "GENE1"
    assert panels.decision_summary_markdown
    assert "Treat now" in panels.decision_snapshot_html
    assert "cell-cycle pathway clinical trial category" in panels.decision_snapshot_html
    assert "Population fit" in panels.decision_snapshot_html
    assert panels.translational_check_rows[0][0].startswith("Is the target")
    assert panels.matrix_rows[0][1] == "Checkpoint-axis review"
    assert panels.tool_evidence_rows[0][3] == "12345678"
    assert "Checkpoint-state pressure" in panels.medea_markdown
    assert panels.claim_choices == ["claim-1"]
    assert "cell-cycle pathway clinical trial category" in list(panels.sankey_figure.data[0].node.label)


def test_clinical_panels_reject_missing_required_artifact() -> None:
    packet = _packet()
    invalid_bundle = packet.bundle.model_copy(update={"matrix": None})
    invalid_packet = packet.model_copy(update={"bundle": invalid_bundle})
    with pytest.raises(ClinicalPanelRenderError, match="matrix"):
        build_clinical_panel_data(invalid_packet)


def test_clinical_panels_reject_failed_narrative_containment() -> None:
    packet = _packet()
    failed = packet.bundle.narrative_containment.model_copy(update={"passed": False})
    invalid_packet = packet.model_copy(
        update={"bundle": packet.bundle.model_copy(update={"narrative_containment": failed})}
    )
    with pytest.raises(ClinicalPanelRenderError, match="containment"):
        build_clinical_panel_data(invalid_packet)


def test_sankey_uses_decision_brief_not_old_artifact_links() -> None:
    packet = _packet()
    bad_link = packet.bundle.sankey.links[0].model_copy(
        update={"target_node_id": "missing-node"}
    )
    bad_sankey = packet.bundle.sankey.model_copy(update={"links": [bad_link]})
    invalid_packet = packet.model_copy(
        update={"bundle": packet.bundle.model_copy(update={"sankey": bad_sankey})}
    )
    figure = build_mechanism_sankey_figure(invalid_packet)
    assert "cell-cycle pathway clinical trial category" in list(figure.data[0].node.label)


def test_persisted_packet_export_writes_validated_api_packet(tmp_path: Path) -> None:
    path = write_persisted_review_packet(_packet(), tmp_path)
    loaded = ReviewPacketExport.model_validate_json(path.read_text(encoding="utf-8"))
    assert loaded.session_id == "session-ui"
    assert loaded.bundle.claims[0].claim_id == "claim-1"




def test_decision_brief_export_writes_focused_validated_artifact(
    tmp_path: Path,
) -> None:
    brief = _packet().bundle.decision_brief
    assert brief is not None
    path = write_persisted_decision_brief(brief, tmp_path)
    exported = path.read_text(encoding="utf-8")
    assert path.name == "translume-decision-brief-artifact-decision-brief.json"
    assert "ranked_treatment_options" in exported
    assert "artifact-extraction" in exported
    assert "ReviewPacketExport" not in exported


def test_api_client_fetches_focused_decision_brief_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    brief = _packet().bundle.decision_brief
    assert brief is not None
    client = TranslumeAPIClient(
        TranslumeAPIClientConfig(base_url="http://translume-api:8080")
    )

    def fake_request(
        method: str,
        path: str,
        *,
        timeout: float,
        **_kwargs: object,
    ) -> httpx.Response:
        assert method == "GET"
        assert path == "/api/v1/review-packets/session-ui/decision-brief"
        assert timeout == client._config.request_timeout_seconds
        return httpx.Response(200, json=brief.model_dump(mode="json"))

    monkeypatch.setattr(client, "_request", fake_request)
    fetched = client.fetch_decision_brief(" session-ui ")
    assert fetched.artifact_id == "artifact-decision-brief"
    assert fetched.ranked_treatment_options[0].clinical_use == "trial_option"


def test_build_api_client_uses_one_hour_process_timeout_by_default() -> None:
    client = build_api_client(
        {
            "TRANSLUME_API_BASE_URL": "http://translume-api:8080",
        }
    )

    assert client._config.request_timeout_seconds == 120.0
    assert client._config.process_timeout_seconds == 3600.0
    assert client._config.downstream_timeout_seconds == 7200.0


def test_build_api_client_allows_process_timeout_override() -> None:
    client = build_api_client(
        {
            "TRANSLUME_API_BASE_URL": "http://translume-api:8080",
            "TRANSLUME_UI_PROCESS_TIMEOUT_SECONDS": "42",
        }
    )

    assert client._config.process_timeout_seconds == 42.0


def test_download_persisted_decision_brief_uses_focused_endpoint(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from translume_ui.app import download_persisted_decision_brief

    brief = _packet().bundle.decision_brief
    assert brief is not None

    class TestOnlyClient:
        def fetch_decision_brief(self, session_id: str):
            assert session_id == "session-ui"
            return brief

    monkeypatch.setattr(
        "translume_ui.app.build_api_client",
        lambda _environment: TestOnlyClient(),
    )
    monkeypatch.setattr(
        "translume_ui.app.export_root_from_environment",
        lambda _environment: tmp_path,
    )
    output_path, status_html = download_persisted_decision_brief("session-ui")
    assert output_path is not None
    assert Path(output_path).exists()
    assert "decision brief export is ready" in status_html
    assert "clinical_decision_summary" in Path(output_path).read_text(
        encoding="utf-8"
    )


def test_gradio_app_exposes_clinical_panel_labels() -> None:
    app = build_app()
    config = str(app.get_config_file())
    assert config.index("Pathway analysis") < config.index("Clinical review")
    assert "Translume tumor-behavior report loaded" not in config
    assert "Upload a report to begin a real persisted review workflow" not in config
    assert "Case summary" not in config
    assert "No persisted case is loaded" not in config
    assert "Oncologist decision brief" in config
    assert "Fast decision snapshot" in config
    assert "Fetch decision brief JSON" in config
    assert "Decision brief JSON download" in config
    assert "Molecular-fit review matrix" in config
    assert "Five translational checks" in config
    assert "Case-derived state evidence" in config
    assert "Artifact provenance" in config
    assert "Exact persisted review packet JSON" in config
    assert "Diagnosis" in config
    assert "Load completed session" in config
    assert "Completed session ZIP" in config
    assert "Load saved pathway session" in config
    assert "session-import-status" in config
    assert "workflow-error" in config
    assert "pathway-processing-status" in config
    assert "Tumor board causal summary" in config


def test_process_handler_renders_persisted_export_not_unpersisted_response(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from translume_ui.app import process_pdf

    processed = _packet()
    persisted_extraction = processed.bundle.extraction.model_copy(
        update={"disease": "Persisted disease context"}
    )
    persisted = processed.model_copy(
        update={
            "bundle": processed.bundle.model_copy(
                update={"extraction": persisted_extraction}
            )
        }
    )

    class TestOnlyClient:
        def process_report(self, file_path: Path, report_type: str) -> ReviewPacketExport:
            assert file_path.name == "report.pdf"
            assert report_type == "NGS"
            return processed

        def fetch_review_packet(self, session_id: str) -> ReviewPacketExport:
            assert session_id == "session-ui"
            return persisted

        def run_downstream_analysis(
            self,
            session_id: str,
            diagnosis: str,
        ) -> DownstreamAnalysisResult:
            assert session_id == "session-ui"
            assert diagnosis == "Example sarcoma"
            return DownstreamAnalysisResult.model_validate(
                {
                    "session_id": session_id,
                    "diagnosis": diagnosis,
                    "precision_run": {
                        "session_id": session_id,
                        "run_id": "run-ui",
                        "run_directory": "session-ui/precision/run-ui",
                        "trial_prescreens_path": "session-ui/trial.json",
                    },
                    "pathway_analysis_markdown": "# Pathway",
                    "research_memo_markdown": "# Research",
                    "tumor_board_summary_markdown": "# Tumor board",
                    "pathway_analysis_path": "session-ui/pathway.md",
                    "research_memo_path": "session-ui/research.md",
                    "tumor_board_summary_path": "session-ui/summary.md",
                }
            )

    monkeypatch.setattr(
        "translume_ui.app.build_api_client",
        lambda _environment: TestOnlyClient(),
    )
    pdf = tmp_path / "report.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    outputs = process_pdf(str(pdf), "NGS", "Example sarcoma")
    assert outputs[0]["visible"] is False
    assert outputs[1]["visible"] is False
    assert outputs[2] == "session-ui"
    assert any(
        "Persisted disease context" in output
        for output in outputs
        if isinstance(output, str)
    )
    assert outputs[-3] == "# Pathway"
    assert outputs[-2] == "# Research"
    assert outputs[-1] == "# Tumor board"


def test_process_handler_shows_top_panel_for_missing_input() -> None:
    from translume_ui.app import process_pdf

    outputs = process_pdf(None, "NGS", "Example sarcoma")

    assert outputs[0]["visible"] is True
    assert "Upload a PDF before processing" in outputs[0]["value"]
    assert outputs[1]["visible"] is True
    assert "Upload a PDF before processing" in outputs[1]["value"]


def test_process_outputs_show_top_panel_for_downstream_failure() -> None:
    from translume_ui.app import _process_outputs

    outputs = _process_outputs(
        "session-ui",
        build_clinical_panel_data(_packet()),
        None,
        '<div class="translume-error">Downstream failed.</div>',
    )

    assert outputs[0]["visible"] is True
    assert "Downstream failed" in outputs[0]["value"]
    assert outputs[1]["visible"] is True
    assert "Downstream failed" in outputs[1]["value"]
    assert "Downstream failed" in outputs[-3]
