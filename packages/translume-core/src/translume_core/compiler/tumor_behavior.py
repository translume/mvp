from __future__ import annotations

from translume_schemas.evidence import EvidenceContextBundle
from translume_schemas.tumor_behavior import TumorBehaviorModelOutput


class LegacyTumorBehaviorDisabledError(RuntimeError):
    """Raised when legacy deterministic tumor-behavior generation is called.

    Acceptance criteria:
        1. Prevents production code from using hardcoded tumor-state templates.
        2. Directs callers to the local vLLM structured-output compiler.
        3. Does not synthesize fallback tumor-state hypotheses.
    """


def generate_tumor_behavior_model_from_context(
    context: EvidenceContextBundle,
) -> TumorBehaviorModelOutput:
    """Fail because tumor behavior must be generated from evidence by local vLLM.

    The previous implementation always produced a fixed proliferative to
    stress-adapted-survival transition. That violated the PRIME_DIRECTIVES
    requirement that tumor-behavior states and transitions be case-derived from
    report text, normalized entities, OptimusKG evidence, ToolUniverse outputs,
    Medea reasoning, and structured local vLLM artifacts.

    Args:
        context: Combined evidence context. Retained only for API compatibility
            while callers are migrated to `generate_tumor_behavior_model_with_model`.

    Raises:
        LegacyTumorBehaviorDisabledError: Always, because this deterministic
            path is not allowed in production or demo execution.
    """
    raise LegacyTumorBehaviorDisabledError(
        "Legacy deterministic tumor-behavior generation is disabled. Use "
        "generate_tumor_behavior_model_with_model with local vLLM structured "
        "outputs and evidence-derived validation."
    )
