"""HTTP clients for the internal precision-oncology and pathway runners."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import httpx

from translume_schemas.downstream import (
    DownstreamAnalysisResult,
    PrecisionPipelineRun,
)


class DownstreamRunnerError(RuntimeError):
    """Raised when an internal runner fails or returns invalid data."""


@dataclass(frozen=True)
class DownstreamRunnerConfig:
    """Connection settings shared by internal downstream runner clients."""

    base_url: str
    timeout_seconds: float

    def normalized_base_url(self) -> str:
        value = self.base_url.strip().rstrip("/")
        if not value.startswith(("http://", "https://")):
            raise ValueError("Downstream runner URL must use HTTP or HTTPS")
        if self.timeout_seconds <= 0:
            raise ValueError("Downstream runner timeout must be positive")
        return value


class PrecisionOncologyRunnerClient:
    """Call the internal precision-oncology runner service."""

    def __init__(self, config: DownstreamRunnerConfig) -> None:
        self._base_url = config.normalized_base_url()
        self._timeout_seconds = config.timeout_seconds

    async def run(
        self,
        *,
        session_id: str,
        review_packet: Mapping[str, Any],
    ) -> PrecisionPipelineRun:
        """Run the precision pipeline for one exact persisted review packet."""
        payload = await _post_json(
            base_url=self._base_url,
            path="/runs",
            timeout_seconds=self._timeout_seconds,
            body={
                "session_id": session_id,
                "review_packet": dict(review_packet),
            },
        )
        try:
            return PrecisionPipelineRun.model_validate(payload)
        except ValueError as error:
            raise DownstreamRunnerError(
                f"Precision runner returned an invalid response: {error}"
            ) from error


class DynamicPathwayRunnerClient:
    """Call the internal dynamic pathway-analysis runner service."""

    def __init__(self, config: DownstreamRunnerConfig) -> None:
        self._base_url = config.normalized_base_url()
        self._timeout_seconds = config.timeout_seconds

    async def run(
        self,
        *,
        session_id: str,
        precision_run: PrecisionPipelineRun,
        diagnosis: str,
    ) -> DownstreamAnalysisResult:
        """Run both pathway stages for one verified precision pipeline run."""
        payload = await _post_json(
            base_url=self._base_url,
            path="/runs",
            timeout_seconds=self._timeout_seconds,
            body={
                "session_id": session_id,
                "precision_run_id": precision_run.run_id,
                "diagnosis": diagnosis,
            },
        )
        payload["precision_run"] = precision_run.model_dump(mode="json")
        try:
            return DownstreamAnalysisResult.model_validate(payload)
        except ValueError as error:
            raise DownstreamRunnerError(
                f"Dynamic pathway runner returned an invalid response: {error}"
            ) from error


async def _post_json(
    *,
    base_url: str,
    path: str,
    timeout_seconds: float,
    body: Mapping[str, Any],
) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.post(f"{base_url}{path}", json=dict(body))
    except httpx.HTTPError as error:
        raise DownstreamRunnerError(
            f"Runner request failed: {error}"
        ) from error
    if response.status_code >= 400:
        raise DownstreamRunnerError(_response_error(response))
    try:
        payload = response.json()
    except ValueError as error:
        raise DownstreamRunnerError(
            "Runner returned non-JSON content"
        ) from error
    if not isinstance(payload, dict):
        raise DownstreamRunnerError(
            "Runner returned a non-object JSON response"
        )
    return payload


def _response_error(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        payload = None
    if isinstance(payload, dict) and isinstance(payload.get("detail"), str):
        return payload["detail"]
    return f"Runner failed with HTTP {response.status_code}"
