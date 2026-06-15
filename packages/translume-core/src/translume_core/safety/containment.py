from __future__ import annotations

import re

from translume_schemas.export import ClinicalArtifactBundle, ClinicalNarrativeCompilerOutput

_GENE_LIKE = re.compile(r"\b[A-Z][A-Z0-9]{2,9}\b")


def validate_narrative_fact_containment(
    narrative: ClinicalNarrativeCompilerOutput,
    bundle: ClinicalArtifactBundle,
) -> list[str]:
    """Return unsupported gene-like tokens introduced by the narrative.

    Acceptance criteria:
        1. Unsupported gene-like names are flagged.
        2. Empty return list means pass.
        3. Function does not mutate inputs.

    Args:
        narrative: Narrative artifact.
        bundle: Source artifact bundle.

    Returns:
        Unsupported gene-like tokens.
    """
    supported = {
        finding.gene.upper()
        for finding in bundle.extraction.molecular_findings
        if finding.gene
    }
    allowed = supported | {"MVP", "RNA", "DNA", "PDF"}
    tokens = set(_GENE_LIKE.findall(narrative.markdown))
    return sorted(token for token in tokens if token not in allowed)
