from __future__ import annotations

from translume_schemas.base import TranslumeBaseModel


class BiologicalAxis(TranslumeBaseModel):
    axis_id: str
    label: str
    supporting_finding_ids: list[str]
    evidence_class: str
    uncertainty: str
    validation_needed: bool


class MolecularPhenotypeOutput(TranslumeBaseModel):
    artifact_id: str
    axes: list[BiologicalAxis]
    limitations: list[str] = []
