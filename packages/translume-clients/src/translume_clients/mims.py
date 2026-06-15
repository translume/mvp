from __future__ import annotations

from dataclasses import dataclass

import httpx

from translume_schemas.entities import NormalizedEntitySet
from translume_schemas.evidence import EvidenceContextBundle
from translume_schemas.graph import GraphEvidenceArtifact
from translume_schemas.medea import MedeaReasoningArtifact
from translume_schemas.tools import ToolRunArtifact


class MimsServiceClientError(RuntimeError):
    """Raised when a required MIMS service call fails."""


@dataclass(frozen=True)
class MimsServiceClientConfig:
    """Connection settings for a MIMS service.

    Attributes:
        base_url: HTTP base URL for the service.
        timeout_seconds: Request timeout in seconds.
    """

    base_url: str
    timeout_seconds: float = 120.0


def _base_url(value: str) -> str:
    """Return a normalized service base URL.

    Acceptance criteria:
        1. Strips trailing slashes.
        2. Rejects empty URLs.
        3. Does not mutate input strings.

    Args:
        value: Raw service URL.

    Returns:
        URL without a trailing slash.

    Raises:
        ValueError: If `value` is empty after stripping.
    """
    stripped = value.strip().rstrip("/")
    if not stripped:
        raise ValueError("service base URL is required")
    return stripped


async def _post_json(
    config: MimsServiceClientConfig,
    path: str,
    payload: dict[str, object],
) -> dict[str, object]:
    """POST JSON to a MIMS service and return the response object.

    Acceptance criteria:
        1. Performs exactly one HTTP POST.
        2. Non-2xx responses raise `MimsServiceClientError`.
        3. Invalid JSON responses raise `MimsServiceClientError`.
        4. Does not fabricate fallback payloads.

    Args:
        config: Service connection settings.
        path: Endpoint path.
        payload: JSON request body.

    Returns:
        JSON response dictionary.

    Raises:
        MimsServiceClientError: If the request or response is invalid.
    """
    url = f"{_base_url(config.base_url)}/{path.lstrip('/')}"
    try:
        async with httpx.AsyncClient(timeout=config.timeout_seconds) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPError as error:
        raise MimsServiceClientError(f"MIMS service request failed: {url}: {error}") from error
    except ValueError as error:
        raise MimsServiceClientError(f"MIMS service returned invalid JSON: {url}") from error
    if not isinstance(data, dict):
        raise MimsServiceClientError(f"MIMS service returned non-object JSON: {url}")
    return data


class OptimusKGServiceClient:
    """HTTP GraphProvider backed by the OptimusKG service."""

    def __init__(self, config: MimsServiceClientConfig) -> None:
        self._config = config

    async def retrieve_context(
        self,
        entities: NormalizedEntitySet,
    ) -> GraphEvidenceArtifact:
        """Retrieve graph context from the OptimusKG service.

        Acceptance criteria:
            1. Sends normalized entities to `/context`.
            2. Validates the response as `GraphEvidenceArtifact`.
            3. Does not fabricate graph nodes or edges locally.
            4. Propagates service failures as explicit errors.

        Args:
            entities: Normalized report entities.

        Returns:
            Graph evidence artifact.
        """
        data = await _post_json(
            self._config,
            "/context",
            {"entities": entities.model_dump(mode="json")},
        )
        return GraphEvidenceArtifact.model_validate(data)


class ToolUniverseServiceClient:
    """HTTP ToolProvider backed by the ToolUniverse service."""

    def __init__(self, config: MimsServiceClientConfig) -> None:
        self._config = config

    async def run_workflows(
        self,
        *,
        workflows: list[str],
        entities: NormalizedEntitySet,
        graph: GraphEvidenceArtifact,
    ) -> list[ToolRunArtifact]:
        """Run governed ToolUniverse workflows through the service.

        Acceptance criteria:
            1. Sends requested workflows and context to `/workflows`.
            2. Validates every artifact in the response.
            3. Does not synthesize missing tool output.
            4. Propagates disallowed workflow failures.

        Args:
            workflows: Allow-listed workflow names requested by the core.
            entities: Normalized entities.
            graph: Graph evidence artifact.

        Returns:
            Tool run artifacts.
        """
        data = await _post_json(
            self._config,
            "/workflows",
            {
                "workflows": workflows,
                "entities": entities.model_dump(mode="json"),
                "graph": graph.model_dump(mode="json"),
            },
        )
        raw_artifacts = data.get("artifacts")
        if not isinstance(raw_artifacts, list):
            raise MimsServiceClientError("ToolUniverse service response missing artifacts list")
        return [ToolRunArtifact.model_validate(item) for item in raw_artifacts]


class MedeaServiceClient:
    """HTTP ReasoningProvider backed by the Medea service."""

    def __init__(self, config: MimsServiceClientConfig) -> None:
        self._config = config

    async def reason_over_context(
        self,
        context: EvidenceContextBundle,
    ) -> MedeaReasoningArtifact:
        """Run bounded Medea reasoning through the service.

        Acceptance criteria:
            1. Sends evidence context to `/reason`.
            2. Validates response as `MedeaReasoningArtifact`.
            3. Does not fabricate bounded reasoning locally.
            4. Propagates remote model-policy failures.

        Args:
            context: Evidence context bundle.

        Returns:
            Medea reasoning artifact.
        """
        data = await _post_json(
            self._config,
            "/reason",
            {"context": context.model_dump(mode="json")},
        )
        return MedeaReasoningArtifact.model_validate(data)
