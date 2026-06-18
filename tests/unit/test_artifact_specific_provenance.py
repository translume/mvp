from __future__ import annotations

from datetime import datetime, timezone

import pytest

from translume_core.provenance.coverage import (
    expected_bundle_artifact_ids,
    require_bundle_provenance_complete,
    source_chunk_ids_from_report_extraction,
)
from translume_core.provenance.provenance import (
    ArtifactProvenanceError,
    build_artifact_provenance,
)
from translume_schemas.export import ClinicalArtifactBundle
from translume_schemas.extraction import MolecularFinding, ReportExtractionOutput


def _extraction() -> ReportExtractionOutput:
    return ReportExtractionOutput(
        artifact_id="artifact_report",
        report_type="NGS",
        source_file_id="source_file_1",
        molecular_findings=[
            MolecularFinding(
                finding_id="finding_mtap",
                gene="MTAP",
                alteration="copy-number loss",
                alteration_type="copy_number_loss",
                confidence=0.9,
                source_chunk_id="chunk_1",
                source_text="MTAP copy-number loss",
                source_page=1,
                needs_human_review=True,
            )
        ],
    )


def _report_provenance(extraction: ReportExtractionOutput):
    return build_artifact_provenance(
        artifact_type="ReportExtractionOutput",
        schema_name="ReportExtractionOutput",
        model_name="local-vllm/test-model",
        prompt_text="source grounded extraction prompt",
        schema_json=ReportExtractionOutput.model_json_schema(),
        source_artifact_ids=[],
        source_chunk_ids=source_chunk_ids_from_report_extraction(extraction),
        source_file_id=extraction.source_file_id,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        artifact_id=extraction.artifact_id,
    )


def test_source_chunk_ids_from_report_extraction_are_ordered_unique() -> None:
    extraction = _extraction().model_copy(
        update={
            "molecular_findings": [
                *_extraction().molecular_findings,
                _extraction().molecular_findings[0].model_copy(update={"finding_id": "finding_2"}),
            ]
        }
    )
    assert source_chunk_ids_from_report_extraction(extraction) == ["chunk_1"]


def test_bundle_provenance_complete_accepts_specific_report_provenance() -> None:
    extraction = _extraction()
    bundle = ClinicalArtifactBundle(
        case_id="case_1",
        session_id="session_1",
        extraction=extraction,
        provenance=[_report_provenance(extraction)],
    )
    assert expected_bundle_artifact_ids(bundle) == {"artifact_report": "ReportExtractionOutput"}
    require_bundle_provenance_complete(bundle)


def test_bundle_provenance_rejects_missing_artifact_provenance() -> None:
    extraction = _extraction()
    bundle = ClinicalArtifactBundle(
        case_id="case_1",
        session_id="session_1",
        extraction=extraction,
        provenance=[],
    )
    with pytest.raises(ArtifactProvenanceError, match="missing provenance"):
        require_bundle_provenance_complete(bundle)


def test_bundle_provenance_rejects_generic_provider_names() -> None:
    extraction = _extraction()
    provenance = _report_provenance(extraction).model_copy(
        update={"model_name": "deterministic_compiler_or_external_provider"}
    )
    bundle = ClinicalArtifactBundle(
        case_id="case_1",
        session_id="session_1",
        extraction=extraction,
        provenance=[provenance],
    )
    with pytest.raises(ArtifactProvenanceError, match="generic model"):
        require_bundle_provenance_complete(bundle)


def test_bundle_provenance_rejects_unknown_extra_records() -> None:
    extraction = _extraction()
    extra = _report_provenance(extraction).model_copy(update={"artifact_id": "artifact_extra"})
    bundle = ClinicalArtifactBundle(
        case_id="case_1",
        session_id="session_1",
        extraction=extraction,
        provenance=[_report_provenance(extraction), extra],
    )
    with pytest.raises(ArtifactProvenanceError, match="unknown artifact"):
        require_bundle_provenance_complete(bundle)
