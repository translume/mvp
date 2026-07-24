from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from translume_core.evaluation.decision_brief import (
    evaluate_decision_brief_against_fixture,
    evaluate_review_packet_against_fixture,
    load_decision_brief_evaluation_fixture,
)
from translume_schemas.decision_brief import (
    ActionableBiologyItem,
    BiomarkerWatchItem,
    CurrentTumorState,
    EvidenceLimitation,
    NextTestRecommendation,
    OncologistDecisionBrief,
    RankedTreatmentOption,
    ResistanceForecastItem,
    RetestingTrigger,
    TreatmentPressureMapRow,
)
from translume_schemas.document import DocumentChunk
from translume_schemas.export import ClinicalArtifactBundle, ReviewPacketExport
from translume_schemas.extraction import MolecularFinding, ReportExtractionOutput


FIXTURE_PATH = Path(
    "tests/fixtures/decision_brief/ngs_lung_egfr_resistance_fixture.json"
)


def _load_evaluation_script():
    script_path = Path("scripts/evaluate_decision_brief.py")
    spec = importlib.util.spec_from_file_location(
        "evaluate_decision_brief",
        script_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load evaluate_decision_brief.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
_SOURCE_IDS = ["artifact_extraction", "artifact_graph"]
_CHUNK_IDS = ["chunk_egfr"]


def test_evaluate_decision_brief_passes_expected_fixture() -> None:
    fixture = _load_fixture()
    report = evaluate_decision_brief_against_fixture(
        brief=_decision_brief(),
        fixture=fixture,
    )

    assert report.passed
    assert report.metrics.expected_signal_recall == 1.0
    assert report.metrics.evidence_coverage == 1.0
    assert report.failure_reasons == []


def test_evaluate_review_packet_uses_extraction_for_report_findings() -> None:
    fixture = _load_fixture()
    report = evaluate_review_packet_against_fixture(
        packet=_review_packet(),
        fixture=fixture,
    )

    assert report.passed
    extraction_signal = next(
        item
        for item in report.expected_signal_results
        if item.signal_id == "finding_egfr_l858r"
    )
    assert "extraction" in extraction_signal.matched_sections


def test_evaluate_decision_brief_flags_missing_expected_signal() -> None:
    fixture = _load_fixture()
    brief = _decision_brief().model_copy(update={"biomarker_watch_list": []})

    report = evaluate_decision_brief_against_fixture(brief=brief, fixture=fixture)

    assert not report.passed
    assert any("biomarker_met" in reason for reason in report.failure_reasons)
    assert report.metrics.expected_signal_recall < 1.0


def test_evaluate_decision_brief_flags_forbidden_signal() -> None:
    fixture = _load_fixture()
    brief = _decision_brief().model_copy(
        update={
            "clinical_decision_summary": (
                "EGFR L858R with MET monitoring; ALK fusion was also introduced."
            )
        }
    )

    report = evaluate_decision_brief_against_fixture(brief=brief, fixture=fixture)

    assert not report.passed
    assert [hit.signal_id for hit in report.forbidden_signal_hits] == ["forbid_alk"]
    assert any("forbid_alk" in reason for reason in report.failure_reasons)


def test_evaluate_decision_brief_flags_unsupported_certainty() -> None:
    fixture = _load_fixture()
    brief = _decision_brief().model_copy(
        update={
            "clinical_decision_summary": (
                "EGFR L858R will respond to an EGFR inhibitor."
            )
        }
    )

    report = evaluate_decision_brief_against_fixture(brief=brief, fixture=fixture)

    assert not report.passed
    assert [hit.phrase for hit in report.unsupported_certainty_hits] == [
        "will respond"
    ]


def test_evaluate_decision_brief_flags_ungrounded_rows() -> None:
    fixture = _load_fixture()
    option = _decision_brief().ranked_treatment_options[0].model_copy(
        update={"source_artifact_ids": [], "unresolved_evidence": []}
    )
    brief = _decision_brief().model_copy(update={"ranked_treatment_options": [option]})

    report = evaluate_decision_brief_against_fixture(brief=brief, fixture=fixture)

    assert not report.passed
    assert report.ungrounded_rows[0].section == "ranked_treatment_options"
    assert report.metrics.evidence_coverage < 1.0


def test_cli_writes_evaluation_report(tmp_path: Path, monkeypatch) -> None:
    brief_path = tmp_path / "brief.json"
    output_path = tmp_path / "eval.json"
    brief_path.write_text(
        json.dumps(_decision_brief().model_dump(mode="json")),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "evaluate_decision_brief.py",
            "--brief",
            str(brief_path),
            "--fixture",
            str(FIXTURE_PATH),
            "--output",
            str(output_path),
        ],
    )

    exit_code = _load_evaluation_script().main()
    report = json.loads(output_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert report["passed"] is True
    assert report["metrics"]["expected_signal_recall"] == 1.0


def _load_fixture():
    return load_decision_brief_evaluation_fixture(
        json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    )


def _decision_brief() -> OncologistDecisionBrief:
    return OncologistDecisionBrief(
        artifact_id="artifact_decision_brief",
        clinical_decision_summary=(
            "Current tumor state centers on EGFR L858R. The top staged "
            "treatment logic is EGFR inhibitor with MET amplification "
            "monitoring, ctDNA re-testing, and clinician review."
        ),
        current_tumor_state=CurrentTumorState(
            dominant_drivers=["EGFR L858R"],
            active_pathways=["EGFR signaling"],
            co_drivers=["TP53 alteration"],
            actionable_alterations=["EGFR L858R"],
            resistance_or_uncertain_alterations=["MET amplification watch item"],
            immune_and_repair_context=["MSI stable"],
            missing_data=["longitudinal resistance sample"],
            source_artifact_ids=_SOURCE_IDS,
            confidence="moderate",
        ),
        actionable_biology=[
            ActionableBiologyItem(
                biology="EGFR pathway activation",
                alteration_or_marker="EGFR L858R",
                actionability="guideline_supported",
                evidence_level="source-backed decision-support signal",
                rationale="The uploaded report includes EGFR L858R.",
                uncertainty="Therapy selection requires clinician review.",
                source_artifact_ids=_SOURCE_IDS,
                confidence="moderate",
            )
        ],
        ranked_treatment_options=[
            RankedTreatmentOption(
                rank=1,
                therapy_name_or_class="EGFR inhibitor",
                clinical_use="guideline_supported",
                therapy_class="EGFR-targeted therapy",
                matched_biomarkers=["EGFR L858R"],
                why_it_fits="EGFR L858R is present in the uploaded report.",
                evidence_level="source-backed decision-support signal",
                resistance_risks=["MET amplification"],
                required_before_use_tests=["confirm EGFR L858R report context"],
                limitations=["Final treatment decision requires oncologist review."],
                source_artifact_ids=_SOURCE_IDS,
                confidence="moderate",
            )
        ],
        treatment_pressure_map=[
            TreatmentPressureMapRow(
                therapy_name_or_class="EGFR inhibitor",
                target_or_pathway="EGFR signaling",
                why_it_fits="EGFR L858R supports EGFR pathway treatment logic.",
                selective_pressure="EGFR pressure can select bypass signaling.",
                likely_escape_routes=["MET amplification"],
                biomarkers_to_watch=["MET", "EGFR secondary mutation"],
                evidence_basis=_SOURCE_IDS,
                source_artifact_ids=_SOURCE_IDS,
                confidence="moderate",
            )
        ],
        resistance_forecast=[
            ResistanceForecastItem(
                escape_route="bypass_signaling",
                description="Monitor for MET amplification as an escape route.",
                associated_treatment_pressure="EGFR inhibitor pressure",
                supporting_evidence=_SOURCE_IDS,
                biomarkers_to_monitor=["MET", "EGFR secondary mutation"],
                source_artifact_ids=_SOURCE_IDS,
                confidence="moderate",
            )
        ],
        biomarker_watch_list=[
            BiomarkerWatchItem(
                biomarker="MET",
                alteration_type="amplification",
                why_watch="MET amplification can indicate bypass signaling.",
                associated_treatment_pressure="EGFR inhibitor pressure",
                preferred_test="ctDNA",
                trigger="radiographic progression or therapy switch",
                priority="high",
                source_artifact_ids=_SOURCE_IDS,
            )
        ],
        retesting_triggers=[
            RetestingTrigger(
                clinical_event="radiographic progression",
                recommended_test="ctDNA",
                rationale="ctDNA can surface emerging EGFR or MET resistance signals.",
                what_result_changes="Detected MET amplification or EGFR resistance signal.",
                urgency="high",
                source_artifact_ids=_SOURCE_IDS,
            )
        ],
        next_test_recommendations=[
            NextTestRecommendation(
                test_type="ctDNA",
                timing="at radiographic progression or before next systemic therapy",
                rationale="ctDNA can quickly evaluate EGFR and MET resistance markers.",
                biomarkers_or_questions=["EGFR", "MET amplification"],
                result_that_would_change_management=(
                    "A new resistance signal would guide next-line review."
                ),
                limitations=["Tissue NGS may be needed if ctDNA is negative."],
                source_artifact_ids=_SOURCE_IDS,
                priority="high",
            )
        ],
        evidence_limitations=[
            EvidenceLimitation(
                limitation="No longitudinal progression sample was available.",
                impact="Resistance forecast remains a watch list.",
                needed_resolution="Repeat molecular testing at progression.",
                source_artifact_ids=_SOURCE_IDS,
            )
        ],
        source_artifact_ids=[*_SOURCE_IDS, "artifact_stage"],
        source_chunk_ids=_CHUNK_IDS,
    )


def _review_packet() -> ReviewPacketExport:
    extraction = ReportExtractionOutput(
        artifact_id="artifact_extraction",
        report_type="NGS",
        disease="non-small cell lung cancer",
        specimen="lung biopsy",
        tumor_percentage="40%",
        molecular_findings=[
            MolecularFinding(
                finding_id="finding_egfr_l858r",
                gene="EGFR",
                alteration="L858R",
                alteration_type="SNV",
                source_text="EGFR L858R detected.",
                source_chunk_id="chunk_egfr",
                confidence=0.99,
            )
        ],
        negative_findings=["ALK fusion not detected"],
        assay_limitations=["No longitudinal progression sample."],
        source_file_id="source_file_1",
    )
    return ReviewPacketExport(
        case_id="case_egfr",
        session_id="session_egfr",
        source_file_id="source_file_1",
        chunks=[
            DocumentChunk(
                chunk_id="chunk_egfr",
                case_id="case_egfr",
                session_id="session_egfr",
                source_file_id="source_file_1",
                report_type="NGS",
                page_start=1,
                page_end=1,
                section="Genomic Findings",
                chunk_type="text",
                source_text="EGFR L858R detected.",
                source_block_ids=["block_1"],
                needs_human_review=False,
            )
        ],
        bundle=ClinicalArtifactBundle(
            case_id="case_egfr",
            session_id="session_egfr",
            extraction=extraction,
            decision_brief=_decision_brief(),
        ),
    )
