from __future__ import annotations

from translume_schemas.base import TranslumeBaseModel


class MolecularFinding(TranslumeBaseModel):
    finding_id: str
    gene: str | None = None
    alteration: str
    alteration_type: str
    source_page: int | None = None
    source_text: str | None = None
    source_chunk_id: str | None = None
    confidence: float
    needs_human_review: bool = True
    research_use_only: bool = False


class ReportExtractionOutput(TranslumeBaseModel):
    artifact_id: str
    report_type: str
    disease: str | None = None
    specimen: str | None = None
    tumor_percentage: str | None = None
    molecular_findings: list[MolecularFinding]
    negative_findings: list[str] = []
    assay_limitations: list[str] = []
    source_file_id: str
    needs_human_review: bool = True
