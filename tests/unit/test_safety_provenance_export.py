from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from translume_core.compiler.structured_model_artifacts import (
    StructuredArtifactGenerationError,
    generate_clinical_narrative_with_model,
)
from translume_core.export.review_packet import build_review_packet_export
from translume_core.provenance.provenance import build_artifact_provenance
from translume_core.safety.language import SafetyLanguageError, validate_safety_language
from translume_core.safety.containment import (
    NarrativeContainmentError,
    require_narrative_fact_containment,
    validate_narrative_fact_containment,
)
from translume_schemas.decision_brief import OncologistDecisionBrief
from translume_schemas.export import (
    ClinicalArtifactBundle,
    ClinicalNarrativeCompilerOutput,
)
from translume_schemas.extraction import MolecularFinding, ReportExtractionOutput


def test_safety_language_rejects_unsupported_certainty() -> None:
    banned = ["will respond", "will be cured", "guaranteed", "definitive cure"]
    with pytest.raises(SafetyLanguageError):
        validate_safety_language("This patient will respond.", banned)
    validate_safety_language("This is a treatment option for clinician review.", banned)


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



class NarrativeModelProvider:
    """Test-only structured-output model provider for narrative generation."""

    def __init__(
        self,
        markdown: str,
        source_artifact_ids: list[str] | None = None,
    ) -> None:
        self.markdown = markdown
        self.source_artifact_ids = (
            ["artifact_report"]
            if source_artifact_ids is None
            else list(source_artifact_ids)
        )

    async def structured_completion(
        self,
        *,
        model_name: str,
        system_prompt: str,
        user_prompt: str,
        schema_name: str,
        json_schema: dict[str, object],
    ) -> dict[str, object]:
        return {
            "artifact_id": _planned_artifact_id(user_prompt),
            "markdown": self.markdown,
            "source_artifact_ids": self.source_artifact_ids,
            "safety_note": (
                "Clinician decision support only; no certain response, cure, "
                "survival benefit, or deterministic outcome is claimed."
            ),
        }


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
        safety_note="Clinician decision support only; no certain response, cure, survival benefit, or deterministic outcome is claimed.",
    )
    report = require_narrative_fact_containment(narrative, bundle)
    assert report.passed is True
    assert report.unsupported_findings == []


@pytest.mark.parametrize(
    "administrative_value",
    ["N/A", "NA", "not applicable", "not available", "unknown"],
)
def test_narrative_containment_allows_administrative_missing_values(
    administrative_value: str,
) -> None:
    """Administrative missing-value notation must not become a clinical fact."""
    bundle = _containment_bundle()
    narrative = ClinicalNarrativeCompilerOutput(
        artifact_id="artifact_narrative",
        markdown=f"Longitudinal response status: {administrative_value}.",
        source_artifact_ids=["artifact_report"],
        safety_note="Clinician decision support only.",
    )

    report = require_narrative_fact_containment(narrative, bundle)

    assert report.passed is True
    assert report.unsupported_findings == []


def test_narrative_containment_ignores_ordinary_slash_notation() -> None:
    """A slash alone must not classify ordinary prose as biomedical."""
    bundle = _containment_bundle()
    narrative = ClinicalNarrativeCompilerOutput(
        artifact_id="artifact_narrative",
        markdown="Use input/output review and/or clinician confirmation.",
        source_artifact_ids=["artifact_report"],
        safety_note="Clinician decision support only.",
    )

    report = require_narrative_fact_containment(narrative, bundle)

    assert report.passed is True
    assert report.unsupported_findings == []


def test_narrative_containment_rejects_unsupported_biomedical_slash_term() -> None:
    """Preserve enforcement for unsupported symbol-anchored slash terms."""
    bundle = _containment_bundle()
    narrative = ClinicalNarrativeCompilerOutput(
        artifact_id="artifact_narrative",
        markdown="BRAF/MEK appears here but is absent from the source artifacts.",
        source_artifact_ids=["artifact_report"],
        safety_note="Clinician decision support only.",
    )

    report = validate_narrative_fact_containment(narrative, bundle)

    assert "BRAF/MEK" in {
        finding.term for finding in report.unsupported_findings
    }


def test_narrative_containment_allows_source_backed_biomedical_slash_term() -> None:
    """Allow a biomedical slash term when it occurs in source artifacts."""
    bundle = _containment_bundle()
    extraction = bundle.extraction.model_copy(
        update={"assay_limitations": ["BRAF/MEK pathway coverage reviewed"]}
    )
    supported_bundle = bundle.model_copy(update={"extraction": extraction})
    narrative = ClinicalNarrativeCompilerOutput(
        artifact_id="artifact_narrative",
        markdown="BRAF/MEK pathway coverage requires clinician review.",
        source_artifact_ids=["artifact_report"],
        safety_note="Clinician decision support only.",
    )

    report = require_narrative_fact_containment(narrative, supported_bundle)

    assert report.passed is True
    assert report.unsupported_findings == []


def test_narrative_containment_rejects_unsupported_gene_and_drug_terms() -> None:
    bundle = _containment_bundle()
    narrative = ClinicalNarrativeCompilerOutput(
        artifact_id="artifact_narrative",
        markdown="EGFR and trametinib appear here but are absent from the source artifacts.",
        source_artifact_ids=["artifact_report"],
        safety_note="Clinician decision support only; no certain response, cure, survival benefit, or deterministic outcome is claimed.",
    )
    report = validate_narrative_fact_containment(narrative, bundle)
    assert {finding.term for finding in report.unsupported_findings} >= {"EGFR", "trametinib"}
    with pytest.raises(NarrativeContainmentError):
        require_narrative_fact_containment(narrative, bundle)


def test_narrative_containment_allows_eid_audit_abbreviation() -> None:
    bundle = _containment_bundle()
    narrative = ClinicalNarrativeCompilerOutput(
        artifact_id="artifact_narrative",
        markdown=(
            "EID references are audit labels for evidence IDs, not new "
            "biomedical findings."
        ),
        source_artifact_ids=["artifact_report"],
        safety_note="Clinician decision support only; no certain response, cure, survival benefit, or deterministic outcome is claimed.",
    )

    report = require_narrative_fact_containment(narrative, bundle)

    assert report.passed is True
    assert report.unsupported_findings == []


def test_narrative_containment_ignores_vague_alteration_fragments() -> None:
    bundle = _containment_bundle()
    narrative = ClinicalNarrativeCompilerOutput(
        artifact_id="artifact_narrative",
        markdown=(
            "This amplification remains reviewable. The mutation should be "
            "read only as a reference to the report finding. The identified "
            "variant and detected mutation remain reviewable."
        ),
        source_artifact_ids=["artifact_report"],
        safety_note="Clinician decision support only; no certain response, cure, survival benefit, or deterministic outcome is claimed.",
    )
    report = require_narrative_fact_containment(narrative, bundle)
    assert report.passed is True
    assert report.unsupported_findings == []


def test_narrative_containment_ignores_grammatical_loss_phrase() -> None:
    bundle = _containment_bundle()
    narrative = ClinicalNarrativeCompilerOutput(
        artifact_id="artifact_narrative",
        markdown=(
            "The evidence remains subject to loss during review and must be "
            "confirmed from the source artifacts."
        ),
        source_artifact_ids=["artifact_report"],
        safety_note="Clinician decision support only.",
    )

    report = require_narrative_fact_containment(narrative, bundle)

    assert report.passed is True
    assert report.unsupported_findings == []


@pytest.mark.parametrize(
    "fragment",
    [
        "and fusion",
        "or mutation",
        "but deletion",
    ],
)
def test_narrative_containment_ignores_conjunction_led_alteration_fragments(
    fragment: str,
) -> None:
    """Do not treat conjunctions as molecular alteration anchors."""
    bundle = _containment_bundle()
    narrative = ClinicalNarrativeCompilerOutput(
        artifact_id="artifact_narrative",
        markdown=f"The review discusses evidence context {fragment} evidence.",
        source_artifact_ids=["artifact_report"],
        safety_note="Clinician decision support only.",
    )

    report = require_narrative_fact_containment(narrative, bundle)

    assert report.passed is True
    assert report.unsupported_findings == []


def test_narrative_containment_still_rejects_gene_anchored_fusion() -> None:
    """Preserve containment enforcement for a specific unsupported fusion."""
    bundle = _containment_bundle()
    narrative = ClinicalNarrativeCompilerOutput(
        artifact_id="artifact_narrative",
        markdown="ALK fusion appears here but is absent from the artifacts.",
        source_artifact_ids=["artifact_report"],
        safety_note="Clinician decision support only.",
    )

    report = validate_narrative_fact_containment(narrative, bundle)

    assert "ALK fusion" in {
        finding.term for finding in report.unsupported_findings
    }


def test_narrative_containment_rejects_unsupported_anchored_alteration() -> None:
    bundle = _containment_bundle()
    narrative = ClinicalNarrativeCompilerOutput(
        artifact_id="artifact_narrative",
        markdown="EGFR mutation appears here but is absent from the artifacts.",
        source_artifact_ids=["artifact_report"],
        safety_note="Clinician decision support only; no certain response, cure, survival benefit, or deterministic outcome is claimed.",
    )
    report = validate_narrative_fact_containment(narrative, bundle)
    assert "EGFR mutation" in {
        finding.term for finding in report.unsupported_findings
    }
    with pytest.raises(NarrativeContainmentError):
        require_narrative_fact_containment(narrative, bundle)


def test_narrative_containment_rejects_unsupported_anchored_loss() -> None:
    bundle = _containment_bundle()
    narrative = ClinicalNarrativeCompilerOutput(
        artifact_id="artifact_narrative",
        markdown="CDKN2A loss appears here but is absent from the artifacts.",
        source_artifact_ids=["artifact_report"],
        safety_note="Clinician decision support only.",
    )

    report = validate_narrative_fact_containment(narrative, bundle)

    assert "CDKN2A loss" in {
        finding.term for finding in report.unsupported_findings
    }
    with pytest.raises(NarrativeContainmentError):
        require_narrative_fact_containment(narrative, bundle)


@pytest.mark.asyncio
async def test_clinical_narrative_generation_normalizes_vague_fragments() -> None:
    bundle = _containment_bundle()
    result = await generate_clinical_narrative_with_model(
        bundle=bundle,
        model_provider=NarrativeModelProvider(
            "This amplification, the mutation, and the identified variant "
            "require human review."
        ),
        model_name="local-test-model",
        prompts_root=Path("configs/prompts"),
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    assert "This amplification" not in result.artifact.markdown
    assert "the mutation" not in result.artifact.markdown
    assert "identified variant" not in result.artifact.markdown
    assert "Report finding" in result.artifact.markdown
    assert "report finding" in result.artifact.markdown
    report = require_narrative_fact_containment(result.artifact, bundle)
    assert report.passed is True


@pytest.mark.asyncio
async def test_narrative_generation_replaces_model_source_ids_from_bundle() -> None:
    """Provenance IDs must be system-owned rather than model-authored."""
    bundle = _containment_bundle()
    provider = NarrativeModelProvider(
        "CHEK2 remains a source-backed finding for clinician review.",
        source_artifact_ids=[
            "artifact_d35c459176355742",
            "artifact_report",
            "artifact_report",
        ],
    )

    result = await generate_clinical_narrative_with_model(
        bundle=bundle,
        model_provider=provider,
        model_name="local-test-model",
        prompts_root=Path("configs/prompts"),
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    assert result.artifact.source_artifact_ids == ["artifact_report"]
    assert require_narrative_fact_containment(result.artifact, bundle).passed


@pytest.mark.asyncio
async def test_narrative_generation_rejects_unknown_id_in_markdown() -> None:
    """An unsupported artifact token in prose must fail within repair."""
    with pytest.raises(
        StructuredArtifactGenerationError,
        match="unsupported artifact IDs",
    ):
        await generate_clinical_narrative_with_model(
            bundle=_containment_bundle(),
            model_provider=NarrativeModelProvider(
                "Evidence artifact_d35c459176355742 requires review."
            ),
            model_name="local-test-model",
            prompts_root=Path("configs/prompts"),
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )


def test_narrative_containment_rejects_unknown_source_artifact_id() -> None:
    bundle = _containment_bundle()
    narrative = ClinicalNarrativeCompilerOutput(
        artifact_id="artifact_narrative",
        markdown="CHEK2 appears in the source-backed molecular findings for review.",
        source_artifact_ids=["artifact_missing"],
        safety_note="Clinician decision support only; no certain response, cure, survival benefit, or deterministic outcome is claimed.",
    )
    with pytest.raises(NarrativeContainmentError):
        require_narrative_fact_containment(narrative, bundle)


def test_narrative_containment_accepts_decision_brief_artifact_id() -> None:
    bundle = _containment_bundle().model_copy(
        update={
            "decision_brief": OncologistDecisionBrief.model_construct(
                artifact_id="artifact_decision_brief"
            )
        }
    )
    narrative = ClinicalNarrativeCompilerOutput(
        artifact_id="artifact_narrative",
        markdown="The decision brief remains subject to clinician review.",
        source_artifact_ids=["artifact_decision_brief"],
        safety_note="Clinician decision support only.",
    )

    report = require_narrative_fact_containment(narrative, bundle)

    assert report.passed is True
    assert report.unsupported_findings == []


def _planned_artifact_id(user_prompt: str) -> str:
    lines = user_prompt.splitlines()
    for index, line in enumerate(lines):
        if (
            line.strip() == "The artifact_id must be exactly:"
            and index + 1 < len(lines)
        ):
            return lines[index + 1].strip()
    raise AssertionError("planned artifact id missing from prompt")
