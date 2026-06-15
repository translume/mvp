from __future__ import annotations

from uuid import NAMESPACE_URL, uuid5

from translume_schemas.evidence import EvidenceContextBundle
from translume_schemas.matrix import TherapyEvidenceMatrixOutput
from translume_schemas.phenotype import MolecularPhenotypeOutput
from translume_schemas.sankey import MechanismSankeyOutput, SankeyLink, SankeyNode


def generate_mechanism_sankey_from_context(
    context: EvidenceContextBundle,
    phenotype: MolecularPhenotypeOutput,
    matrix: TherapyEvidenceMatrixOutput,
) -> MechanismSankeyOutput:
    """Create a Finding → Mechanism → Fit → Validation Sankey artifact.

    Acceptance criteria:
        1. Every node has id, label, kind, and evidence class.
        2. Every link source and target exists.
        3. Direction follows Finding → Mechanism → Fit → Validation.
        4. Link weights are visual weights, not probabilities.
        5. Every mechanism link points to source evidence.
        6. Missing evidence is shown as requiring validation.

    Args:
        context: Combined evidence context.
        phenotype: Molecular phenotype artifact.
        matrix: Molecular-fit matrix artifact.

    Returns:
        Mechanism Sankey artifact.
    """
    nodes: list[SankeyNode] = []
    links: list[SankeyLink] = []
    node_ids: set[str] = set()
    for axis, row in zip(phenotype.axes, matrix.rows, strict=False):
        mechanism_id = _node_id(context.artifact_id, "mechanism", axis.label)
        fit_id = _node_id(context.artifact_id, "fit", row.molecular_fit)
        validation_id = _node_id(context.artifact_id, "validation", row.required_validation)
        for finding_id in axis.supporting_finding_ids:
            finding = _finding_label(context, finding_id)
            finding_node_id = _node_id(context.artifact_id, "finding", finding_id)
            _append_node(nodes, node_ids, finding_node_id, finding, "finding", "patient_specific_finding")
            _append_node(nodes, node_ids, mechanism_id, axis.label, "mechanism", axis.evidence_class)
            _append_node(nodes, node_ids, fit_id, row.molecular_fit, "molecular_fit", row.evidence_basis)
            _append_node(nodes, node_ids, validation_id, "Validation: " + row.required_validation, "validation_test", "requires_validation")
            links.extend(
                [
                    _link(finding_node_id, mechanism_id, context.extraction.artifact_id),
                    _link(mechanism_id, fit_id, phenotype.artifact_id),
                    _link(fit_id, validation_id, matrix.artifact_id),
                ]
            )
    artifact_id = f"artifact_{uuid5(NAMESPACE_URL, f'{context.artifact_id}:sankey').hex[:16]}"
    return MechanismSankeyOutput(artifact_id=artifact_id, nodes=nodes, links=links)


def _node_id(seed: str, kind: str, label: str) -> str:
    return f"node_{uuid5(NAMESPACE_URL, f'{seed}:{kind}:{label}').hex[:16]}"


def _append_node(
    nodes: list[SankeyNode],
    node_ids: set[str],
    node_id: str,
    label: str,
    kind: str,
    evidence_class: str,
) -> None:
    if node_id in node_ids:
        return
    node_ids.add(node_id)
    nodes.append(SankeyNode(node_id=node_id, label=label, kind=kind, evidence_class=evidence_class))


def _link(source_id: str, target_id: str, artifact_id: str) -> SankeyLink:
    return SankeyLink(
        source_node_id=source_id,
        target_node_id=target_id,
        value=1.0,
        claim_class="evidence_path_requires_review",
        validation_required=True,
        source_artifact_ids=[artifact_id],
    )


def _finding_label(context: EvidenceContextBundle, finding_id: str) -> str:
    for finding in context.extraction.molecular_findings:
        if finding.finding_id == finding_id:
            prefix = finding.gene or "alteration"
            return f"{prefix}: {finding.alteration}"
    return finding_id
