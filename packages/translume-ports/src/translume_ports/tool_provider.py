from __future__ import annotations

from typing import Protocol

from translume_schemas.entities import NormalizedEntitySet
from translume_schemas.graph import GraphEvidenceArtifact
from translume_schemas.tools import ToolRunArtifact


class ToolProvider(Protocol):
    async def run_workflows(
        self,
        *,
        workflows: list[str],
        entities: NormalizedEntitySet,
        graph: GraphEvidenceArtifact,
    ) -> list[ToolRunArtifact]:
        """Run governed evidence workflows."""
