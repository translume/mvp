from __future__ import annotations

import json
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from translume_adapters.errors import ProviderUnavailableError
from translume_schemas.evidence import EvidenceContextBundle
from translume_schemas.medea import MedeaReasoningArtifact


class MedeaReasoningProvider:
    """Bounded Medea reasoning adapter using local result artifacts.

    A production Medea service should write schema-compatible reasoning JSON to
    this artifact path after routing all model calls through local vLLM. This
    adapter refuses to fabricate reasoning when that result is missing.
    """

    def __init__(self, reasoning_json_path: Path) -> None:
        self._reasoning_json_path = reasoning_json_path

    async def reason_over_context(
        self,
        context: EvidenceContextBundle,
    ) -> MedeaReasoningArtifact:
        """Load bounded Medea reasoning for an evidence context.

        Acceptance criteria:
            1. Missing Medea reasoning raises `ProviderUnavailableError`.
            2. Output is schema-validated.
            3. Output is evidence support, not clinical truth.
            4. Every claim requires human review.
            5. No remote model provider is called.

        Args:
            context: Preliminary evidence context.

        Returns:
            Medea reasoning artifact.
        """
        if not self._reasoning_json_path.exists():
            raise ProviderUnavailableError(
                f"Medea reasoning artifact is missing: {self._reasoning_json_path}. "
                "Run Medea bounded reasoning workflow before enabling MIMS-required mode."
            )
        payload = json.loads(self._reasoning_json_path.read_text(encoding="utf-8"))
        artifact_id = f"artifact_{uuid5(NAMESPACE_URL, context.artifact_id + ':medea').hex[:16]}"
        return MedeaReasoningArtifact(
            artifact_id=artifact_id,
            reasoning_mode=str(payload.get("reasoning_mode", "bounded_review_support")),
            summary=str(payload.get("summary", "")),
            supported_hypotheses=[str(item) for item in payload.get("supported_hypotheses", [])],
            weakened_hypotheses=[str(item) for item in payload.get("weakened_hypotheses", [])],
            warnings=[str(item) for item in payload.get("warnings", [])],
            requires_human_review=True,
        )
