from __future__ import annotations

from pathlib import Path
from typing import Any

from translume_core.document.docling_json import docling_dict_to_document_extraction
from translume_schemas.document import DocumentExtractionOutput


class DoclingServiceError(RuntimeError):
    """Raised when the Docling service cannot convert a document."""


def build_docling_format_options() -> dict[Any, Any]:
    """Build Docling format options for Translume PDF extraction.

    Acceptance criteria:
        1. Uses Docling's standard PDF pipeline.
        2. Disables OCR to avoid unsupported RapidOCR runtime defaults.
        3. Preserves text-native PDF layout and table extraction behavior.
        4. Returns a new options mapping on every call.

    Returns:
        Format options keyed by Docling input format.
    """
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import PdfFormatOption

    pipeline_options = PdfPipelineOptions(do_ocr=False)
    return {
        InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options),
    }


def convert_pdf_with_docling(
    file_path: Path,
    *,
    source_file_id: str,
    extraction_method: str = "docling",
) -> DocumentExtractionOutput:
    """Convert a PDF with the real Docling Python API.

    Acceptance criteria:
        1. Real conversion: Uses `docling.document_converter.DocumentConverter`.
        2. No fake output: Missing Docling dependency or failed conversion raises
           DoclingServiceError.
        3. Non-clinical: Produces document structure only, never clinical
           conclusions.
        4. Provenance: Preserves Docling page/bbox provenance when exported.
        5. Validation: Missing source file raises FileNotFoundError.

    Args:
        file_path: PDF path to convert.
        source_file_id: Stored source file identifier.
        extraction_method: Method label to place on the output.

    Returns:
        Normalized document extraction output.

    Raises:
        FileNotFoundError: If the PDF path does not exist.
        DoclingServiceError: If Docling is unavailable or conversion fails.
    """
    if not file_path.exists():
        raise FileNotFoundError(str(file_path))
    try:
        from docling.document_converter import DocumentConverter
    except ImportError as error:
        raise DoclingServiceError("docling package is not installed") from error
    try:
        result = DocumentConverter(
            format_options=build_docling_format_options(),
        ).convert(str(file_path))
        document = result.document
        exported: dict[str, Any] = document.export_to_dict()
    except Exception as error:  # pragma: no cover - depends on Docling runtime.
        raise DoclingServiceError(f"docling conversion failed: {error}") from error
    return docling_dict_to_document_extraction(
        exported,
        source_file_id=source_file_id,
        extraction_method=extraction_method,
    )
