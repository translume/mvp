from __future__ import annotations

from uuid import NAMESPACE_URL, uuid5

from translume_schemas.evidence import EvidenceContextBundle
from translume_schemas.extraction import MolecularFinding
from translume_schemas.phenotype import BiologicalAxis, MolecularPhenotypeOutput


def generate_molecular_phenotype_from_context(
    context: EvidenceContextBundle,
) -> MolecularPhenotypeOutput:
    """Build biological axes from report findings and evidence context.

    Acceptance criteria:
        1. Every biological axis references supporting findings.
        2. Graph/tool/Medea evidence may support but not replace report facts.
        3. Every axis has evidence class and uncertainty.
        4. Unsupported axes are marked hypothesis-generating.
        5. Axes may support treatment logic but not unsupported certainty.
        6. No gene-specific clinical mapping is hardcoded in this function.

    Args:
        context: Combined report and enrichment evidence.

    Returns:
        Molecular phenotype artifact.
    """
    grouped: dict[str, list[str]] = {}
    for finding in context.extraction.molecular_findings:
        if not finding.gene:
            continue
        label = _axis_label(finding)
        grouped.setdefault(label, []).append(finding.finding_id)
    axes = [
        BiologicalAxis(
            axis_id=f"axis_{uuid5(NAMESPACE_URL, f'{context.artifact_id}:{label}').hex[:16]}",
            label=label,
            supporting_finding_ids=finding_ids,
            evidence_class=_evidence_class(context),
            uncertainty=(
                "Requires expert review and confirmatory testing before use "
                "in clinical reasoning."
            ),
            validation_needed=True,
        )
        for label, finding_ids in sorted(grouped.items())
    ]
    artifact_id = f"artifact_{uuid5(NAMESPACE_URL, f'{context.artifact_id}:phenotype').hex[:16]}"
    return MolecularPhenotypeOutput(
        artifact_id=artifact_id,
        axes=axes,
        limitations=[
            "Biological axes require oncology review before treatment selection.",
            "Research-use-only expression findings require explicit validation before interpretation.",
        ],
    )


def _axis_label(finding: MolecularFinding) -> str:
    gene = finding.gene.upper()
    alteration_type = finding.alteration_type.replace("_", " ")
    if finding.research_use_only:
        return f"{gene} research-use expression context"
    return f"{gene} {alteration_type} context"


def _evidence_class(context: EvidenceContextBundle) -> str:
    has_graph = bool(context.graph_evidence.edges)
    has_tools = bool(context.tool_outputs)
    has_medea = bool(context.medea_reasoning.summary)
    if has_graph and (has_tools or has_medea):
        return "report_plus_enrichment_supported_context"
    if has_graph:
        return "report_plus_graph_supported_context"
    return "report_supported_hypothesis_requires_validation"
