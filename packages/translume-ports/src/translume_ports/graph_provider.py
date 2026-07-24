from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from translume_schemas.entities import NormalizedEntitySet
from translume_schemas.graph import GraphEvidenceArtifact, GraphRetrievalMode


class GraphProvider(Protocol):
    async def retrieve_context(
        self,
        entities: NormalizedEntitySet,
        retrieval_modes: Sequence[GraphRetrievalMode] | None = None,
    ) -> GraphEvidenceArtifact:
        """Retrieve graph evidence for normalized entities."""
