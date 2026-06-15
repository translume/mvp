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
