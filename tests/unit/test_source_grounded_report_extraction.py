from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from translume_core.compiler.report_extraction import (
    LegacyReportExtractionDisabledError,
    generate_report_extraction_from_chunks,
)
from translume_core.compiler.structured_model_artifacts import (
    _MAX_PROMPT_RETRIEVED_CHUNKS,
    _MAX_PROMPT_SOURCE_TEXT_CHARS,
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


class FailingReportExtractionModel:
    async def structured_completion(self, **_: object) -> dict[str, object]:
        raise RuntimeError("vLLM error 400: maximum context length")


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
async def test_report_extraction_batches_all_retrieved_chunks_in_page_order() -> None:
    source_file_id = "source_file_1"
    chunks = [
        _chunk(
            "GENOMIC VARIANTS\nMTAP copy-number loss detected. " * 40,
            chunk_id=f"chunk_{index:02d}",
        ).model_copy(update={"score": float(index)})
        for index in range(_MAX_PROMPT_RETRIEVED_CHUNKS + 5)
    ]
    provider = RecordingReportExtractionModel(
        {
            "artifact_id": _planned_artifact_id(source_file_id),
            "report_type": "NGS",
            "source_file_id": source_file_id,
            "needs_human_review": True,
            "negative_findings": [],
            "assay_limitations": [],
            "molecular_findings": [],
        }
    )

    result = await generate_report_extraction_with_model(
        retrieved_chunks=chunks,
        report_type="NGS",
        source_file_id=source_file_id,
        model_provider=provider,
        model_name="local-model",
        prompts_root=Path("configs/prompts"),
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    payload = _payload_from_user_prompt(str(provider.calls[0]["user_prompt"]))
    prompt_chunks = payload["retrieved_chunks"]

    assert result.artifact.molecular_findings == []
    assert len(provider.calls) == 2
    assert len(prompt_chunks) == _MAX_PROMPT_RETRIEVED_CHUNKS
    assert prompt_chunks[0]["chunk_id"] == "chunk_00"
    assert prompt_chunks[-1]["chunk_id"] == "chunk_19"
    second_payload = _payload_from_user_prompt(str(provider.calls[1]["user_prompt"]))
    assert [item["chunk_id"] for item in second_payload["retrieved_chunks"]] == [
        "chunk_20",
        "chunk_21",
        "chunk_22",
        "chunk_23",
        "chunk_24",
    ]
    assert payload["batch_context"]["total_batches"] == 2
    assert payload["retrieval_truncation"]["original_chunks"] == len(chunks)
    assert payload["retrieval_truncation"]["kept_chunks"] == len(prompt_chunks)


@pytest.mark.asyncio
async def test_report_extraction_uses_page_order_not_score_order() -> None:
    source_file_id = "source_file_1"
    chunks = [
        _chunk("GENOMIC VARIANTS\nLow score text.", chunk_id="chunk_low"),
        _chunk("GENOMIC VARIANTS\nMissing score text.", chunk_id="chunk_missing")
        .model_copy(update={"score": None}),
        _chunk("GENOMIC VARIANTS\nHigh score text.", chunk_id="chunk_high")
        .model_copy(update={"score": 5.0}),
    ]
    provider = RecordingReportExtractionModel(
        {
            "artifact_id": _planned_artifact_id(source_file_id),
            "report_type": "NGS",
            "source_file_id": source_file_id,
            "needs_human_review": True,
            "negative_findings": [],
            "assay_limitations": [],
            "molecular_findings": [],
        }
    )

    await generate_report_extraction_with_model(
        retrieved_chunks=chunks,
        report_type="NGS",
        source_file_id=source_file_id,
        model_provider=provider,
        model_name="local-model",
        prompts_root=Path("configs/prompts"),
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    payload = _payload_from_user_prompt(str(provider.calls[0]["user_prompt"]))

    assert [
        chunk["chunk_id"] for chunk in payload["retrieved_chunks"]
    ] == ["chunk_high", "chunk_low", "chunk_missing"]


@pytest.mark.asyncio
async def test_report_extraction_truncates_retrieved_chunk_source_text() -> None:
    source_file_id = "source_file_1"
    provider = RecordingReportExtractionModel(
        {
            "artifact_id": _planned_artifact_id(source_file_id),
            "report_type": "NGS",
            "source_file_id": source_file_id,
            "needs_human_review": True,
            "negative_findings": [],
            "assay_limitations": [],
            "molecular_findings": [],
        }
    )

    await generate_report_extraction_with_model(
        retrieved_chunks=[_chunk("MTAP loss. " * 200)],
        report_type="NGS",
        source_file_id=source_file_id,
        model_provider=provider,
        model_name="local-model",
        prompts_root=Path("configs/prompts"),
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    payload = _payload_from_user_prompt(str(provider.calls[0]["user_prompt"]))
    source_text = payload["retrieved_chunks"][0]["source_text"]

    assert len(source_text) > _MAX_PROMPT_SOURCE_TEXT_CHARS
    assert "[truncated" in source_text


@pytest.mark.asyncio
async def test_report_extraction_model_error_includes_prompt_diagnostics() -> None:
    source_file_id = "source_file_1"

    with pytest.raises(
        StructuredArtifactGenerationError,
        match="ReportExtractionOutput structured output failed for prompt",
    ) as error_info:
        await generate_report_extraction_with_model(
            retrieved_chunks=[_chunk("GENOMIC VARIANTS\nMTAP loss detected.")],
            report_type="NGS",
            source_file_id=source_file_id,
            model_provider=FailingReportExtractionModel(),
            model_name="local-model",
            prompts_root=Path("configs/prompts"),
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )

    message = str(error_info.value)
    assert "prompt 'report_extraction'" in message
    assert "system_prompt_chars=" in message
    assert "user_prompt_chars=" in message
    assert "payload_json_chars=" in message
    assert "maximum context length" in message


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


def _payload_from_user_prompt(user_prompt: str) -> dict[str, object]:
    marker = "Payload JSON:\n"
    payload_json = user_prompt.split(marker, maxsplit=1)[1]
    payload = json.loads(payload_json)
    if not isinstance(payload, dict):
        raise TypeError("prompt payload should be a JSON object")
    return payload
