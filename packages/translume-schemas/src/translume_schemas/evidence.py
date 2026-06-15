from __future__ import annotations

from translume_schemas.base import TranslumeBaseModel
from translume_schemas.extraction import ReportExtractionOutput
from translume_schemas.graph import GraphEvidenceArtifact
from translume_schemas.medea import MedeaReasoningArtifact
from translume_schemas.tools import ToolRunArtifact


class EvidenceContextBundle(TranslumeBaseModel):
    artifact_id: str
    extraction: ReportExtractionOutput
    graph_evidence: GraphEvidenceArtifact
    tool_outputs: list[ToolRunArtifact]
    medea_reasoning: MedeaReasoningArtifact
    missing_evidence: list[str] = []
    conflicting_evidence: list[str] = []
