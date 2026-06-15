from __future__ import annotations

from typing import Protocol

from translume_schemas.entities import NormalizedEntitySet
from translume_schemas.graph import GraphEvidenceArtifact


class GraphProvider(Protocol):
    async def retrieve_context(
        self,
        entities: NormalizedEntitySet,
    ) -> GraphEvidenceArtifact:
        """Retrieve graph evidence for normalized entities."""
