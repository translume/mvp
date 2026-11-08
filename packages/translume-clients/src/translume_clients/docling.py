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
    timeout_seconds: float = 7200.0
    extraction_method: str = "openai"


class DoclingServiceClient:
    """HTTP client for the internal OpenAI document-extraction service."""

    def __init__(self, config: DoclingClientConfig) -> None:
        self._config = config
        self._base_url = config.base_url.rstrip("/")

    def extract(self, stored_file: StoredFile) -> DocumentExtractionOutput:
        """Extract structured document content through the remote-model service.

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
                raise DoclingClientError(
                    "remote document service request failed"
                ) from error
        if response.status_code >= 400:
            raise DoclingClientError(
                f"remote document service error {response.status_code}: "
                + _error_detail(response)
            )
        try:
            return DocumentExtractionOutput.model_validate(response.json())
        except (ValueError, TypeError) as error:
            raise DoclingClientError(
                "remote document service returned invalid extraction JSON"
            ) from error


def _error_detail(response: httpx.Response) -> str:
    """Return only the service's bounded diagnostic, never an arbitrary body."""
    try:
        payload = response.json()
    except ValueError:
        return "request failed without a structured diagnostic"
    detail = payload.get("detail") if isinstance(payload, dict) else None
    if not isinstance(detail, str):
        return "request failed without a structured diagnostic"
    return detail[:500]
