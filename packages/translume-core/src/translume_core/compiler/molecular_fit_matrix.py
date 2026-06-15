from __future__ import annotations

from uuid import NAMESPACE_URL, uuid5

from translume_schemas.evidence import EvidenceContextBundle
from translume_schemas.matrix import MolecularFitRow, TherapyEvidenceMatrixOutput
from translume_schemas.phenotype import MolecularPhenotypeOutput


def generate_molecular_fit_matrix_from_context(
    context: EvidenceContextBundle,
    phenotype: MolecularPhenotypeOutput,
) -> TherapyEvidenceMatrixOutput:
    """Build molecular-fit rows for expert review without recommendations.

    Acceptance criteria:
        1. Every row has rank.
        2. Every row has why_from_omics.
        3. Every row has evidence_basis and limitations.
        4. Every conditional row has required_validation.
        5. `not_a_recommendation` is true for every row.
        6. No unsafe treatment language is generated.
        7. Molecular-fit labels are derived from phenotype axes rather than
           gene-specific hardcoded mappings.

    Args:
        context: Combined evidence context.
        phenotype: Biological axes artifact.

    Returns:
        Molecular-fit matrix artifact.
    """
    rows: list[MolecularFitRow] = []
    for rank, axis in enumerate(phenotype.axes, start=1):
        molecular_fit = _review_fit_label(axis.label)
        rows.append(
            MolecularFitRow(
                rank=rank,
                molecular_fit=molecular_fit,
                fit_label="reviewable_molecular_fit",
                why_from_omics=(
                    f"Axis '{axis.label}' is supported by report findings "
                    f"{', '.join(axis.supporting_finding_ids)}."
                ),
                evidence_basis=axis.evidence_class,
                limitations=axis.uncertainty,
                required_validation=(
                    "Confirm the source finding and any pathway/protein-level "
                    "relevance before clinical interpretation."
                ),
                not_a_recommendation=True,
            )
        )
    artifact_id = f"artifact_{uuid5(NAMESPACE_URL, f'{context.artifact_id}:matrix').hex[:16]}"
    return TherapyEvidenceMatrixOutput(artifact_id=artifact_id, rows=rows)


def _review_fit_label(axis_label: str) -> str:
    normalized = " ".join(axis_label.split())
    return f"{normalized} review"
