from __future__ import annotations

from translume_schemas.base import TranslumeBaseModel


class MolecularFitRow(TranslumeBaseModel):
    rank: int
    molecular_fit: str
    fit_label: str
    why_from_omics: str
    evidence_basis: str
    limitations: str
    required_validation: str
    not_a_recommendation: bool = True


class TherapyEvidenceMatrixOutput(TranslumeBaseModel):
    artifact_id: str
    rows: list[MolecularFitRow]
