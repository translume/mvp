from __future__ import annotations

from datetime import datetime

from translume_core.provenance.provenance import (
    ArtifactProvenanceError,
    build_artifact_provenance,
    require_complete_provenance_record,
)
from translume_schemas.claims import ClaimEvidenceOutput
from translume_schemas.entities import NormalizedEntitySet
from translume_schemas.evidence import EvidenceContextBundle
from translume_schemas.export import ClinicalArtifactBundle
from translume_schemas.extraction import ReportExtractionOutput
from translume_schemas.graph import GraphEvidenceArtifact
from translume_schemas.medea import MedeaReasoningArtifact
from translume_schemas.provenance import ArtifactProvenance
from translume_schemas.tools import ToolRunArtifact


def source_chunk_ids_from_report_extraction(
    extraction: ReportExtractionOutput,
) -> list[str]:
    """Return ordered unique source chunk IDs used by report findings.

    Acceptance criteria:
        1. Preserves first-seen order.
        2. Excludes missing/empty chunk IDs.
        3. Does not infer chunk IDs.
        4. Performs no I/O.
    """
    seen: set[str] = set()
    ordered: list[str] = []
    for finding in extraction.molecular_findings:
        chunk_id = (finding.source_chunk_id or "").strip()
        if chunk_id and chunk_id not in seen:
            seen.add(chunk_id)
            ordered.append(chunk_id)
    return ordered


def provenance_for_normalized_entities(
    entities: NormalizedEntitySet,
    extraction: ReportExtractionOutput,
    *,
    created_at: datetime,
) -> ArtifactProvenance:
    """Return provenance for entity normalization.

    Acceptance criteria:
        1. Links normalized entities to the report extraction artifact.
        2. Carries source chunk IDs from source-aligned report findings.
        3. Uses a concrete schema hash for NormalizedEntitySet.
        4. Uses a concrete Translume normalizer provider label, not a generic
           compiler placeholder.
    """
    return build_artifact_provenance(
        artifact_type="NormalizedEntitySet",
        schema_name="NormalizedEntitySet",
        model_name="translume_entity_normalizer_v1",
        prompt_text="Normalize source-grounded molecular report findings into biomedical entities without clinical inference.",
        schema_json=NormalizedEntitySet.model_json_schema(),
        source_artifact_ids=[extraction.artifact_id],
        source_chunk_ids=source_chunk_ids_from_report_extraction(extraction),
        source_file_id=extraction.source_file_id,
        created_at=created_at,
        artifact_id=entities.artifact_id,
    )


def provenance_for_graph_evidence(
    graph: GraphEvidenceArtifact,
    entities: NormalizedEntitySet,
    extraction: ReportExtractionOutput,
    *,
    created_at: datetime,
) -> ArtifactProvenance:
    """Return provenance for OptimusKG graph context.

    Acceptance criteria:
        1. Links graph evidence to normalized entities.
        2. Keeps graph provenance separate from clinical claims.
        3. Uses GraphEvidenceArtifact schema hash.
        4. Does not synthesize graph nodes or edges.
    """
    return build_artifact_provenance(
        artifact_type="GraphEvidenceArtifact",
        schema_name="GraphEvidenceArtifact",
        model_name="optimuskg_python_client_polars_provider",
        prompt_text="Retrieve OptimusKG graph context for normalized report entities and normalize real graph rows into GraphEvidenceArtifact.",
        schema_json=GraphEvidenceArtifact.model_json_schema(),
        source_artifact_ids=[entities.artifact_id],
        source_chunk_ids=source_chunk_ids_from_report_extraction(extraction),
        source_file_id=extraction.source_file_id,
        created_at=created_at,
        artifact_id=graph.artifact_id,
    )


def provenance_for_tool_output(
    tool: ToolRunArtifact,
    entities: NormalizedEntitySet,
    graph: GraphEvidenceArtifact,
    extraction: ReportExtractionOutput,
    *,
    created_at: datetime,
) -> ArtifactProvenance:
    """Return provenance for one ToolUniverse workflow output.

    Acceptance criteria:
        1. Links tool output to normalized entities and graph context.
        2. Preserves the concrete workflow in model/provider name.
        3. Uses ToolRunArtifact schema hash.
        4. Performs no I/O and does not inspect external services.
    """
    return build_artifact_provenance(
        artifact_type="ToolRunArtifact",
        schema_name="ToolRunArtifact",
        model_name=f"tooluniverse_workflow:{tool.workflow}",
        prompt_text=(
            f"Run allow-listed ToolUniverse workflow {tool.workflow} against normalized entities "
            "and graph evidence; normalize the real tool result into ToolRunArtifact."
        ),
        schema_json=ToolRunArtifact.model_json_schema(),
        source_artifact_ids=[entities.artifact_id, graph.artifact_id],
        source_chunk_ids=source_chunk_ids_from_report_extraction(extraction),
        source_file_id=extraction.source_file_id,
        created_at=created_at,
        artifact_id=tool.artifact_id,
    )


def provenance_for_medea_reasoning(
    medea: MedeaReasoningArtifact,
    context_without_medea: EvidenceContextBundle,
    *,
    created_at: datetime,
) -> ArtifactProvenance:
    """Return provenance for bounded Medea reasoning.

    Acceptance criteria:
        1. Links Medea reasoning to the evidence context it reviewed.
        2. Uses a concrete local-vLLM Medea provider label.
        3. Uses MedeaReasoningArtifact schema hash.
        4. Does not claim Medea runtime validation by itself.
    """
    extraction = context_without_medea.extraction
    return build_artifact_provenance(
        artifact_type="MedeaReasoningArtifact",
        schema_name="MedeaReasoningArtifact",
        model_name="medea_service_local_vllm_bounded_reasoning",
        prompt_text="Run bounded Medea literature/omics reasoning over the current EvidenceContextBundle using local vLLM routing.",
        schema_json=MedeaReasoningArtifact.model_json_schema(),
        source_artifact_ids=[
            context_without_medea.extraction.artifact_id,
            context_without_medea.graph_evidence.artifact_id,
            *[tool.artifact_id for tool in context_without_medea.tool_outputs],
        ],
        source_chunk_ids=source_chunk_ids_from_report_extraction(extraction),
        source_file_id=extraction.source_file_id,
        created_at=created_at,
        artifact_id=medea.artifact_id,
    )


def provenance_for_evidence_context(
    context: EvidenceContextBundle,
    *,
    created_at: datetime,
) -> ArtifactProvenance:
    """Return provenance for the merged evidence context bundle.

    Acceptance criteria:
        1. Links the context to report, graph, tool, and Medea artifacts.
        2. Uses EvidenceContextBundle schema hash.
        3. Carries source chunks from the report extraction.
        4. Performs no I/O.
    """
    return build_artifact_provenance(
        artifact_type="EvidenceContextBundle",
        schema_name="EvidenceContextBundle",
        model_name="translume_evidence_context_compiler_v1",
        prompt_text="Merge source-backed report extraction, OptimusKG graph evidence, ToolUniverse outputs, and Medea reasoning into an EvidenceContextBundle.",
        schema_json=EvidenceContextBundle.model_json_schema(),
        source_artifact_ids=_context_source_ids(context),
        source_chunk_ids=source_chunk_ids_from_report_extraction(context.extraction),
        source_file_id=context.extraction.source_file_id,
        created_at=created_at,
        artifact_id=context.artifact_id,
    )


def provenance_for_claim(
    claim: ClaimEvidenceOutput,
    extraction: ReportExtractionOutput,
    *,
    created_at: datetime,
) -> ArtifactProvenance:
    """Return provenance for one reviewable claim card.

    Acceptance criteria:
        1. Treats claim cards as auditable reasoning artifacts.
        2. Links each claim to its source artifact IDs.
        3. Uses ClaimEvidenceOutput schema hash.
        4. Preserves source chunk lineage through the report extraction.
    """
    return build_artifact_provenance(
        artifact_type="ClaimEvidenceOutput",
        schema_name="ClaimEvidenceOutput",
        model_name="local_vllm_claim_evidence_compiler",
        prompt_text="Classify one major clinical-translational statement as fact, inference, hypothesis, missing evidence, or needs review using structured source artifacts.",
        schema_json=ClaimEvidenceOutput.model_json_schema(),
        source_artifact_ids=list(claim.source_artifact_ids),
        source_chunk_ids=source_chunk_ids_from_report_extraction(extraction),
        source_file_id=extraction.source_file_id,
        created_at=created_at,
        artifact_id=claim.claim_id,
    )


def expected_bundle_artifact_ids(bundle: ClinicalArtifactBundle) -> dict[str, str]:
    """Return expected artifact IDs and schema names for a bundle.

    Acceptance criteria:
        1. Includes every present top-level artifact.
        2. Includes graph, tool, Medea, and evidence context artifacts.
        3. Includes every claim card by claim_id.
        4. Performs no I/O.
    """
    expected = {bundle.extraction.artifact_id: "ReportExtractionOutput"}
    if bundle.entities is not None:
        expected[bundle.entities.artifact_id] = "NormalizedEntitySet"
    if bundle.evidence_context is not None:
        expected[bundle.evidence_context.artifact_id] = "EvidenceContextBundle"
        expected[bundle.evidence_context.graph_evidence.artifact_id] = "GraphEvidenceArtifact"
        for tool in bundle.evidence_context.tool_outputs:
            expected[tool.artifact_id] = "ToolRunArtifact"
        expected[bundle.evidence_context.medea_reasoning.artifact_id] = "MedeaReasoningArtifact"
    if bundle.phenotype is not None:
        expected[bundle.phenotype.artifact_id] = "MolecularPhenotypeOutput"
    if bundle.matrix is not None:
        expected[bundle.matrix.artifact_id] = "TherapyEvidenceMatrixOutput"
    if bundle.sankey is not None:
        expected[bundle.sankey.artifact_id] = "MechanismSankeyOutput"
    if bundle.confirmatory is not None:
        expected[bundle.confirmatory.artifact_id] = "ConfirmatoryTestingOutput"
    if bundle.tumor_behavior is not None:
        expected[bundle.tumor_behavior.artifact_id] = "TumorBehaviorModelOutput"
    if bundle.decision_brief is not None:
        expected[bundle.decision_brief.artifact_id] = "OncologistDecisionBrief"
    for claim in bundle.claims:
        expected[claim.claim_id] = "ClaimEvidenceOutput"
    if bundle.narrative is not None:
        expected[bundle.narrative.artifact_id] = "ClinicalNarrativeCompilerOutput"
    if bundle.narrative_containment is not None:
        expected[bundle.narrative_containment.artifact_id] = "NarrativeContainmentReport"
    return expected


def require_bundle_provenance_complete(bundle: ClinicalArtifactBundle) -> None:
    """Fail if the clinical bundle lacks artifact-specific provenance.

    Acceptance criteria:
        1. Every present artifact has exactly one provenance record.
        2. Every provenance record has a concrete schema name and schema hash.
        3. Generic compiler/provider labels are rejected.
        4. Extra provenance records that do not match bundle artifacts are
           rejected to prevent scorecard inflation.
        5. Does not mutate the bundle.
    """
    expected = expected_bundle_artifact_ids(bundle)
    records = {record.artifact_id: record for record in bundle.provenance}
    missing = sorted(set(expected) - set(records))
    extra = sorted(set(records) - set(expected))
    if missing:
        raise ArtifactProvenanceError(
            "clinical artifact bundle is missing provenance for artifact IDs: "
            + ", ".join(missing)
        )
    if extra:
        raise ArtifactProvenanceError(
            "clinical artifact bundle contains provenance for unknown artifact IDs: "
            + ", ".join(extra)
        )
    for artifact_id, expected_schema in sorted(expected.items()):
        record = records[artifact_id]
        require_complete_provenance_record(record)
        if record.schema_name != expected_schema:
            raise ArtifactProvenanceError(
                f"artifact provenance {artifact_id} has schema_name {record.schema_name}; "
                f"expected {expected_schema}"
            )


def _context_source_ids(context: EvidenceContextBundle) -> list[str]:
    return [
        context.extraction.artifact_id,
        context.graph_evidence.artifact_id,
        *[tool.artifact_id for tool in context.tool_outputs],
        context.medea_reasoning.artifact_id,
    ]
