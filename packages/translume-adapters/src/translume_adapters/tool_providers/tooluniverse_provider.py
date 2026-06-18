from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import httpx

from translume_adapters.errors import ProviderUnavailableError
from translume_adapters.tool_providers.tooluniverse_runtime import ToolUniverseRuntime
from translume_schemas.entities import NormalizedEntitySet
from translume_schemas.graph import GraphEvidenceArtifact
from translume_schemas.tools import ToolRunArtifact


@dataclass(frozen=True)
class ToolUniverseProviderConfig:
    """Configuration for the real ToolUniverse service adapter."""

    base_url: str
    timeout_seconds: float = 240.0


class ToolUniverseProvider:
    """Governed ToolUniverse adapter backed by real service or real runtime.

    Production API deployments should use the HTTP service mode so ToolUniverse
    dependency conflicts stay isolated. Direct-process deployments/tests may use
    the runtime mode by passing a vendored repo path and workflow config path.
    Both modes execute real configured ToolUniverse workflows and reject
    precomputed evidence files.
    """

    def __init__(
        self,
        config: ToolUniverseProviderConfig | str | Path,
        workflow_config_path: Path | None = None,
        module_names: tuple[str, ...] = ("tooluniverse",),
    ) -> None:
        self._runtime: ToolUniverseRuntime | None = None
        if workflow_config_path is not None:
            self._config = None
            self._runtime = ToolUniverseRuntime(
                repo_path=Path(config),
                workflow_config_path=workflow_config_path,
                module_names=module_names,
            )
            return
        if isinstance(config, str):
            config = ToolUniverseProviderConfig(base_url=config)
        if isinstance(config, Path):
            raise ProviderUnavailableError(
                "ToolUniverseProvider direct runtime mode requires workflow_config_path"
            )
        self._config = config

    async def run_workflows(
        self,
        *,
        workflows: list[str],
        entities: NormalizedEntitySet,
        graph: GraphEvidenceArtifact,
    ) -> list[ToolRunArtifact]:
        """Run governed workflows through a real ToolUniverse boundary.

        Acceptance criteria:
            1. Sends normalized entities and graph context to the service or real
               ToolUniverse runtime.
            2. Validates every returned artifact as `ToolRunArtifact`.
            3. Does not read fixture files or fabricate missing tool output.
            4. Propagates service/runtime failures as explicit provider errors.
        """
        if self._runtime is not None:
            return await self._runtime.run_workflows(
                workflows=workflows,
                entities=entities,
                graph=graph,
            )
        url = f"{self._base_url()}/workflows"
        payload = {
            "workflows": workflows,
            "entities": entities.model_dump(mode="json"),
            "graph": graph.model_dump(mode="json"),
        }
        try:
            async with httpx.AsyncClient(timeout=self._config.timeout_seconds) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as error:
            raise ProviderUnavailableError(f"ToolUniverse service request failed: {url}: {error}") from error
        except ValueError as error:
            raise ProviderUnavailableError(f"ToolUniverse service returned invalid JSON: {url}") from error
        raw_artifacts = data.get("artifacts") if isinstance(data, dict) else None
        if not isinstance(raw_artifacts, list):
            raise ProviderUnavailableError("ToolUniverse service response missing artifacts list")
        return [ToolRunArtifact.model_validate(item) for item in raw_artifacts]

    def _base_url(self) -> str:
        if self._config is None:
            raise ProviderUnavailableError("ToolUniverse service config is required")
        value = self._config.base_url.strip().rstrip("/")
        if not value:
            raise ProviderUnavailableError("ToolUniverse service base URL is required")
        return value
