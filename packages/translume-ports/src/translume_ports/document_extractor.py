from __future__ import annotations

from typing import Protocol

from translume_schemas.document import DocumentExtractionOutput
from translume_schemas.session import StoredFile


class DocumentExtractor(Protocol):
    def extract(self, stored_file: StoredFile) -> DocumentExtractionOutput:
        """Extract structured document content from a stored file."""
