from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from translume_schemas.export import ReviewPacketExport
from translume_ui.api_client import write_persisted_review_packet
from translume_ui.app import build_app
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
                            "limitations": "Not treatment directing.",
                            "required_validation": "Confirm downstream protein state.",
                            "not_a_recommendation": True,
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
    assert panels.matrix_rows[0][1] == "Checkpoint-axis review"
    assert panels.tool_evidence_rows[0][3] == "12345678"
    assert "Checkpoint-state pressure" in panels.medea_markdown
    assert panels.claim_choices == ["claim-1"]
    assert "Example sarcoma" in panels.case_summary_html
    assert panels.sankey_figure.data[0].node.label[0] == "GENE1 loss"


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


def test_sankey_rejects_unknown_node_references() -> None:
    packet = _packet()
    bad_link = packet.bundle.sankey.links[0].model_copy(
        update={"target_node_id": "missing-node"}
    )
    bad_sankey = packet.bundle.sankey.model_copy(update={"links": [bad_link]})
    invalid_packet = packet.model_copy(
        update={"bundle": packet.bundle.model_copy(update={"sankey": bad_sankey})}
    )
    with pytest.raises(ClinicalPanelRenderError, match="unknown target node"):
        build_mechanism_sankey_figure(invalid_packet)


def test_persisted_packet_export_writes_validated_api_packet(tmp_path: Path) -> None:
    path = write_persisted_review_packet(_packet(), tmp_path)
    loaded = ReviewPacketExport.model_validate_json(path.read_text(encoding="utf-8"))
    assert loaded.session_id == "session-ui"
    assert loaded.bundle.claims[0].claim_id == "claim-1"


def test_gradio_app_exposes_clinical_panel_labels() -> None:
    app = build_app()
    config = str(app.get_config_file())
    assert "Molecular-fit review matrix" in config
    assert "Mechanism Sankey" in config
    assert "Case-derived state evidence" in config
    assert "Artifact provenance" in config
    assert "Exact persisted review packet JSON" in config


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

    monkeypatch.setattr(
        "translume_ui.app.build_api_client",
        lambda _environment: TestOnlyClient(),
    )
    pdf = tmp_path / "report.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    outputs = process_pdf(str(pdf), "NGS")
    assert outputs[1] == "session-ui"
    assert "Persisted disease context" in outputs[2]
    assert "Example sarcoma" not in outputs[2]
