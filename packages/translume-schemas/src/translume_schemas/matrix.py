from __future__ import annotations

from translume_schemas.base import TranslumeBaseModel
from translume_schemas.decision_brief import ClinicalUse, ConfidenceLabel


class MolecularFitRow(TranslumeBaseModel):
    rank: int
    molecular_fit: str
    fit_label: str
    why_from_omics: str
    evidence_basis: str
    limitations: str
    required_validation: str
    clinical_use: ClinicalUse
    therapy_class: str
    matched_biomarkers: list[str] = []
    resistance_risks: list[str] = []
    required_before_use_tests: list[str] = []
    confidence: ConfidenceLabel = "needs_review"
    evidence_level: str


class TherapyEvidenceMatrixOutput(TranslumeBaseModel):
    artifact_id: str
    rows: list[MolecularFitRow]
