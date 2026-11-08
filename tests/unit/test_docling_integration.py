from __future__ import annotations

from pathlib import Path

import pytest
from docling_service.openai_converter import document_config_from_environment
from translume_clients.docling import DoclingClientConfig, DoclingServiceClient
from translume_core.document.docling_json import docling_dict_to_document_extraction
from translume_core.workflow import (
    TranslumeWorkflowConfig,
    TranslumeWorkflowProviders,
    _extract_best_document,
)
from translume_schemas.session import StoredFile


def test_document_service_defaults_to_remote_astra_pro() -> None:
    settings = document_config_from_environment({})
    assert settings.model_name == "gpt-6-astra"
    assert settings.reasoning_mode == "pro"
    assert settings.max_page_bytes < 50_000_000


def test_docling_dict_to_document_extraction_preserves_layout() -> None:
    exported = {
        "pages": {"1": {"size": {"width": 612, "height": 792}}},
        "texts": [
            {
                "label": "section_header",
                "text": "GENOMIC VARIANTS",
                "prov": [{"page_no": 1, "bbox": {"l": 1, "t": 2, "r": 3, "b": 4}}],
            },
            {
                "label": "text",
                "text": "CHEK2 splice-region loss of function",
                "prov": [{"page_no": 1, "bbox": {"l": 5, "t": 6, "r": 7, "b": 8}}],
            },
        ],
        "tables": [
            {
                "label": "table",
                "data": {
                    "table_cells": [
                        {"text": "Gene"},
                        {"text": "Alteration"},
                        {"text": "MTAP"},
                        {"text": "Copy number loss"},
                    ]
                },
                "prov": [{"page_no": 1, "bbox": {"l": 10, "t": 11, "r": 12, "b": 13}}],
            }
        ],
    }
    extraction = docling_dict_to_document_extraction(
        exported,
        source_file_id="file_a",
        extraction_method="docling",
    )
    page = extraction.pages[0]
    assert extraction.extraction_method == "docling"
    assert page.page_number == 1
    assert any(block.block_type == "heading" for block in page.blocks)
    assert any(block.block_type == "table" for block in page.blocks)
    assert page.tables
    assert page.blocks[0].bbox is not None
    assert "GENOMIC VARIANTS" in page.text


def test_docling_required_without_provider_fails(tmp_path: Path) -> None:
    stored_file = StoredFile(
        case_id="case_a",
        session_id="session_a",
        source_file_id="file_a",
        filename="a.pdf",
        path=tmp_path / "a.pdf",
        size_bytes=1,
        sha256="abc",
    )
    stored_file.path.write_bytes(b"%PDF-1.4")
    with pytest.raises(RuntimeError, match="Remote document extractor is required"):
        _extract_best_document(
            stored_file,
            TranslumeWorkflowProviders(),
            TranslumeWorkflowConfig(storage_root=tmp_path, require_docling=True),
        )


def test_docling_client_requires_existing_file(tmp_path: Path) -> None:
    stored_file = StoredFile(
        case_id="case_a",
        session_id="session_a",
        source_file_id="file_a",
        filename="missing.pdf",
        path=tmp_path / "missing.pdf",
        size_bytes=1,
        sha256="abc",
    )
    client = DoclingServiceClient(
        DoclingClientConfig(base_url="http://docling-service:8090")
    )
    with pytest.raises(FileNotFoundError):
        client.extract(stored_file)
