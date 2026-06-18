from __future__ import annotations

from datetime import datetime, timezone

import pytest

from translume_core.export.review_packet import build_review_packet_export
from translume_core.provenance.provenance import build_artifact_provenance
from translume_core.safety.language import SafetyLanguageError, validate_safety_language
from translume_schemas.export import ClinicalArtifactBundle
from translume_schemas.extraction import ReportExtractionOutput


def test_safety_language_rejects_treatment_direction() -> None:
    with pytest.raises(SafetyLanguageError):
        validate_safety_language("This is the recommended treatment.", ["recommended treatment"])
    validate_safety_language("This is a molecular fit for expert review.", ["recommended treatment"])


def test_provenance_hashes_prompt_and_schema() -> None:
    prov = build_artifact_provenance(
        "report_extraction", "ReportExtractionOutput", "local", "prompt", {"type": "object"}, [],
        datetime(2026, 1, 1, tzinfo=timezone.utc), artifact_id="artifact_a",
    )
    assert prov.prompt_hash is not None
    assert prov.schema_hash is not None


def test_review_packet_export_is_serializable() -> None:
    extraction = ReportExtractionOutput(artifact_id="artifact_e", report_type="NGS", molecular_findings=[], source_file_id="file_a")
    bundle = ClinicalArtifactBundle(case_id="case", session_id="sess", extraction=extraction)
    export = build_review_packet_export(bundle, [], "file_a")
    assert export.model_dump()["source_file_id"] == "file_a"

from translume_core.safety.containment import (
    NarrativeContainmentError,
    require_narrative_fact_containment,
    validate_narrative_fact_containment,
)
from translume_schemas.export import ClinicalNarrativeCompilerOutput
from translume_schemas.extraction import MolecularFinding


def _containment_bundle() -> ClinicalArtifactBundle:
    extraction = ReportExtractionOutput(
        artifact_id="artifact_report",
        report_type="NGS",
        disease="Source-backed sarcoma context",
        molecular_findings=[
            MolecularFinding(
                finding_id="finding_chek2",
                gene="CHEK2",
                alteration="splice-region loss-of-function",
                alteration_type="variant",
                confidence=0.9,
                source_text="CHEK2 splice-region loss-of-function",
                source_chunk_id="chunk_1",
                source_page=1,
                needs_human_review=True,
            )
        ],
        source_file_id="source_file_1",
    )
    return ClinicalArtifactBundle(
        case_id="case_1",
        session_id="session_1",
        extraction=extraction,
    )


def test_narrative_containment_accepts_source_backed_terms() -> None:
    bundle = _containment_bundle()
    narrative = ClinicalNarrativeCompilerOutput(
        artifact_id="artifact_narrative",
        markdown="CHEK2 appears in the source-backed molecular findings for review.",
        source_artifact_ids=["artifact_report"],
        safety_note="Research support only; not a diagnosis or treatment recommendation.",
    )
    report = require_narrative_fact_containment(narrative, bundle)
    assert report.passed is True
    assert report.unsupported_findings == []


def test_narrative_containment_rejects_unsupported_gene_and_drug_terms() -> None:
    bundle = _containment_bundle()
    narrative = ClinicalNarrativeCompilerOutput(
        artifact_id="artifact_narrative",
        markdown="EGFR and trametinib appear here but are absent from the source artifacts.",
        source_artifact_ids=["artifact_report"],
        safety_note="Research support only; not a diagnosis or treatment recommendation.",
    )
    report = validate_narrative_fact_containment(narrative, bundle)
    assert {finding.term for finding in report.unsupported_findings} >= {"EGFR", "trametinib"}
    with pytest.raises(NarrativeContainmentError):
        require_narrative_fact_containment(narrative, bundle)


def test_narrative_containment_rejects_unknown_source_artifact_id() -> None:
    bundle = _containment_bundle()
    narrative = ClinicalNarrativeCompilerOutput(
        artifact_id="artifact_narrative",
        markdown="CHEK2 appears in the source-backed molecular findings for review.",
        source_artifact_ids=["artifact_missing"],
        safety_note="Research support only; not a diagnosis or treatment recommendation.",
    )
    with pytest.raises(NarrativeContainmentError):
        require_narrative_fact_containment(narrative, bundle)
