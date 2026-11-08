"""Compatibility imports for the renamed remote document converter.

The service directory remains named ``docling-service`` for existing internal
URLs. It does not install or execute Docling or any local inference pipeline.
"""

from docling_service.openai_converter import (
    DocumentConversionError as DoclingServiceError,
)
from docling_service.openai_converter import (
    convert_pdf_with_openai as convert_pdf_with_docling,
)

__all__ = ["DoclingServiceError", "convert_pdf_with_docling"]
