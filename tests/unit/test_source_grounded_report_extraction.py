from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from translume_core.compiler.report_extraction import (
    LegacyReportExtractionDisabledError,
    generate_report_extraction_from_chunks,
)
from translume_core.compiler.structured_model_artifacts import (
    StructuredArtifactGenerationError,
    generate_report_extraction_with_model,
)
from translume_schemas.document import DocumentChunk, RetrievedDocumentChunk


class RecordingReportExtractionModel:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.calls: list[dict[str, object]] = []

    async def structured_completion(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(dict(kwargs))
        return dict(self.payload)


def _planned_artifact_id(source_file_id: str) -> str:
    from uuid import NAMESPACE_URL, uuid5

    return f"artifact_{uuid5(NAMESPACE_URL, f'{source_file_id}:ReportExtractionOutput').hex[:16]}"


def _chunk(text: str, chunk_id: str = "chunk_1") -> RetrievedDocumentChunk:
    return RetrievedDocumentChunk(
        chunk=DocumentChunk(
            chunk_id=chunk_id,
            case_id="case_1",
            session_id="session_1",
            source_file_id="source_file_1",
            report_type="NGS",
            page_start=2,
            page_end=2,
            section="GENOMIC VARIANTS",
            chunk_type="molecular_finding",
            source_text=text,
            source_block_ids=["block_1"],
            needs_human_review=False,
        ),
        score=1.0,
        retrieval_method="lexical_metadata",
    )


@pytest.mark.asyncio
async def test_report_extraction_requires_retrieved_source_chunks(tmp_path: Path) -> None:
    provider = RecordingReportExtractionModel({})
    with pytest.raises(StructuredArtifactGenerationError, match="requires retrieved OpenSearch source chunks"):
        await generate_report_extraction_with_model(
            retrieved_chunks=[],
            report_type="NGS",
            source_file_id="source_file_1",
            model_provider=provider,
            model_name="local-model",
            prompts_root=Path("configs/prompts"),
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
    assert provider.calls == []


@pytest.mark.asyncio
async def test_report_extraction_source_aligns_findings_to_retrieved_chunks() -> None:
    source_file_id = "source_file_1"
    chunk = _chunk(
        "GENOMIC VARIANTS\nMTAP copy-number loss detected. CDKN2A copy-number loss detected."
    )
    provider = RecordingReportExtractionModel(
        {
            "artifact_id": _planned_artifact_id(source_file_id),
            "report_type": "incorrect_report_type_from_model",
            "disease": None,
            "specimen": None,
            "tumor_percentage": None,
            "source_file_id": "incorrect_source_file_from_model",
            "needs_human_review": False,
            "negative_findings": [],
            "assay_limitations": [],
            "molecular_findings": [
                {
                    "finding_id": "finding_mtap",
                    "gene": "MTAP",
                    "alteration": "copy-number loss",
                    "alteration_type": "copy_number_loss",
                    "confidence": 0.91,
                    "needs_human_review": False,
                    "research_use_only": False,
                }
            ],
        }
    )
    result = await generate_report_extraction_with_model(
        retrieved_chunks=[chunk],
        report_type="NGS",
        source_file_id=source_file_id,
        model_provider=provider,
        model_name="local-model",
        prompts_root=Path("configs/prompts"),
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    finding = result.artifact.molecular_findings[0]
    assert result.artifact.report_type == "NGS"
    assert result.artifact.source_file_id == source_file_id
    assert result.artifact.needs_human_review is True
    assert finding.source_chunk_id == "chunk_1"
    assert finding.source_page == 2
    assert finding.source_text is not None
    assert "MTAP" in finding.source_text
    assert finding.needs_human_review is True
    assert provider.calls[0]["schema_name"] == "ReportExtractionOutput"
    assert "source_grounding_contract" in str(provider.calls[0]["user_prompt"])


@pytest.mark.asyncio
async def test_report_extraction_downgrades_unsupported_model_findings() -> None:
    source_file_id = "source_file_1"
    chunk = _chunk("GENOMIC VARIANTS\nMTAP copy-number loss detected.")
    provider = RecordingReportExtractionModel(
        {
            "artifact_id": _planned_artifact_id(source_file_id),
            "report_type": "NGS",
            "source_file_id": source_file_id,
            "needs_human_review": True,
            "negative_findings": [],
            "assay_limitations": [],
            "molecular_findings": [
                {
                    "finding_id": "finding_unsupported",
                    "gene": "ZZZGENE",
                    "alteration": "unsupported event",
                    "alteration_type": "variant",
                    "confidence": 0.95,
                    "needs_human_review": True,
                    "research_use_only": False,
                }
            ],
        }
    )
    result = await generate_report_extraction_with_model(
        retrieved_chunks=[chunk],
        report_type="NGS",
        source_file_id=source_file_id,
        model_provider=provider,
        model_name="local-model",
        prompts_root=Path("configs/prompts"),
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    finding = result.artifact.molecular_findings[0]
    assert finding.source_chunk_id is None
    assert finding.source_text is None
    assert finding.confidence <= 0.25
    assert finding.needs_human_review is True


def test_legacy_deterministic_report_extraction_fails_loudly() -> None:
    with pytest.raises(LegacyReportExtractionDisabledError):
        generate_report_extraction_from_chunks(
            [],
            report_type="NGS",
            source_file_id="source_file_1",
        )
