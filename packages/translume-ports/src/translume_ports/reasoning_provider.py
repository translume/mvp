from __future__ import annotations

from typing import Protocol

from translume_schemas.evidence import EvidenceContextBundle
from translume_schemas.medea import MedeaReasoningArtifact


class ReasoningProvider(Protocol):
    async def reason_over_context(
        self,
        context: EvidenceContextBundle,
    ) -> MedeaReasoningArtifact:
        """Run bounded reasoning over evidence context."""
