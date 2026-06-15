from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import httpx

from translume_schemas.document import DocumentExtractionOutput
from translume_schemas.session import StoredFile


class DoclingClientError(RuntimeError):
    """Raised when the Docling service cannot extract a document."""


@dataclass(frozen=True)
class DoclingClientConfig:
    """Docling service client configuration.

    Attributes:
        base_url: Docling service base URL.
        timeout_seconds: HTTP timeout in seconds.
        extraction_method: Extraction method label sent to the service.
    """

    base_url: str
    timeout_seconds: float = 240.0
    extraction_method: str = "docling"


class DoclingServiceClient:
    """HTTP client for the real Docling document extraction service."""

    def __init__(self, config: DoclingClientConfig) -> None:
        self._config = config
        self._base_url = config.base_url.rstrip("/")

    def extract(self, stored_file: StoredFile) -> DocumentExtractionOutput:
        """Extract structured document content through Docling service.

        Acceptance criteria:
            1. Sends the stored PDF bytes to the configured Docling service.
            2. Non-2xx responses raise DoclingClientError.
            3. Invalid response shapes raise DoclingClientError.
            4. Output is parsed as DocumentExtractionOutput.
            5. Network I/O is isolated in this boundary.

        Args:
            stored_file: Stored source PDF metadata.

        Returns:
            Structured document extraction output.

        Raises:
            FileNotFoundError: If stored_file.path does not exist.
            DoclingClientError: If service extraction fails.
        """
        path = Path(stored_file.path)
        if not path.exists():
            raise FileNotFoundError(str(path))
        url = f"{self._base_url}/extract"
        with path.open("rb") as file_obj:
            files = {"file": (stored_file.filename, file_obj, "application/pdf")}
            data = {
                "source_file_id": stored_file.source_file_id,
                "extraction_method": self._config.extraction_method,
            }
            try:
                response = httpx.post(
                    url,
                    files=files,
                    data=data,
                    timeout=self._config.timeout_seconds,
                )
            except httpx.HTTPError as error:
                raise DoclingClientError(f"docling service request failed: {error}") from error
        if response.status_code >= 400:
            raise DoclingClientError(
                f"docling service error {response.status_code}: {response.text}"
            )
        try:
            return DocumentExtractionOutput.model_validate(response.json())
        except Exception as error:
            raise DoclingClientError("docling service returned invalid extraction JSON") from error
