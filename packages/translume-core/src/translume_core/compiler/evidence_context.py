from __future__ import annotations

from uuid import uuid5, NAMESPACE_URL

from translume_schemas.evidence import EvidenceContextBundle
from translume_schemas.extraction import ReportExtractionOutput
from translume_schemas.graph import GraphEvidenceArtifact
from translume_schemas.medea import MedeaReasoningArtifact
from translume_schemas.tools import ToolRunArtifact


def combine_evidence_sources(
    extraction: ReportExtractionOutput,
    graph_evidence: GraphEvidenceArtifact,
    tool_outputs: list[ToolRunArtifact],
    medea_reasoning: MedeaReasoningArtifact,
) -> EvidenceContextBundle:
    """Combine report, graph, tool, and reasoning evidence.

    Acceptance criteria:
        1. Bundle preserves all source artifact IDs.
        2. Bundle separates report facts from graph/tool/model evidence.
        3. Missing evidence is explicitly represented.
        4. Bundle is JSON-serializable.
        5. No final clinical claims are made here.

    Args:
        extraction: Report factual extraction.
        graph_evidence: Graph context artifact.
        tool_outputs: Tool workflow artifacts.
        medea_reasoning: Bounded reasoning artifact.

    Returns:
        Evidence context bundle.
    """
    missing = [*graph_evidence.missing_entities]
    for output in tool_outputs:
        missing.extend(output.warnings)
    missing.extend(medea_reasoning.warnings)
    artifact_id = f"artifact_{uuid5(NAMESPACE_URL, f'{extraction.artifact_id}:evidence').hex[:16]}"
    return EvidenceContextBundle(
        artifact_id=artifact_id,
        extraction=extraction,
        graph_evidence=graph_evidence,
        tool_outputs=tool_outputs,
        medea_reasoning=medea_reasoning,
        missing_evidence=missing,
    )
