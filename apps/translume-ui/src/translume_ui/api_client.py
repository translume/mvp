from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from pydantic import ValidationError

from translume_schemas.decision_brief import OncologistDecisionBrief
from translume_schemas.downstream import DownstreamAnalysisResult
from translume_schemas.export import ReviewPacketExport


class TranslumeUIAPIError(RuntimeError):
    """Raised when the Gradio UI cannot obtain valid data from FastAPI."""


@dataclass(frozen=True)
class TranslumeAPIClientConfig:
    """Connection settings for the Translume API used by the Gradio UI."""

    base_url: str
    request_timeout_seconds: float = 120.0
    process_timeout_seconds: float = 3600.0
    downstream_timeout_seconds: float = 7200.0

    def normalized_base_url(self) -> str:
        value = self.base_url.strip().rstrip("/")
        if not value:
            raise ValueError("Translume API base URL is required")
        if not value.startswith(("http://", "https://")):
            raise ValueError("Translume API base URL must use http:// or https://")
        if self.request_timeout_seconds <= 0:
            raise ValueError("request_timeout_seconds must be positive")
        if self.process_timeout_seconds <= 0:
            raise ValueError("process_timeout_seconds must be positive")
        if self.downstream_timeout_seconds <= 0:
            raise ValueError("downstream_timeout_seconds must be positive")
        return value


class TranslumeAPIClient:
    """Synchronous UI boundary for the real Translume FastAPI service.

    This client never synthesizes report artifacts. Every returned review packet
    is validated against ``ReviewPacketExport`` before the UI renders it.
    """

    def __init__(self, config: TranslumeAPIClientConfig) -> None:
        self._config = config
        self._base_url = config.normalized_base_url()

    def process_report(self, file_path: Path, report_type: str) -> ReviewPacketExport:
        """Submit one PDF to the production report-processing endpoint."""
        if not file_path.exists() or not file_path.is_file():
            raise TranslumeUIAPIError(f"Uploaded PDF is unavailable: {file_path}")
        if file_path.suffix.casefold() != ".pdf":
            raise TranslumeUIAPIError("Only PDF reports are accepted")
        normalized_report_type = report_type.strip()
        if not normalized_report_type:
            raise TranslumeUIAPIError("Report type is required")

        with file_path.open("rb") as handle:
            response = self._request(
                "POST",
                "/api/v1/reports/process",
                timeout=self._config.process_timeout_seconds,
                files={"file": (file_path.name, handle, "application/pdf")},
                data={"report_type": normalized_report_type},
            )
        return _validate_review_packet_response(response, operation="process report")

    def fetch_review_packet(self, session_id: str) -> ReviewPacketExport:
        """Fetch the exact persisted review packet for a session."""
        normalized_session_id = _required_identifier(session_id, "session_id")
        response = self._request(
            "GET",
            f"/api/v1/review-packets/{normalized_session_id}/export",
            timeout=self._config.request_timeout_seconds,
        )
        return _validate_review_packet_response(
            response,
            operation="fetch persisted review packet",
        )

    def run_downstream_analysis(
        self,
        session_id: str,
        diagnosis: str,
    ) -> DownstreamAnalysisResult:
        """Run downstream pathway analysis for one persisted review packet."""
        normalized_session_id = _required_identifier(session_id, "session_id")
        normalized_diagnosis = diagnosis.strip()
        if not normalized_diagnosis:
            raise TranslumeUIAPIError("Diagnosis is required")
        response = self._request(
            "POST",
            (
                "/api/v1/review-packets/"
                f"{normalized_session_id}/downstream-analysis"
            ),
            timeout=self._config.downstream_timeout_seconds,
            json={"diagnosis": normalized_diagnosis},
        )
        payload = _response_json_object(response, operation="run downstream analysis")
        try:
            return DownstreamAnalysisResult.model_validate(payload)
        except ValidationError as error:
            raise TranslumeUIAPIError(
                f"Translume API returned invalid downstream analysis: {error}"
            ) from error

    def fetch_decision_brief(self, session_id: str) -> OncologistDecisionBrief:
        """Fetch the exact persisted oncologist decision brief for a session.

        Acceptance criteria:
            1. Requires a non-empty session ID.
            2. Calls the focused decision-brief API endpoint.
            3. Validates the payload against ``OncologistDecisionBrief``.
            4. Does not reconstruct or synthesize decision-brief content.
        """
        normalized_session_id = _required_identifier(session_id, "session_id")
        response = self._request(
            "GET",
            f"/api/v1/review-packets/{normalized_session_id}/decision-brief",
            timeout=self._config.request_timeout_seconds,
        )
        return _validate_decision_brief_response(
            response,
            operation="fetch persisted decision brief",
        )

    def validate_claim(
        self,
        *,
        session_id: str,
        claim_id: str,
        status: str,
        reviewer_id: str | None,
        reviewer_note: str | None,
    ) -> dict[str, Any]:
        """Persist one human claim-validation decision through FastAPI."""
        normalized_session_id = _required_identifier(session_id, "session_id")
        normalized_claim_id = _required_identifier(claim_id, "claim_id")
        normalized_status = status.strip()
        if normalized_status not in {"validated", "rejected", "needs_review"}:
            raise TranslumeUIAPIError(f"Unsupported validation status: {status}")

        response = self._request(
            "POST",
            (
                f"/api/v1/review-packets/{normalized_session_id}/claims/"
                f"{normalized_claim_id}/validation"
            ),
            timeout=self._config.request_timeout_seconds,
            json={
                "status": normalized_status,
                "reviewer_id": _none_if_blank(reviewer_id),
                "reviewer_note": _none_if_blank(reviewer_note),
            },
        )
        payload = _response_json_object(response, operation="validate claim")
        response_session = str(payload.get("session_id", "")).strip()
        if response_session != normalized_session_id:
            raise TranslumeUIAPIError(
                "Validation API returned a session that does not match the request"
            )
        return payload

    def _request(
        self,
        method: str,
        path: str,
        *,
        timeout: float,
        **kwargs: Any,
    ) -> httpx.Response:
        url = f"{self._base_url}/{path.lstrip('/')}"
        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.request(method, url, **kwargs)
        except httpx.HTTPError as error:
            raise TranslumeUIAPIError(
                f"Translume API request failed for {url}: {error}"
            ) from error
        if response.status_code >= 400:
            raise TranslumeUIAPIError(_api_error_message(response, operation=path))
        return response


def write_persisted_review_packet(
    packet: ReviewPacketExport,
    export_root: Path,
) -> Path:
    """Write the API-validated persisted packet to an atomic JSON export file."""
    export_root.mkdir(parents=True, exist_ok=True)
    safe_session_id = _safe_filename_component(packet.session_id)
    destination = export_root / f"translume-review-packet-{safe_session_id}.json"
    temporary = destination.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(packet.model_dump(mode="json"), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary.replace(destination)
    return destination


def write_persisted_decision_brief(
    brief: OncologistDecisionBrief,
    export_root: Path,
) -> Path:
    """Write an API-validated decision brief to an atomic JSON export file.

    Acceptance criteria:
        1. Creates the export directory when missing.
        2. Names the file from the validated decision-brief artifact ID.
        3. Writes only the decision brief, not the full review packet.
        4. Uses atomic replacement to avoid partial user downloads.

    Args:
        brief: API-validated persisted decision-brief artifact.
        export_root: Directory where the JSON file should be written.

    Returns:
        Path to the completed JSON export.
    """
    export_root.mkdir(parents=True, exist_ok=True)
    safe_artifact_id = _safe_filename_component(brief.artifact_id)
    destination = export_root / f"translume-decision-brief-{safe_artifact_id}.json"
    temporary = destination.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(brief.model_dump(mode="json"), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary.replace(destination)
    return destination


def _validate_decision_brief_response(
    response: httpx.Response,
    *,
    operation: str,
) -> OncologistDecisionBrief:
    payload = _response_json_object(response, operation=operation)
    try:
        return OncologistDecisionBrief.model_validate(payload)
    except ValidationError as error:
        raise TranslumeUIAPIError(
            "Translume API returned an invalid oncologist decision brief "
            f"during {operation}: {error}"
        ) from error


def _validate_review_packet_response(
    response: httpx.Response,
    *,
    operation: str,
) -> ReviewPacketExport:
    payload = _response_json_object(response, operation=operation)
    try:
        return ReviewPacketExport.model_validate(payload)
    except ValidationError as error:
        raise TranslumeUIAPIError(
            f"Translume API returned an invalid review packet during {operation}: {error}"
        ) from error


def _response_json_object(
    response: httpx.Response,
    *,
    operation: str,
) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as error:
        raise TranslumeUIAPIError(
            f"Translume API returned non-JSON content during {operation}"
        ) from error
    if not isinstance(payload, dict):
        raise TranslumeUIAPIError(
            f"Translume API returned a non-object JSON value during {operation}"
        )
    return payload


def _api_error_message(response: httpx.Response, *, operation: str) -> str:
    detail = response.text.strip()
    try:
        payload = response.json()
    except ValueError:
        payload = None
    if isinstance(payload, dict):
        candidate = payload.get("detail")
        if isinstance(candidate, str) and candidate.strip():
            detail = candidate.strip()
    detail = detail or "No error detail was returned"
    return f"Translume API error {response.status_code} during {operation}: {detail}"


def _required_identifier(value: str, label: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise TranslumeUIAPIError(f"{label} is required")
    return normalized


def _none_if_blank(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _safe_filename_component(value: str) -> str:
    normalized = "".join(
        character if character.isalnum() or character in {"-", "_"} else "-"
        for character in value.strip()
    ).strip("-")
    if not normalized:
        raise TranslumeUIAPIError("session_id cannot be converted to an export filename")
    return normalized
