from __future__ import annotations

from uuid import NAMESPACE_URL, uuid5

from translume_schemas.confirmatory import ConfirmatoryTest, ConfirmatoryTestingOutput
from translume_schemas.evidence import EvidenceContextBundle
from translume_schemas.matrix import TherapyEvidenceMatrixOutput


def generate_confirmatory_testing_from_context(
    context: EvidenceContextBundle,
    matrix: TherapyEvidenceMatrixOutput,
) -> ConfirmatoryTestingOutput:
    """Convert molecular-fit uncertainty into validation tests.

    Acceptance criteria:
        1. Every test answers a specific uncertainty.
        2. Every test links to a finding or molecular-fit row.
        3. Every test explains positive and negative interpretation.
        4. Every test has priority and evidence gap.
        5. Testing questions support treatment logic without unsupported certainty.

    Args:
        context: Combined evidence context.
        matrix: Molecular-fit matrix.

    Returns:
        Confirmatory testing artifact.
    """
    tests: list[ConfirmatoryTest] = []
    for row in matrix.rows:
        test_id = f"test_{uuid5(NAMESPACE_URL, f'{matrix.artifact_id}:{row.rank}').hex[:16]}"
        tests.append(
            ConfirmatoryTest(
                test_id=test_id,
                question=f"Does the evidence support the {row.molecular_fit} context in this tumor?",
                why_it_matters=row.why_from_omics,
                positive_interpretation=(
                    "Would increase confidence that the molecular context is "
                    "relevant to treatment-option review."
                ),
                negative_interpretation="Would weaken or deprioritize the review hypothesis and should be captured in validation notes.",
                priority="review_required",
                evidence_gap=row.required_validation,
                source_claim_ids=[],
            )
        )
    artifact_id = f"artifact_{uuid5(NAMESPACE_URL, f'{context.artifact_id}:confirmatory').hex[:16]}"
    return ConfirmatoryTestingOutput(
        artifact_id=artifact_id,
        tests=tests,
        must_not_assume=[
            "Do not claim certain response, cure, survival benefit, or deterministic outcome.",
            "Use treatment-pressure and monitoring language only when evidence-grounded.",
            "Do not treat research-use-only expression signals as clinically established without validation.",
        ],
    )
