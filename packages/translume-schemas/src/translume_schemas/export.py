from __future__ import annotations

from translume_schemas.base import TranslumeBaseModel
from translume_schemas.claims import ClaimEvidenceOutput
from translume_schemas.confirmatory import ConfirmatoryTestingOutput
from translume_schemas.document import DocumentChunk
from translume_schemas.entities import NormalizedEntitySet
from translume_schemas.evidence import EvidenceContextBundle
from translume_schemas.extraction import ReportExtractionOutput
from translume_schemas.ledger import LedgerEvent
from translume_schemas.matrix import TherapyEvidenceMatrixOutput
from translume_schemas.phenotype import MolecularPhenotypeOutput
from translume_schemas.provenance import ArtifactProvenance
from translume_schemas.sankey import MechanismSankeyOutput
from translume_schemas.tumor_behavior import TumorBehaviorModelOutput
from translume_schemas.validation import ValidationDecision


class ClinicalNarrativeCompilerOutput(TranslumeBaseModel):
    artifact_id: str
    markdown: str
    source_artifact_ids: list[str]
    safety_note: str


class ClinicalArtifactBundle(TranslumeBaseModel):
    case_id: str
    session_id: str
    extraction: ReportExtractionOutput
    entities: NormalizedEntitySet | None = None
    evidence_context: EvidenceContextBundle | None = None
    phenotype: MolecularPhenotypeOutput | None = None
    matrix: TherapyEvidenceMatrixOutput | None = None
    sankey: MechanismSankeyOutput | None = None
    confirmatory: ConfirmatoryTestingOutput | None = None
    tumor_behavior: TumorBehaviorModelOutput | None = None
    claims: list[ClaimEvidenceOutput] = []
    narrative: ClinicalNarrativeCompilerOutput | None = None
    validation_decisions: list[ValidationDecision] = []
    provenance: list[ArtifactProvenance] = []
    ledger_events: list[LedgerEvent] = []


class ReviewPacketExport(TranslumeBaseModel):
    case_id: str
    session_id: str
    source_file_id: str
    chunks: list[DocumentChunk]
    bundle: ClinicalArtifactBundle
