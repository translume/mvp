from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from translume_core.compiler.structured_model_artifacts import (
    StructuredArtifactGenerationError,
    _artifact_id,
    _context_source_chunk_ids,
    _context_source_ids,
    _generate_artifact,
    _validate_safety,
    compact_confirmatory_for_prompt,
    compact_evidence_context_for_prompt,
    compact_matrix_for_prompt,
    compact_phenotype_for_prompt,
    compact_sankey_for_prompt,
    compact_tumor_behavior_for_prompt,
)
from translume_core.provenance.provenance import build_artifact_provenance
from translume_core.performance import run_with_latency_budget
from translume_core.safety.language import SafetyLanguageError
from translume_schemas.confirmatory import ConfirmatoryTestingOutput
from translume_schemas.decision_brief import (
    ActionableBiologyOutput,
    BiomarkerWatchListOutput,
    CurrentTumorStateOutput,
    EvidenceLimitation,
    EvidenceSentence,
    NextTestRecommendationsOutput,
    OncologistDecisionBrief,
    RankedTreatmentOptionsOutput,
    ResistanceForecastOutput,
    RetestingTriggersOutput,
    TranslationalAssessmentOutput,
    TranslationalQuestionAssessment,
    TreatmentPressureMapOutput,
    TherapyEscapeSankeyPath,
)
from translume_schemas.evidence import EvidenceContextBundle
from translume_schemas.matrix import TherapyEvidenceMatrixOutput
from translume_schemas.phenotype import MolecularPhenotypeOutput
from translume_schemas.provenance import ArtifactProvenance
from translume_schemas.sankey import MechanismSankeyOutput
from translume_schemas.tumor_behavior import TumorBehaviorModelOutput


_DECISION_STAGE_PROMPT_CHAR_BUDGETS = {
    "current_tumor_state": 32000,
    "actionable_biology": 28000,
    "ranked_treatment_options": 32000,
    "treatment_pressure_map": 30000,
    "resistance_escape_forecast": 34000,
    "biomarker_watch_list": 28000,
    "retesting_triggers": 24000,
    "next_test_recommendations": 24000,
    "translational_assessment": 32000,
    "oncologist_decision_brief_synthesis": 40000,
}
_DEFAULT_DECISION_STAGE_PROMPT_CHAR_BUDGET = 28000


@dataclass(frozen=True)
class DecisionBriefLatencyBudgets:
    """Latency budgets for independently callable decision-brief stages."""

    default_timeout_seconds: float | None = None
    stage_timeout_seconds: Mapping[str, float] = field(default_factory=dict)

    def for_stage(self, stage_name: str) -> float | None:
        """Return the timeout for a stage, allowing full or short stage keys."""
        short_name = stage_name.split(".")[-1]
        if stage_name in self.stage_timeout_seconds:
            return self.stage_timeout_seconds[stage_name]
        if short_name in self.stage_timeout_seconds:
            return self.stage_timeout_seconds[short_name]
        return self.default_timeout_seconds


def _decision_stage_budget(
    latency_budgets: DecisionBriefLatencyBudgets | None,
    stage_name: str,
) -> float | None:
    if latency_budgets is None:
        return None
    return latency_budgets.for_stage(stage_name)


async def _generate_decision_stage_artifact(
    *,
    stage_name: str,
    latency_budgets: DecisionBriefLatencyBudgets | None,
    **kwargs: Any,
):
    """Generate one stage artifact under its configured latency budget."""
    full_stage_name = f"decision_brief.{stage_name}"
    return await run_with_latency_budget(
        stage_name=full_stage_name,
        timeout_seconds=_decision_stage_budget(latency_budgets, full_stage_name),
        awaitable=_generate_artifact(**kwargs),
    )


@dataclass(frozen=True)
class DecisionBriefGenerationResult:
    """Final decision brief plus provenance for the exported artifact."""

    artifact: OncologistDecisionBrief
    provenance: ArtifactProvenance


async def generate_oncologist_decision_brief_with_model(
    *,
    context: EvidenceContextBundle,
    phenotype: MolecularPhenotypeOutput,
    matrix: TherapyEvidenceMatrixOutput,
    sankey: MechanismSankeyOutput,
    confirmatory: ConfirmatoryTestingOutput,
    tumor_behavior: TumorBehaviorModelOutput,
    model_provider: object,
    model_name: str,
    prompts_root: Path,
    created_at: datetime,
    latency_budgets: DecisionBriefLatencyBudgets | None = None,
) -> DecisionBriefGenerationResult:
    """Generate a staged oncologist decision brief through local vLLM.

    Acceptance criteria:
        1. Runs each decision prompt stage independently.
        2. Applies schema validation, repair retry, and evidence checks to stage
           outputs before synthesis.
        3. Synthesizes the final brief deterministically from stage outputs only.
        4. Rejects unsupported certainty language.
        5. Carries source artifact and source chunk lineage.

    Args:
        context: Combined report, graph, tool, and Medea evidence.
        phenotype: Molecular phenotype artifact.
        matrix: Treatment/molecular-fit evidence matrix.
        sankey: Mechanism Sankey artifact.
        confirmatory: Confirmatory testing artifact.
        tumor_behavior: Tumor behavior / resistance-state artifact.
        model_provider: Local structured-output model provider.
        model_name: Local vLLM model name.
        prompts_root: Directory containing prompt templates.
        created_at: Provenance timestamp.

    Returns:
        Final decision brief with provenance.
    """
    stage_outputs = await generate_decision_brief_stage_outputs_with_model(
        context=context,
        phenotype=phenotype,
        matrix=matrix,
        sankey=sankey,
        confirmatory=confirmatory,
        tumor_behavior=tumor_behavior,
        model_provider=model_provider,
        model_name=model_name,
        prompts_root=prompts_root,
        created_at=created_at,
        latency_budgets=latency_budgets,
    )
    source_artifact_ids = decision_stage_source_ids(
        context=context,
        phenotype=phenotype,
        matrix=matrix,
        sankey=sankey,
        confirmatory=confirmatory,
        tumor_behavior=tumor_behavior,
        stage_artifact_ids=stage_outputs.artifact_ids(),
    )
    artifact = synthesize_oncologist_decision_brief_from_stage_outputs(
        planned_artifact_id=_artifact_id(context.artifact_id, "OncologistDecisionBrief"),
        stage_outputs=stage_outputs,
        source_artifact_ids=source_artifact_ids,
        source_chunk_ids=_context_source_chunk_ids(context),
    )
    _validate_decision_brief(artifact)
    require_decision_brief_matches_stage_outputs(
        brief=artifact,
        **stage_outputs.as_validation_kwargs(),
    )
    provenance = build_artifact_provenance(
        artifact_type="OncologistDecisionBrief",
        schema_name="OncologistDecisionBrief",
        model_name="decision_brief_deterministic_synthesis",
        prompt_text=None,
        schema_json=OncologistDecisionBrief.model_json_schema(),
        source_artifact_ids=source_artifact_ids,
        source_chunk_ids=_context_source_chunk_ids(context),
        source_file_id=context.extraction.source_file_id,
        created_at=created_at,
        generation_status="deterministic_synthesis",
        artifact_id=artifact.artifact_id,
    )
    return DecisionBriefGenerationResult(artifact=artifact, provenance=provenance)


@dataclass(frozen=True)
class DecisionBriefStageOutputs:
    """All independently generated prompt-stage outputs for a decision brief."""

    current_state: CurrentTumorStateOutput
    actionable_biology: ActionableBiologyOutput
    treatment_options: RankedTreatmentOptionsOutput
    treatment_pressure: TreatmentPressureMapOutput
    resistance_forecast: ResistanceForecastOutput
    biomarker_watch: BiomarkerWatchListOutput
    retesting_triggers: RetestingTriggersOutput
    next_tests: NextTestRecommendationsOutput
    translational_assessment: TranslationalAssessmentOutput
    evidence_sentence_map: tuple[EvidenceSentence, ...] = ()

    def artifact_ids(self) -> list[str]:
        """Return stage artifact IDs in synthesis order."""
        return [
            self.current_state.artifact_id,
            self.actionable_biology.artifact_id,
            self.treatment_options.artifact_id,
            self.treatment_pressure.artifact_id,
            self.resistance_forecast.artifact_id,
            self.biomarker_watch.artifact_id,
            self.retesting_triggers.artifact_id,
            self.next_tests.artifact_id,
            *(
                [self.translational_assessment.artifact_id]
                if self.translational_assessment is not None
                else []
            ),
        ]

    def as_validation_kwargs(self) -> dict[str, object]:
        """Return keyword arguments accepted by stage validators."""
        return {
            "current_state": self.current_state,
            "actionable_biology": self.actionable_biology,
            "treatment_options": self.treatment_options,
            "treatment_pressure": self.treatment_pressure,
            "resistance_forecast": self.resistance_forecast,
            "biomarker_watch": self.biomarker_watch,
            "retesting_triggers": self.retesting_triggers,
            "next_tests": self.next_tests,
            "translational_assessment": self.translational_assessment,
        }


async def generate_decision_brief_stage_outputs_with_model(
    *,
    context: EvidenceContextBundle,
    phenotype: MolecularPhenotypeOutput,
    matrix: TherapyEvidenceMatrixOutput,
    sankey: MechanismSankeyOutput,
    confirmatory: ConfirmatoryTestingOutput,
    tumor_behavior: TumorBehaviorModelOutput,
    model_provider: object,
    model_name: str,
    prompts_root: Path,
    created_at: datetime,
    latency_budgets: DecisionBriefLatencyBudgets | None = None,
) -> DecisionBriefStageOutputs:
    """Generate and validate each decision-brief prompt stage.

    Acceptance criteria:
        1. Each prompt stage is callable and testable as its own function.
        2. Stage dependencies are explicit in function arguments.
        3. Malformed stage outputs use the shared structured-output repair path.
        4. Stage outputs are evidence-grounded before final synthesis.
        5. The function returns immutable Pydantic artifacts only.

    Args:
        context: Combined evidence context.
        phenotype: Molecular phenotype artifact.
        matrix: Treatment/molecular-fit evidence matrix.
        sankey: Mechanism Sankey artifact.
        confirmatory: Confirmatory testing artifact.
        tumor_behavior: Tumor behavior artifact.
        model_provider: Local structured-output model provider.
        model_name: Local vLLM model name.
        prompts_root: Directory containing prompt files.
        created_at: Provenance timestamp.

    Returns:
        Validated stage outputs for deterministic synthesis.
    """
    current_state = await generate_current_tumor_state_stage_with_model(
        context=context,
        model_provider=model_provider,
        model_name=model_name,
        prompts_root=prompts_root,
        created_at=created_at,
        latency_budgets=latency_budgets,
    )
    actionable_biology = await generate_actionable_biology_stage_with_model(
        context=context,
        current_state=current_state,
        model_provider=model_provider,
        model_name=model_name,
        prompts_root=prompts_root,
        created_at=created_at,
        latency_budgets=latency_budgets,
    )
    treatment_options = await generate_treatment_options_stage_with_model(
        context=context,
        phenotype=phenotype,
        matrix=matrix,
        actionable_biology=actionable_biology,
        model_provider=model_provider,
        model_name=model_name,
        prompts_root=prompts_root,
        created_at=created_at,
        latency_budgets=latency_budgets,
    )
    treatment_pressure = await generate_treatment_pressure_stage_with_model(
        context=context,
        treatment_options=treatment_options,
        phenotype=phenotype,
        sankey=sankey,
        model_provider=model_provider,
        model_name=model_name,
        prompts_root=prompts_root,
        created_at=created_at,
        latency_budgets=latency_budgets,
    )
    resistance_forecast = await generate_resistance_forecast_stage_with_model(
        context=context,
        treatment_pressure=treatment_pressure,
        tumor_behavior=tumor_behavior,
        sankey=sankey,
        model_provider=model_provider,
        model_name=model_name,
        prompts_root=prompts_root,
        created_at=created_at,
        latency_budgets=latency_budgets,
    )
    biomarker_watch = await generate_biomarker_watch_stage_with_model(
        context=context,
        resistance_forecast=resistance_forecast,
        treatment_pressure=treatment_pressure,
        model_provider=model_provider,
        model_name=model_name,
        prompts_root=prompts_root,
        created_at=created_at,
        latency_budgets=latency_budgets,
    )
    retesting_triggers = await generate_retesting_triggers_stage_with_model(
        context=context,
        biomarker_watch=biomarker_watch,
        confirmatory=confirmatory,
        model_provider=model_provider,
        model_name=model_name,
        prompts_root=prompts_root,
        created_at=created_at,
        latency_budgets=latency_budgets,
    )
    next_tests = await generate_next_test_stage_with_model(
        context=context,
        biomarker_watch=biomarker_watch,
        retesting_triggers=retesting_triggers,
        confirmatory=confirmatory,
        model_provider=model_provider,
        model_name=model_name,
        prompts_root=prompts_root,
        created_at=created_at,
        latency_budgets=latency_budgets,
    )
    translational_assessment = await generate_translational_assessment_stage_with_model(
        context=context,
        current_state=current_state,
        actionable_biology=actionable_biology,
        treatment_options=treatment_options,
        treatment_pressure=treatment_pressure,
        resistance_forecast=resistance_forecast,
        biomarker_watch=biomarker_watch,
        retesting_triggers=retesting_triggers,
        next_tests=next_tests,
        model_provider=model_provider,
        model_name=model_name,
        prompts_root=prompts_root,
        created_at=created_at,
        latency_budgets=latency_budgets,
    )
    evidence_sentence_map = build_evidence_sentence_map_from_context(context)
    translational_assessment = enforce_patient_population_alignment_and_evidence_labels(
        translational_assessment,
        context=context,
        evidence_sentence_map=evidence_sentence_map,
    )
    stage_outputs = DecisionBriefStageOutputs(
        current_state=current_state,
        actionable_biology=actionable_biology,
        treatment_options=treatment_options,
        treatment_pressure=treatment_pressure,
        resistance_forecast=resistance_forecast,
        biomarker_watch=biomarker_watch,
        retesting_triggers=retesting_triggers,
        next_tests=next_tests,
        translational_assessment=translational_assessment,
        evidence_sentence_map=tuple(evidence_sentence_map),
    )
    require_decision_stage_outputs_evidence_grounded(
        **stage_outputs.as_validation_kwargs()
    )
    return stage_outputs


async def generate_current_tumor_state_stage_with_model(
    *,
    context: EvidenceContextBundle,
    model_provider: object,
    model_name: str,
    prompts_root: Path,
    created_at: datetime,
    latency_budgets: DecisionBriefLatencyBudgets | None = None,
) -> CurrentTumorStateOutput:
    """Generate the current tumor state prompt stage."""
    result = await _generate_decision_stage_artifact(
        stage_name="current_tumor_state",
        latency_budgets=latency_budgets,
        prompt_name="current_tumor_state",
        schema_model=CurrentTumorStateOutput,
        planned_artifact_id=_artifact_id(context.artifact_id, "CurrentTumorStateOutput"),
        payload=build_current_state_prompt_packet(context),
        source_artifact_ids=_context_source_ids(context),
        source_chunk_ids=_context_source_chunk_ids(context),
        source_file_id=context.extraction.source_file_id,
        model_provider=model_provider,
        model_name=model_name,
        prompts_root=prompts_root,
        created_at=created_at,
    )
    return result.artifact


async def generate_actionable_biology_stage_with_model(
    *,
    context: EvidenceContextBundle,
    current_state: CurrentTumorStateOutput,
    model_provider: object,
    model_name: str,
    prompts_root: Path,
    created_at: datetime,
    latency_budgets: DecisionBriefLatencyBudgets | None = None,
) -> ActionableBiologyOutput:
    """Generate the actionable biology prompt stage."""
    result = await _generate_decision_stage_artifact(
        stage_name="actionable_biology",
        latency_budgets=latency_budgets,
        prompt_name="actionable_biology",
        schema_model=ActionableBiologyOutput,
        planned_artifact_id=_artifact_id(context.artifact_id, "ActionableBiologyOutput"),
        payload=build_actionable_biology_prompt_packet(
            context=context,
            current_state=current_state,
        ),
        source_artifact_ids=[*_context_source_ids(context), current_state.artifact_id],
        source_chunk_ids=_context_source_chunk_ids(context),
        source_file_id=context.extraction.source_file_id,
        model_provider=model_provider,
        model_name=model_name,
        prompts_root=prompts_root,
        created_at=created_at,
    )
    return result.artifact


async def generate_treatment_options_stage_with_model(
    *,
    context: EvidenceContextBundle,
    phenotype: MolecularPhenotypeOutput,
    matrix: TherapyEvidenceMatrixOutput,
    actionable_biology: ActionableBiologyOutput,
    model_provider: object,
    model_name: str,
    prompts_root: Path,
    created_at: datetime,
    latency_budgets: DecisionBriefLatencyBudgets | None = None,
) -> RankedTreatmentOptionsOutput:
    """Generate the ranked treatment options prompt stage."""
    planned_artifact_id = _artifact_id(
        context.artifact_id,
        "RankedTreatmentOptionsOutput",
    )
    payload = build_treatment_options_prompt_packet(
        context=context,
        phenotype=phenotype,
        matrix=matrix,
        actionable_biology=actionable_biology,
    )
    source_artifact_ids = [
        *_context_source_ids(context),
        phenotype.artifact_id,
        matrix.artifact_id,
        actionable_biology.artifact_id,
    ]
    result = await _generate_decision_stage_artifact(
        stage_name="ranked_treatment_options",
        latency_budgets=latency_budgets,
        prompt_name="ranked_treatment_options",
        schema_model=RankedTreatmentOptionsOutput,
        planned_artifact_id=planned_artifact_id,
        payload=payload,
        source_artifact_ids=source_artifact_ids,
        source_chunk_ids=_context_source_chunk_ids(context),
        source_file_id=context.extraction.source_file_id,
        model_provider=model_provider,
        model_name=model_name,
        prompts_root=prompts_root,
        created_at=created_at,
    )
    normalized_artifact = _normalize_ranked_treatment_required_lists(
        result.artifact,
        matrix=matrix,
        actionable_biology=actionable_biology,
    )
    try:
        _validate_ranked_treatment_options_output(normalized_artifact)
    except StructuredArtifactGenerationError as error:
        if not _is_empty_required_before_use_tests_error(error):
            raise
        result = await _generate_decision_stage_artifact(
            stage_name="ranked_treatment_options",
            latency_budgets=latency_budgets,
            prompt_name="ranked_treatment_options",
            schema_model=RankedTreatmentOptionsOutput,
            planned_artifact_id=planned_artifact_id,
            payload=_ranked_treatment_options_repair_payload(
                payload,
                error=error,
                matrix=matrix,
                actionable_biology=actionable_biology,
            ),
            source_artifact_ids=source_artifact_ids,
            source_chunk_ids=_context_source_chunk_ids(context),
            source_file_id=context.extraction.source_file_id,
            model_provider=model_provider,
            model_name=model_name,
            prompts_root=prompts_root,
            created_at=created_at,
        )
        normalized_artifact = _normalize_ranked_treatment_required_lists(
            result.artifact,
            matrix=matrix,
            actionable_biology=actionable_biology,
        )
        _validate_ranked_treatment_options_output(normalized_artifact)
    return normalized_artifact


async def generate_treatment_pressure_stage_with_model(
    *,
    context: EvidenceContextBundle,
    treatment_options: RankedTreatmentOptionsOutput,
    phenotype: MolecularPhenotypeOutput,
    sankey: MechanismSankeyOutput,
    model_provider: object,
    model_name: str,
    prompts_root: Path,
    created_at: datetime,
    latency_budgets: DecisionBriefLatencyBudgets | None = None,
) -> TreatmentPressureMapOutput:
    """Generate the treatment pressure prompt stage."""
    result = await _generate_decision_stage_artifact(
        stage_name="treatment_pressure",
        latency_budgets=latency_budgets,
        prompt_name="treatment_pressure",
        schema_model=TreatmentPressureMapOutput,
        planned_artifact_id=_artifact_id(context.artifact_id, "TreatmentPressureMapOutput"),
        payload=build_treatment_pressure_prompt_packet(
            context=context,
            treatment_options=treatment_options,
            phenotype=phenotype,
            sankey=sankey,
        ),
        source_artifact_ids=[
            *_context_source_ids(context),
            phenotype.artifact_id,
            sankey.artifact_id,
            treatment_options.artifact_id,
        ],
        source_chunk_ids=_context_source_chunk_ids(context),
        source_file_id=context.extraction.source_file_id,
        model_provider=model_provider,
        model_name=model_name,
        prompts_root=prompts_root,
        created_at=created_at,
    )
    return result.artifact


async def generate_resistance_forecast_stage_with_model(
    *,
    context: EvidenceContextBundle,
    treatment_pressure: TreatmentPressureMapOutput,
    tumor_behavior: TumorBehaviorModelOutput,
    sankey: MechanismSankeyOutput,
    model_provider: object,
    model_name: str,
    prompts_root: Path,
    created_at: datetime,
    latency_budgets: DecisionBriefLatencyBudgets | None = None,
) -> ResistanceForecastOutput:
    """Generate the resistance forecast prompt stage."""
    result = await _generate_decision_stage_artifact(
        stage_name="resistance_forecast",
        latency_budgets=latency_budgets,
        prompt_name="resistance_forecast",
        schema_model=ResistanceForecastOutput,
        planned_artifact_id=_artifact_id(context.artifact_id, "ResistanceForecastOutput"),
        payload=build_escape_forecast_prompt_packet(
            context=context,
            treatment_pressure=treatment_pressure,
            tumor_behavior=tumor_behavior,
            sankey=sankey,
        ),
        source_artifact_ids=[
            *_context_source_ids(context),
            sankey.artifact_id,
            tumor_behavior.artifact_id,
            treatment_pressure.artifact_id,
        ],
        source_chunk_ids=_context_source_chunk_ids(context),
        source_file_id=context.extraction.source_file_id,
        model_provider=model_provider,
        model_name=model_name,
        prompts_root=prompts_root,
        created_at=created_at,
    )
    return result.artifact


async def generate_biomarker_watch_stage_with_model(
    *,
    context: EvidenceContextBundle,
    resistance_forecast: ResistanceForecastOutput,
    treatment_pressure: TreatmentPressureMapOutput,
    model_provider: object,
    model_name: str,
    prompts_root: Path,
    created_at: datetime,
    latency_budgets: DecisionBriefLatencyBudgets | None = None,
) -> BiomarkerWatchListOutput:
    """Generate the biomarker watch-list prompt stage."""
    result = await _generate_decision_stage_artifact(
        stage_name="biomarker_watch_list",
        latency_budgets=latency_budgets,
        prompt_name="biomarker_watch_list",
        schema_model=BiomarkerWatchListOutput,
        planned_artifact_id=_artifact_id(context.artifact_id, "BiomarkerWatchListOutput"),
        payload=build_biomarker_watch_prompt_packet(
            context=context,
            resistance_forecast=resistance_forecast,
            treatment_pressure=treatment_pressure,
        ),
        source_artifact_ids=[
            *_context_source_ids(context),
            resistance_forecast.artifact_id,
            treatment_pressure.artifact_id,
        ],
        source_chunk_ids=_context_source_chunk_ids(context),
        source_file_id=context.extraction.source_file_id,
        model_provider=model_provider,
        model_name=model_name,
        prompts_root=prompts_root,
        created_at=created_at,
    )
    return result.artifact


async def generate_retesting_triggers_stage_with_model(
    *,
    context: EvidenceContextBundle,
    biomarker_watch: BiomarkerWatchListOutput,
    confirmatory: ConfirmatoryTestingOutput,
    model_provider: object,
    model_name: str,
    prompts_root: Path,
    created_at: datetime,
    latency_budgets: DecisionBriefLatencyBudgets | None = None,
) -> RetestingTriggersOutput:
    """Generate the re-testing trigger prompt stage."""
    result = await _generate_decision_stage_artifact(
        stage_name="retesting_triggers",
        latency_budgets=latency_budgets,
        prompt_name="retesting_triggers",
        schema_model=RetestingTriggersOutput,
        planned_artifact_id=_artifact_id(context.artifact_id, "RetestingTriggersOutput"),
        payload=build_retesting_trigger_prompt_packet(
            context=context,
            biomarker_watch=biomarker_watch,
            confirmatory=confirmatory,
        ),
        source_artifact_ids=[
            *_context_source_ids(context),
            confirmatory.artifact_id,
            biomarker_watch.artifact_id,
        ],
        source_chunk_ids=_context_source_chunk_ids(context),
        source_file_id=context.extraction.source_file_id,
        model_provider=model_provider,
        model_name=model_name,
        prompts_root=prompts_root,
        created_at=created_at,
    )
    return result.artifact


async def generate_next_test_stage_with_model(
    *,
    context: EvidenceContextBundle,
    biomarker_watch: BiomarkerWatchListOutput,
    retesting_triggers: RetestingTriggersOutput,
    confirmatory: ConfirmatoryTestingOutput,
    model_provider: object,
    model_name: str,
    prompts_root: Path,
    created_at: datetime,
    latency_budgets: DecisionBriefLatencyBudgets | None = None,
) -> NextTestRecommendationsOutput:
    """Generate the next-test recommendation prompt stage."""
    result = await _generate_decision_stage_artifact(
        stage_name="next_test_recommendation",
        latency_budgets=latency_budgets,
        prompt_name="next_test_recommendation",
        schema_model=NextTestRecommendationsOutput,
        planned_artifact_id=_artifact_id(
            context.artifact_id,
            "NextTestRecommendationsOutput",
        ),
        payload=build_next_test_prompt_packet(
            context=context,
            biomarker_watch=biomarker_watch,
            retesting_triggers=retesting_triggers,
            confirmatory=confirmatory,
        ),
        source_artifact_ids=[
            *_context_source_ids(context),
            confirmatory.artifact_id,
            biomarker_watch.artifact_id,
            retesting_triggers.artifact_id,
        ],
        source_chunk_ids=_context_source_chunk_ids(context),
        source_file_id=context.extraction.source_file_id,
        model_provider=model_provider,
        model_name=model_name,
        prompts_root=prompts_root,
        created_at=created_at,
    )
    return result.artifact


async def generate_translational_assessment_stage_with_model(
    *,
    context: EvidenceContextBundle,
    current_state: CurrentTumorStateOutput,
    actionable_biology: ActionableBiologyOutput,
    treatment_options: RankedTreatmentOptionsOutput,
    treatment_pressure: TreatmentPressureMapOutput,
    resistance_forecast: ResistanceForecastOutput,
    biomarker_watch: BiomarkerWatchListOutput,
    retesting_triggers: RetestingTriggersOutput,
    next_tests: NextTestRecommendationsOutput,
    model_provider: object,
    model_name: str,
    prompts_root: Path,
    created_at: datetime,
    latency_budgets: DecisionBriefLatencyBudgets | None = None,
) -> TranslationalAssessmentOutput:
    """Generate the five-question translational assessment prompt stage.

    Acceptance criteria:
        1. Uses only upstream staged decision-brief outputs and evidence context.
        2. Answers the five MVP translational questions explicitly.
        3. Marks patient-population fit as unresolved unless evidence is present.
        4. Preserves row-level evidence or unresolved-evidence status.
        5. Rejects unsupported certainty language through shared validation.
    """
    result = await _generate_decision_stage_artifact(
        stage_name="translational_assessment",
        latency_budgets=latency_budgets,
        prompt_name="translational_assessment",
        schema_model=TranslationalAssessmentOutput,
        planned_artifact_id=_artifact_id(
            context.artifact_id,
            "TranslationalAssessmentOutput",
        ),
        payload=build_translational_assessment_prompt_packet(
            context=context,
            current_state=current_state,
            actionable_biology=actionable_biology,
            treatment_options=treatment_options,
            treatment_pressure=treatment_pressure,
            resistance_forecast=resistance_forecast,
            biomarker_watch=biomarker_watch,
            retesting_triggers=retesting_triggers,
            next_tests=next_tests,
        ),
        source_artifact_ids=[
            *_context_source_ids(context),
            current_state.artifact_id,
            actionable_biology.artifact_id,
            treatment_options.artifact_id,
            treatment_pressure.artifact_id,
            resistance_forecast.artifact_id,
            biomarker_watch.artifact_id,
            retesting_triggers.artifact_id,
            next_tests.artifact_id,
        ],
        source_chunk_ids=_context_source_chunk_ids(context),
        source_file_id=context.extraction.source_file_id,
        model_provider=model_provider,
        model_name=model_name,
        prompts_root=prompts_root,
        created_at=created_at,
    )
    return result.artifact


def build_current_state_prompt_packet(
    context: EvidenceContextBundle,
) -> dict[str, object]:
    """Return task-specific context for current tumor state reasoning."""
    compact = compact_evidence_context_for_prompt(context)
    return _with_prompt_budget("current_tumor_state", {
        "task": "current_tumor_state",
        "evidence_context": compact,
        "required_output_focus": [
            "dominant drivers",
            "active pathways",
            "co-drivers",
            "actionable and uncertain alterations",
            "immune and DNA repair context",
            "missing data",
        ],
    })


def build_actionable_biology_prompt_packet(
    *,
    context: EvidenceContextBundle,
    current_state: CurrentTumorStateOutput,
) -> dict[str, object]:
    """Return task-specific context for actionable biology extraction."""
    compact = compact_evidence_context_for_prompt(context)
    return _with_prompt_budget("actionable_biology", {
        "task": "actionable_biology",
        "current_tumor_state": current_state.model_dump(mode="json"),
        "report_biomarkers_and_findings": compact["extraction"],
        "graph_evidence": compact["graph_evidence"],
        "tool_outputs": _tool_outputs_by_workflow(
            compact["tool_outputs"],
            {
                "variant_context",
                "target_context",
                "therapy_context",
                "guideline_context",
            },
        ),
        "missing_evidence": compact["missing_evidence"],
        "conflicting_evidence": compact["conflicting_evidence"],
    })


def build_treatment_options_prompt_packet(
    *,
    context: EvidenceContextBundle,
    phenotype: MolecularPhenotypeOutput,
    matrix: TherapyEvidenceMatrixOutput,
    actionable_biology: ActionableBiologyOutput,
) -> dict[str, object]:
    """Return task-specific context for ranked treatment options."""
    compact = compact_evidence_context_for_prompt(context)
    return _with_prompt_budget("ranked_treatment_options", {
        "task": "ranked_treatment_options",
        "actionable_biology": actionable_biology.model_dump(mode="json"),
        "molecular_phenotype": compact_phenotype_for_prompt(phenotype),
        "molecular_fit_matrix": compact_matrix_for_prompt(matrix),
        "graph_evidence": compact["graph_evidence"],
        "tool_outputs": _tool_outputs_by_workflow(
            compact["tool_outputs"],
            {
                "therapy_context",
                "guideline_context",
                "clinical_trial_context",
                "trial_context_review",
                "recent_therapy_agent_backfill_context",
                "target_context",
            },
        ),
        "clinical_use_categories": [
            "approved_option",
            "guideline_supported",
            "off_label_rationale",
            "trial_option",
            "avoid_or_deprioritize",
            "insufficient_evidence",
        ],
    })


def build_treatment_pressure_prompt_packet(
    *,
    context: EvidenceContextBundle,
    treatment_options: RankedTreatmentOptionsOutput,
    phenotype: MolecularPhenotypeOutput,
    sankey: MechanismSankeyOutput,
) -> dict[str, object]:
    """Return task-specific context for treatment pressure mapping."""
    compact = compact_evidence_context_for_prompt(context)
    return _with_prompt_budget("treatment_pressure_map", {
        "task": "treatment_pressure_map",
        "ranked_treatment_options": treatment_options.model_dump(mode="json"),
        "molecular_phenotype": compact_phenotype_for_prompt(phenotype),
        "mechanism_sankey": compact_sankey_for_prompt(sankey),
        "pathway_context": compact["graph_evidence"],
        "tool_outputs": _tool_outputs_by_workflow(
            compact["tool_outputs"],
            {"pathway_context", "therapy_context", "resistance_mechanism_context"},
        ),
    })


def build_escape_forecast_prompt_packet(
    *,
    context: EvidenceContextBundle,
    treatment_pressure: TreatmentPressureMapOutput,
    tumor_behavior: TumorBehaviorModelOutput,
    sankey: MechanismSankeyOutput,
) -> dict[str, object]:
    """Return task-specific context for resistance/escape forecasting."""
    compact = compact_evidence_context_for_prompt(context)
    return _with_prompt_budget("resistance_escape_forecast", {
        "task": "resistance_escape_forecast",
        "treatment_pressure_map": treatment_pressure.model_dump(mode="json"),
        "tumor_behavior": compact_tumor_behavior_for_prompt(tumor_behavior),
        "mechanism_sankey": compact_sankey_for_prompt(sankey),
        "graph_evidence": compact["graph_evidence"],
        "tool_outputs": _tool_outputs_by_workflow(
            compact["tool_outputs"],
            {
                "resistance_mechanism_context",
                "lineage_transformation_context",
                "pathway_context",
                "therapy_context",
            },
        ),
        "medea_reasoning": compact["medea_reasoning"],
        "escape_route_categories": [
            "bypass_signaling",
            "secondary_resistance_mutation",
            "copy_number_evolution",
            "fusion_rearrangement_evolution",
            "dna_repair_restoration",
            "immune_escape",
            "histologic_transformation",
            "resistant_subclone_expansion",
            "other",
        ],
    })


def build_biomarker_watch_prompt_packet(
    *,
    context: EvidenceContextBundle,
    resistance_forecast: ResistanceForecastOutput,
    treatment_pressure: TreatmentPressureMapOutput,
) -> dict[str, object]:
    """Return task-specific context for biomarker watch-list generation."""
    compact = compact_evidence_context_for_prompt(context)
    return _with_prompt_budget("biomarker_watch_list", {
        "task": "biomarker_watch_list",
        "current_report_findings": compact["extraction"],
        "resistance_forecast": resistance_forecast.model_dump(mode="json"),
        "treatment_pressure_map": treatment_pressure.model_dump(mode="json"),
        "graph_evidence": compact["graph_evidence"],
        "tool_outputs": _tool_outputs_by_workflow(
            compact["tool_outputs"],
            {
                "biomarker_retesting_context",
                "resistance_mechanism_context",
                "variant_context",
                "pathway_context",
            },
        ),
        "preferred_test_modalities": _test_modalities(),
    })


def build_retesting_trigger_prompt_packet(
    *,
    context: EvidenceContextBundle,
    biomarker_watch: BiomarkerWatchListOutput,
    confirmatory: ConfirmatoryTestingOutput,
) -> dict[str, object]:
    """Return task-specific context for re-testing triggers."""
    compact = compact_evidence_context_for_prompt(context)
    return _with_prompt_budget("retesting_triggers", {
        "task": "retesting_triggers",
        "disease_and_specimen_context": compact["extraction"],
        "biomarker_watch_list": biomarker_watch.model_dump(mode="json"),
        "confirmatory_testing": compact_confirmatory_for_prompt(confirmatory),
        "graph_evidence": compact["graph_evidence"],
        "tool_outputs": _tool_outputs_by_workflow(
            compact["tool_outputs"],
            {"biomarker_retesting_context", "guideline_context"},
        ),
        "event_based_trigger_categories": [
            "radiographic progression",
            "mixed response or oligoprogression",
            "rapid progression on targeted therapy",
            "rising tumor markers before imaging progression",
            "new metastatic site",
            "before switching systemic therapy",
            "ctDNA-negative progression",
            "suspected histologic transformation",
        ],
        "preferred_test_modalities": _test_modalities(),
    })


def build_next_test_prompt_packet(
    *,
    context: EvidenceContextBundle,
    biomarker_watch: BiomarkerWatchListOutput,
    retesting_triggers: RetestingTriggersOutput,
    confirmatory: ConfirmatoryTestingOutput,
) -> dict[str, object]:
    """Return task-specific context for next-test recommendations."""
    compact = compact_evidence_context_for_prompt(context)
    return _with_prompt_budget("next_test_recommendations", {
        "task": "next_test_recommendations",
        "current_report_limitations": compact["extraction"].get("assay_limitations", []),
        "biomarker_watch_list": biomarker_watch.model_dump(mode="json"),
        "retesting_triggers": retesting_triggers.model_dump(mode="json"),
        "confirmatory_testing": compact_confirmatory_for_prompt(confirmatory),
        "graph_evidence": compact["graph_evidence"],
        "tool_outputs": _tool_outputs_by_workflow(
            compact["tool_outputs"],
            {"biomarker_retesting_context", "guideline_context"},
        ),
        "preferred_test_modalities": _test_modalities(),
    })


def build_translational_assessment_prompt_packet(
    *,
    context: EvidenceContextBundle,
    current_state: CurrentTumorStateOutput,
    actionable_biology: ActionableBiologyOutput,
    treatment_options: RankedTreatmentOptionsOutput,
    treatment_pressure: TreatmentPressureMapOutput,
    resistance_forecast: ResistanceForecastOutput,
    biomarker_watch: BiomarkerWatchListOutput,
    retesting_triggers: RetestingTriggersOutput,
    next_tests: NextTestRecommendationsOutput,
) -> dict[str, object]:
    """Return task-specific context for five-question assessment.

    Acceptance criteria:
        1. Includes only staged rows and targeted evidence needed for the
           translational questions.
        2. Preserves upstream evidence/unresolved evidence fields.
        3. Provides explicit question keys expected by the schema.
        4. Does not perform model-like inference in packet construction.
    """
    compact = compact_evidence_context_for_prompt(context)
    return _with_prompt_budget("translational_assessment", {
        "task": "five_question_translational_assessment",
        "questions": [
            {
                "question_key": "target_relevance",
                "question": "Is the target actually relevant to this tumor's behavior?",
            },
            {
                "question_key": "biomarker_evidence",
                "question": (
                    "Does the biomarker evidence support action, or is it "
                    "weak/incomplete?"
                ),
            },
            {
                "question_key": "resistance_mechanisms",
                "question": (
                    "Are resistance mechanisms already present or likely to emerge?"
                ),
            },
            {
                "question_key": "patient_population_alignment",
                "question": (
                    "Is the patient population aligned with the evidence behind "
                    "the treatment?"
                ),
            },
            {
                "question_key": "evidence_resolution",
                "question": (
                    "What evidence is strong, what is unresolved, and what needs "
                    "validation next?"
                ),
            },
        ],
        "current_tumor_state": current_state.model_dump(mode="json"),
        "actionable_biology": actionable_biology.model_dump(mode="json"),
        "ranked_treatment_options": treatment_options.model_dump(mode="json"),
        "treatment_pressure_map": treatment_pressure.model_dump(mode="json"),
        "resistance_forecast": resistance_forecast.model_dump(mode="json"),
        "biomarker_watch_list": biomarker_watch.model_dump(mode="json"),
        "retesting_triggers": retesting_triggers.model_dump(mode="json"),
        "next_test_recommendations": next_tests.model_dump(mode="json"),
        "disease_and_specimen_context": compact["extraction"],
        "graph_evidence": compact["graph_evidence"],
        "tool_outputs": _tool_outputs_by_workflow(
            compact["tool_outputs"],
            {
                "target_context",
                "variant_context",
                "therapy_context",
                "guideline_context",
                "clinical_trial_context",
                "trial_context_review",
                "resistance_mechanism_context",
                "biomarker_retesting_context",
                "recent_therapy_agent_backfill_context",
            },
        ),
        "missing_evidence": compact["missing_evidence"],
        "conflicting_evidence": compact["conflicting_evidence"],
        "assessment_rules": [
            "Answer every question with status and evidence_strength.",
            "Use supported only when staged rows and evidence directly support it.",
            "Use weak_or_incomplete or unresolved when evidence is partial.",
            "Patient-population alignment must be unresolved unless disease, specimen, line/context, and treatment evidence alignment are present in supplied evidence.",
            "Do not answer dose, exposure, toxicity, or therapeutic window as resolved in this MVP; surface them under evidence_resolution when missing.",
        ],
    })


def build_decision_brief_synthesis_packet(
    *,
    current_state: CurrentTumorStateOutput,
    actionable_biology: ActionableBiologyOutput,
    treatment_options: RankedTreatmentOptionsOutput,
    treatment_pressure: TreatmentPressureMapOutput,
    resistance_forecast: ResistanceForecastOutput,
    biomarker_watch: BiomarkerWatchListOutput,
    retesting_triggers: RetestingTriggersOutput,
    next_tests: NextTestRecommendationsOutput,
    translational_assessment: TranslationalAssessmentOutput,
    source_chunk_ids: Sequence[str],
) -> dict[str, object]:
    """Return final synthesis payload containing only staged outputs."""
    return _with_prompt_budget("oncologist_decision_brief_synthesis", {
        "task": "oncologist_decision_brief_synthesis",
        "current_state_stage": current_state.model_dump(mode="json"),
        "actionable_biology_stage": actionable_biology.model_dump(mode="json"),
        "ranked_treatment_options_stage": treatment_options.model_dump(mode="json"),
        "treatment_pressure_stage": treatment_pressure.model_dump(mode="json"),
        "resistance_forecast_stage": resistance_forecast.model_dump(mode="json"),
        "biomarker_watch_stage": biomarker_watch.model_dump(mode="json"),
        "retesting_trigger_stage": retesting_triggers.model_dump(mode="json"),
        "next_test_stage": next_tests.model_dump(mode="json"),
        "translational_assessment_stage": translational_assessment.model_dump(mode="json"),
        "source_chunk_ids": list(source_chunk_ids),
        "required_translational_questions": [
            "Is the target actually relevant to this tumor's behavior?",
            "Does the biomarker evidence support action, or is it weak/incomplete?",
            "Are resistance mechanisms already present or likely to emerge?",
            "Is the patient population aligned with the evidence behind the treatment?",
            "What evidence is strong, what is unresolved, and what needs validation next?",
        ],
        "synthesis_rules": [
            "Do not introduce genes, drugs, biomarkers, or pathways absent from staged outputs.",
            "Deduplicate overlapping findings and surface conflicts as evidence_limitations.",
            "Rank by clinical_use, evidence_level, confidence, and relevance.",
            "Use risk/watch language for escape routes, not deterministic outcomes.",
            "Every decision row must carry source_artifact_ids or unresolved_evidence.",
            "Keep validation_status exactly needs_review.",
        ],
    })


def synthesize_oncologist_decision_brief_from_stage_outputs(
    *,
    planned_artifact_id: str,
    stage_outputs: DecisionBriefStageOutputs,
    source_artifact_ids: Sequence[str],
    source_chunk_ids: Sequence[str],
) -> OncologistDecisionBrief:
    """Build the final decision brief only from stage outputs.

    Acceptance criteria:
        1. Determinism: Same stages and IDs return the same final brief.
        2. No mutation: Stage outputs are read and copied into the brief.
        3. Grounding: No clinical rows are created outside stage outputs.
        4. Summary: The text summary is composed from staged row content only.
        5. Limitations: Unresolved stage evidence is surfaced explicitly.

    Args:
        planned_artifact_id: Deterministic artifact ID for the final brief.
        stage_outputs: Validated decision-brief prompt stage outputs.
        source_artifact_ids: Source artifacts for final provenance.
        source_chunk_ids: Source chunks for final provenance.

    Returns:
        Clinician-facing decision brief for review.
    """
    translational_assessment = (
        stage_outputs.translational_assessment
        or _fallback_translational_assessment_from_stage_outputs(stage_outputs)
    )
    limitations = _evidence_limitations_from_stage_outputs(stage_outputs)
    limitations = [
        *limitations,
        *_evidence_limitations_from_translational_assessment(
            translational_assessment
        ),
    ]
    return OncologistDecisionBrief(
        artifact_id=planned_artifact_id,
        clinical_decision_summary=_clinical_summary_from_stage_outputs(stage_outputs),
        current_tumor_state=stage_outputs.current_state.current_tumor_state,
        actionable_biology=stage_outputs.actionable_biology.actionable_biology,
        ranked_treatment_options=(
            stage_outputs.treatment_options.ranked_treatment_options
        ),
        treatment_pressure_map=stage_outputs.treatment_pressure.treatment_pressure_map,
        resistance_forecast=stage_outputs.resistance_forecast.resistance_forecast,
        biomarker_watch_list=stage_outputs.biomarker_watch.biomarker_watch_list,
        retesting_triggers=stage_outputs.retesting_triggers.retesting_triggers,
        next_test_recommendations=(
            stage_outputs.next_tests.next_test_recommendations
        ),
        translational_assessment=translational_assessment,
        therapy_escape_sankey_paths=build_therapy_escape_sankey_paths(
            stage_outputs,
            evidence_sentence_map=stage_outputs.evidence_sentence_map,
        ),
        evidence_sentence_map=list(stage_outputs.evidence_sentence_map),
        evidence_limitations=limitations,
        source_artifact_ids=list(source_artifact_ids),
        source_chunk_ids=list(source_chunk_ids),
        validation_status="needs_review",
    )







def build_evidence_sentence_map_from_context(
    context: EvidenceContextBundle,
) -> list[EvidenceSentence]:
    """Build human-readable evidence atoms from report and MIMS artifacts.

    Acceptance criteria:
        1. Uses only persisted source artifacts in the evidence context.
        2. Labels evidence for clinicians without exposing internal IDs.
        3. Preserves artifact/chunk/page provenance for backend audit.
        4. Includes report findings, negative/RNA findings, assay caveats,
           ToolUniverse evidence, graph context, and Medea hypotheses.
        5. Returns deterministic IDs and ordering.
    """
    sentences: list[EvidenceSentence] = []
    extraction = context.extraction
    for finding in extraction.molecular_findings:
        label = "RNA research-use-only signal" if finding.research_use_only else "Report finding"
        statement = _joined_or_fallback(
            [finding.gene or "", finding.alteration, finding.alteration_type],
            fallback=finding.alteration,
        )
        sentences.append(
            _evidence_sentence(
                evidence_label=label,
                statement=statement,
                source_type="research_use_only" if finding.research_use_only else "report",
                quote=finding.source_text or statement,
                source_artifact_ids=[extraction.artifact_id],
                source_chunk_ids=[finding.source_chunk_id] if finding.source_chunk_id else [],
                source_page=finding.source_page,
                relevance="Source molecular finding from uploaded report.",
            )
        )
    for value in extraction.negative_findings:
        label = _negative_evidence_label(value)
        sentences.append(
            _evidence_sentence(
                evidence_label=label,
                statement=value,
                source_type="report",
                quote=value,
                source_artifact_ids=[extraction.artifact_id],
                source_chunk_ids=[],
                source_page=None,
                relevance="Negative or absent report finding that constrains interpretation.",
            )
        )
    for value in extraction.assay_limitations:
        label = _assay_limit_label(value)
        sentences.append(
            _evidence_sentence(
                evidence_label=label,
                statement=value,
                source_type="research_use_only" if "research use" in value.casefold() else "assay_limitation",
                quote=value,
                source_artifact_ids=[extraction.artifact_id],
                source_chunk_ids=[],
                source_page=None,
                relevance="Assay limitation or caveat from the uploaded report.",
            )
        )
    for tool in context.tool_outputs:
        for item in tool.evidence_items:
            statement = _tool_evidence_statement(item)
            if not statement:
                continue
            sentences.append(
                _evidence_sentence(
                    evidence_label=_tool_evidence_label(tool.workflow, item),
                    statement=statement,
                    source_type="clinical_trial" if _is_trial_evidence(tool.workflow, item) else "tool",
                    quote=statement,
                    source_artifact_ids=[tool.artifact_id],
                    source_chunk_ids=[],
                    source_page=None,
                    relevance=f"ToolUniverse workflow: {tool.workflow}.",
                )
            )
    graph = context.graph_evidence
    for edge in graph.edges[:40]:
        source = _graph_node_label(graph, edge.source_node_id)
        target = _graph_node_label(graph, edge.target_node_id)
        statement = f"{source} — {edge.relation_type} — {target}"
        sentences.append(
            _evidence_sentence(
                evidence_label="Graph context",
                statement=statement,
                source_type="graph",
                quote=statement,
                source_artifact_ids=[graph.artifact_id],
                source_chunk_ids=[],
                source_page=None,
                relevance="OptimusKG relationship used as contextual evidence.",
            )
        )
    medea = context.medea_reasoning
    for hypothesis in [*medea.supported_hypotheses, *medea.weakened_hypotheses][:30]:
        sentences.append(
            _evidence_sentence(
                evidence_label="Hypothesis only",
                statement=hypothesis,
                source_type="medea_hypothesis",
                quote=hypothesis,
                source_artifact_ids=[medea.artifact_id],
                source_chunk_ids=[],
                source_page=None,
                relevance="Medea output is hypothesis support, not final clinical authority.",
            )
        )
    return _dedupe_evidence_sentences(sentences)


def enforce_patient_population_alignment_and_evidence_labels(
    assessment: TranslationalAssessmentOutput,
    *,
    context: EvidenceContextBundle,
    evidence_sentence_map: Sequence[EvidenceSentence],
) -> TranslationalAssessmentOutput:
    """Apply hard MVP gates to translational checks after model generation.

    Patient-population fit is intentionally conservative: it stays unresolved
    unless the uploaded/report/tool context contains tumor type match, disease
    setting, line of therapy, prior therapy, biomarker definition, assay context,
    and cohort/eligibility evidence.
    """
    questions = {
        "target_relevance": _with_question_evidence_labels(
            assessment.target_relevance,
            evidence_sentence_map,
        ),
        "biomarker_evidence": _with_question_evidence_labels(
            assessment.biomarker_evidence,
            evidence_sentence_map,
        ),
        "resistance_mechanisms": _with_question_evidence_labels(
            assessment.resistance_mechanisms,
            evidence_sentence_map,
        ),
        "patient_population_alignment": _with_question_evidence_labels(
            assessment.patient_population_alignment,
            evidence_sentence_map,
        ),
        "evidence_resolution": _with_question_evidence_labels(
            assessment.evidence_resolution,
            evidence_sentence_map,
        ),
    }
    missing_population = _missing_population_alignment_context(context)
    if missing_population:
        current = questions["patient_population_alignment"]
        unresolved = _unique_strings([*current.unresolved_evidence, *missing_population])
        validation_next = _unique_strings(
            [
                *current.validation_next,
                "Confirm disease setting/stage, line of therapy, prior therapies, biomarker definition, assay context, and evidence cohort eligibility before treating population fit as resolved.",
            ]
        )
        questions["patient_population_alignment"] = current.model_copy(
            update={
                "answer": (
                    "Population alignment remains unresolved. The supplied evidence "
                    "does not yet prove that the treatment evidence cohort matches "
                    "this patient's tumor type, disease setting, line of therapy, "
                    "prior therapy, biomarker definition, and assay context."
                ),
                "status": "unresolved",
                "evidence_strength": "unresolved",
                "supporting_evidence": [],
                "unresolved_evidence": unresolved,
                "validation_next": validation_next,
                "evidence_labels": _unique_strings(
                    [*current.evidence_labels, "Unresolved population fit"]
                ),
            }
        )
    unresolved = _unique_strings(
        [
            *assessment.unresolved_evidence,
            *questions["patient_population_alignment"].unresolved_evidence,
        ]
    )
    return assessment.model_copy(
        update={
            "target_relevance": questions["target_relevance"],
            "biomarker_evidence": questions["biomarker_evidence"],
            "resistance_mechanisms": questions["resistance_mechanisms"],
            "patient_population_alignment": questions["patient_population_alignment"],
            "evidence_resolution": questions["evidence_resolution"],
            "unresolved_evidence": unresolved,
        }
    )


def build_therapy_escape_sankey_paths(
    stage_outputs: DecisionBriefStageOutputs,
    *,
    evidence_sentence_map: Sequence[EvidenceSentence],
) -> list[TherapyEscapeSankeyPath]:
    """Build explicit therapy → target → behavior → escape paths."""
    disease_state = _joined_or_fallback(
        [
            *stage_outputs.current_state.current_tumor_state.dominant_drivers,
            *stage_outputs.current_state.current_tumor_state.active_pathways,
        ],
        fallback="Tumor behavior state requires review",
    )
    trigger_timing = _joined_or_fallback(
        [row.clinical_event for row in stage_outputs.retesting_triggers.retesting_triggers],
        fallback="Monitor at progression or before next treatment decision",
    )
    paths: list[TherapyEscapeSankeyPath] = []
    for pressure in stage_outputs.treatment_pressure.treatment_pressure_map:
        therapy_name, therapy_source, unresolved_agent = _resolve_actual_therapy_display(
            pressure.therapy_name_or_class,
            target_or_pathway=pressure.target_or_pathway,
            evidence_sentence_map=evidence_sentence_map,
        )
        evidence_ids = _evidence_ids_for_terms(
            evidence_sentence_map,
            [therapy_name, pressure.therapy_name_or_class, pressure.target_or_pathway],
        )
        source_ids = _unique_strings(pressure.source_artifact_ids)
        escape_routes = pressure.likely_escape_routes or [
            row.escape_route
            for row in stage_outputs.resistance_forecast.resistance_forecast
            if _shares_text(row.associated_treatment_pressure, pressure.therapy_name_or_class)
            or _shares_text(row.associated_treatment_pressure, pressure.target_or_pathway)
        ]
        if not escape_routes:
            escape_routes = ["escape pathway requires review"]
        for route in _unique_strings(escape_routes):
            unresolved = _unique_strings([*pressure.unresolved_evidence, *unresolved_agent])
            paths.append(
                TherapyEscapeSankeyPath(
                    therapy_display_name=therapy_name,
                    therapy_source=therapy_source,
                    molecular_target_or_pathway=pressure.target_or_pathway,
                    target_driver_status=_target_driver_status(
                        pressure.target_or_pathway,
                        stage_outputs.current_state.current_tumor_state,
                    ),
                    predicted_behavior_state=disease_state,
                    escape_pathway=route,
                    monitoring_timing=trigger_timing,
                    evidence_sentence_ids=evidence_ids,
                    source_artifact_ids=source_ids,
                    unresolved_evidence=unresolved,
                    confidence=pressure.confidence,
                )
            )
    return paths


def _evidence_sentence(
    *,
    evidence_label: str,
    statement: str,
    source_type: str,
    quote: str,
    source_artifact_ids: Sequence[str],
    source_chunk_ids: Sequence[str],
    source_page: int | None,
    relevance: str,
) -> EvidenceSentence:
    statement_clean = _brief_truncate(_normalize_spaces(statement), 600)
    quote_clean = _brief_truncate(_normalize_spaces(quote), 800)
    key = "|".join(
        [evidence_label, statement_clean, source_type, ",".join(source_artifact_ids)]
    )
    return EvidenceSentence(
        evidence_id=f"evidence_{_artifact_id(key, 'EvidenceSentence').split('_', 1)[1]}",
        evidence_label=evidence_label,
        statement=statement_clean,
        source_type=source_type,
        quote=quote_clean,
        source_artifact_ids=list(source_artifact_ids),
        source_chunk_ids=list(source_chunk_ids),
        source_page=source_page,
        relevance=relevance,
    )


def _negative_evidence_label(value: str) -> str:
    lowered = value.casefold()
    if "rearrangement" in lowered or "splicing" in lowered or "rna" in lowered:
        return "RNA/xR negative finding"
    if "microsatellite" in lowered or "tmb" in lowered:
        return "Immunotherapy marker"
    return "Report negative finding"


def _assay_limit_label(value: str) -> str:
    lowered = value.casefold()
    if "research use" in lowered:
        return "RNA research-use-only caveat"
    if "normal" in lowered and "unavailable" in lowered:
        return "Missing matched normal"
    if "line" in lowered or "previously prescribed" in lowered:
        return "Missing treatment history"
    return "Assay limitation"


def _tool_evidence_label(workflow: str, item: Mapping[str, str]) -> str:
    if _is_trial_evidence(workflow, item):
        return "Clinical trial criterion"
    if workflow == "recent_therapy_agent_backfill_context":
        return "Recent therapy-agent evidence"
    if "guideline" in workflow:
        return "Guideline/tool evidence"
    if "resistance" in workflow:
        return "Resistance mechanism evidence"
    return "Tool evidence"


def _is_trial_evidence(workflow: str, item: Mapping[str, str]) -> bool:
    text = " ".join(str(value) for value in item.values()).casefold()
    return "trial" in workflow or "nct" in text or "clinical trial" in text


def _tool_evidence_statement(item: Mapping[str, str]) -> str:
    preferred = [
        "title",
        "brief_title",
        "official_title",
        "summary",
        "finding",
        "relevance",
        "description",
        "value",
    ]
    parts = [str(item[key]).strip() for key in preferred if str(item.get(key, "")).strip()]
    if not parts:
        parts = [str(value).strip() for value in item.values() if str(value).strip()]
    return _brief_truncate(" | ".join(parts), 700)


def _graph_node_label(graph: Any, node_id: str) -> str:
    for node in graph.nodes:
        if node.node_id == node_id:
            return node.label
    return node_id


def _dedupe_evidence_sentences(
    values: Sequence[EvidenceSentence],
) -> list[EvidenceSentence]:
    result: list[EvidenceSentence] = []
    seen: set[str] = set()
    for value in values:
        key = value.evidence_id
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def _with_question_evidence_labels(
    question: TranslationalQuestionAssessment,
    evidence_sentence_map: Sequence[EvidenceSentence],
) -> TranslationalQuestionAssessment:
    evidence_ids = _evidence_ids_for_terms(
        evidence_sentence_map,
        [question.answer, *question.supporting_evidence, *question.validation_next],
    )
    labels = [
        item.evidence_label
        for item in evidence_sentence_map
        if item.evidence_id in evidence_ids
    ]
    if question.unresolved_evidence:
        labels.append("Unresolved evidence")
    return question.model_copy(
        update={
            "evidence_sentence_ids": _unique_strings(
                [*question.evidence_sentence_ids, *evidence_ids]
            ),
            "evidence_labels": _unique_strings([*question.evidence_labels, *labels]),
        }
    )


def _missing_population_alignment_context(context: EvidenceContextBundle) -> list[str]:
    text = _context_text_for_population_gate(context)
    missing: list[str] = []
    if not (context.extraction.disease or "tumor type" in text):
        missing.append("Missing tumor type match for the treatment evidence cohort.")
    if not any(term in text for term in ("stage", "metastatic", "advanced", "recurrent", "progression")):
        missing.append("Missing disease setting or extent of disease.")
    if not any(term in text for term in ("line of therapy", "first-line", "second-line", "third-line", "prior therapy")):
        missing.append("Missing line-of-therapy context.")
    if not any(term in text for term in ("previously prescribed", "prior treatment", "treatment history")):
        missing.append("Missing prior treatment history.")
    if not context.extraction.molecular_findings:
        missing.append("Missing biomarker definition from source report.")
    if not (context.extraction.specimen or context.extraction.tumor_percentage):
        missing.append("Missing assay/specimen context for applying evidence.")
    if not any(term in text for term in ("eligibility", "cohort", "inclusion", "exclusion", "nct", "trial")):
        missing.append("Missing evidence cohort or trial eligibility match.")
    return _unique_strings(missing)


def _context_text_for_population_gate(context: EvidenceContextBundle) -> str:
    values: list[str] = [
        context.extraction.disease or "",
        context.extraction.specimen or "",
        context.extraction.tumor_percentage or "",
        *context.extraction.negative_findings,
        *context.extraction.assay_limitations,
    ]
    values.extend(
        _tool_evidence_statement(item)
        for tool in context.tool_outputs
        for item in tool.evidence_items
    )
    return " ".join(values).casefold()


def _resolve_actual_therapy_display(
    therapy_name_or_class: str,
    *,
    target_or_pathway: str,
    evidence_sentence_map: Sequence[EvidenceSentence],
) -> tuple[str, str, list[str]]:
    candidates = _extract_actual_agents_from_text(therapy_name_or_class)
    if not candidates:
        candidates = _agents_from_evidence_map(
            evidence_sentence_map,
            [therapy_name_or_class, target_or_pathway],
        )
    if candidates:
        return "; ".join(candidates[:4]), "resolved_drug_or_trial_agent", []
    unresolved = (
        "Actual drug or trial agent was not resolved from report/tool evidence; "
        "recent therapy-agent backfill workflow should be reviewed."
    )
    return (
        f"Actual agent unresolved for {therapy_name_or_class}",
        "unresolved_after_backfill",
        [unresolved],
    )


def _extract_actual_agents_from_text(value: str) -> list[str]:
    candidates: list[str] = []
    patterns = [
        r"\b[A-Z]{2,6}\s?\d{2,5}\b",
        r"\b[A-Z][a-z]+(?:parib|ciclib|tinib|metinib|rafenib|taxel|mab)\b",
        r"\bOlaparib\b",
        r"\bDocetaxel\b",
        r"\bTNG908\b",
        r"\bAMG\s?193\b",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, value):
            candidate = " ".join(match.group(0).split())
            if _is_actual_agent_candidate(candidate) and candidate not in candidates:
                candidates.append(candidate)
    return candidates


def _agents_from_evidence_map(
    evidence_sentence_map: Sequence[EvidenceSentence],
    terms: Sequence[str],
) -> list[str]:
    agents: list[str] = []
    normalized_terms = [term.casefold() for term in terms if term.strip()]
    for evidence in evidence_sentence_map:
        haystack = f"{evidence.statement} {evidence.quote}".casefold()
        if normalized_terms and not any(term in haystack for term in normalized_terms):
            if evidence.source_type != "clinical_trial":
                continue
        for agent in _extract_actual_agents_from_text(f"{evidence.statement} {evidence.quote}"):
            if agent not in agents:
                agents.append(agent)
    return agents


def _is_actual_agent_candidate(value: str) -> bool:
    blocked = {
        "NCCN",
        "FDA",
        "PARP",
        "PRMT5",
        "CDK4",
        "CDK6",
        "DNA",
        "RNA",
        "MTAP",
        "CHEK2",
        "CDKN2A",
        "CDKN2B",
        "MSS",
        "TMB",
    }
    return value.upper().replace(" ", "") not in blocked and len(value) >= 4


def _target_driver_status(target: str, tumor_state: Any) -> str:
    evidence_text = " ".join(
        [
            *tumor_state.dominant_drivers,
            *tumor_state.active_pathways,
            *tumor_state.actionable_alterations,
            *tumor_state.co_drivers,
        ]
    ).casefold()
    target_terms = [term.casefold() for term in _target_terms(target)]
    if any(term in evidence_text for term in target_terms):
        return "report-supported tumor behavior driver or pathway"
    return "context-dependent target; driver status requires validation"


def _target_terms(value: str) -> list[str]:
    return [term for term in re.split(r"[^A-Za-z0-9]+", value) if len(term) >= 3]


def _evidence_ids_for_terms(
    evidence_sentence_map: Sequence[EvidenceSentence],
    terms: Sequence[str],
) -> list[str]:
    raw_terms: list[str] = []
    for value in terms:
        raw_terms.extend(_target_terms(str(value)))
    normalized_terms = [term.casefold() for term in raw_terms if len(term) >= 3]
    result: list[str] = []
    for evidence in evidence_sentence_map:
        haystack = f"{evidence.evidence_label} {evidence.statement} {evidence.quote}".casefold()
        if any(term in haystack for term in normalized_terms):
            result.append(evidence.evidence_id)
    return _unique_strings(result)[:12]


def _shares_text(left: str, right: str) -> bool:
    left_terms = {term.casefold() for term in _target_terms(left)}
    right_terms = {term.casefold() for term in _target_terms(right)}
    return bool(left_terms & right_terms)


def _unique_strings(values: Sequence[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


def _normalize_spaces(value: str) -> str:
    return " ".join(str(value).split())


def _brief_truncate(value: str, max_chars: int) -> str:
    clean = _normalize_spaces(value)
    if len(clean) <= max_chars:
        return clean
    return clean[: max_chars - 16].rstrip() + " … [truncated]"
def _fallback_translational_assessment_from_stage_outputs(
    stage_outputs: DecisionBriefStageOutputs,
) -> TranslationalAssessmentOutput:
    """Build conservative five-question checks when legacy tests omit the stage."""
    source_ids = stage_outputs.artifact_ids()
    drivers = _joined_or_fallback(
        stage_outputs.current_state.current_tumor_state.dominant_drivers,
        fallback="not resolved",
    )
    top_treatments = _joined_or_fallback(
        [
            row.therapy_name_or_class
            for row in stage_outputs.treatment_options.ranked_treatment_options
        ],
        fallback="not resolved",
    )
    escape_routes = _joined_or_fallback(
        [row.escape_route for row in stage_outputs.resistance_forecast.resistance_forecast],
        fallback="not resolved",
    )
    next_validation = _joined_or_fallback(
        [
            row.rationale
            for row in stage_outputs.next_tests.next_test_recommendations
        ],
        fallback="clinician review required",
    )
    unresolved_population = (
        "Patient-population alignment requires disease setting, line of therapy, "
        "prior treatment, assay context, and label/trial cohort match; keep "
        "unresolved unless those data are present."
    )

    def question(
        *,
        key: str,
        text: str,
        answer: str,
        status: str,
        strength: str,
        supporting: Sequence[str],
        unresolved: Sequence[str],
        validation: Sequence[str],
    ) -> TranslationalQuestionAssessment:
        return TranslationalQuestionAssessment(
            question_key=key,
            question=text,
            answer=answer,
            status=status,
            evidence_strength=strength,
            supporting_evidence=list(supporting),
            unresolved_evidence=list(unresolved),
            validation_next=list(validation),
            source_artifact_ids=list(source_ids),
            confidence="needs_review",
        )

    return TranslationalAssessmentOutput(
        artifact_id=_artifact_id(
            stage_outputs.current_state.artifact_id,
            "TranslationalAssessmentOutput",
        ),
        target_relevance=question(
            key="target_relevance",
            text="Is the target actually relevant to this tumor's behavior?",
            answer=(
                f"Current staged drivers/pathways center on {drivers}. Therapy/target "
                f"relevance should be interpreted through the treatment-pressure rows, not mutation detection alone."
            ),
            status="partially_supported" if drivers != "not resolved" else "unresolved",
            strength="moderate" if drivers != "not resolved" else "unresolved",
            supporting=[f"Resolved staged drivers/pathways: {drivers}"],
            unresolved=[],
            validation=["Confirm the target is behavior-driving rather than only detected."],
        ),
        biomarker_evidence=question(
            key="biomarker_evidence",
            text="Does the biomarker evidence support action, or is it weak/incomplete?",
            answer=(
                f"Staged treatment options include {top_treatments}. Biomarker actionability should follow clinical_use and evidence_level labels in those rows."
            ),
            status="partially_supported" if top_treatments != "not resolved" else "unresolved",
            strength="moderate" if top_treatments != "not resolved" else "unresolved",
            supporting=[f"Resolved staged treatment options: {top_treatments}"],
            unresolved=[],
            validation=["Review evidence_level, clinical_use, and required_before_use_tests."],
        ),
        resistance_mechanisms=question(
            key="resistance_mechanisms",
            text="Are resistance mechanisms already present or likely to emerge?",
            answer=(
                f"Resistance is represented as risk/watch logic. Resolved escape routes: {escape_routes}."
            ),
            status="partially_supported" if escape_routes != "not resolved" else "unresolved",
            strength="moderate" if escape_routes != "not resolved" else "unresolved",
            supporting=[f"Resolved escape routes: {escape_routes}"],
            unresolved=[],
            validation=["Monitor listed biomarkers at event-based re-testing triggers."],
        ),
        patient_population_alignment=question(
            key="patient_population_alignment",
            text="Is the patient population aligned with the evidence behind the treatment?",
            answer=(
                "Population alignment is unresolved unless the supplied evidence explicitly matches tumor type, disease setting, line of therapy, prior therapy, and biomarker context."
            ),
            status="unresolved",
            strength="unresolved",
            supporting=[],
            unresolved=[unresolved_population],
            validation=["Add or verify patient clinical context and evidence cohort fit."],
        ),
        evidence_resolution=question(
            key="evidence_resolution",
            text="What evidence is strong, what is unresolved, and what needs validation next?",
            answer=f"Next validation should focus on: {next_validation}.",
            status="partially_supported",
            strength="moderate",
            supporting=[f"Next-test rationale: {next_validation}"],
            unresolved=[
                value
                for _stage_name, _artifact_id, values in _stage_unresolved_evidence(stage_outputs)
                for value in values
                if value.strip()
            ],
            validation=[next_validation],
        ),
        unresolved_evidence=[unresolved_population],
    )

def _evidence_limitations_from_translational_assessment(
    assessment: TranslationalAssessmentOutput | None,
) -> list[EvidenceLimitation]:
    """Return limitation rows from unresolved translational checks."""
    if assessment is None:
        return []
    return [
        EvidenceLimitation(
            limitation=value,
            impact=(
                f"The translational check '{question.question}' remains "
                "incomplete or requires source validation."
            ),
            needed_resolution="; ".join(question.validation_next),
            source_artifact_ids=question.source_artifact_ids,
        )
        for question in _translational_questions(assessment)
        for value in question.unresolved_evidence
        if value.strip()
    ]


def _clinical_summary_from_stage_outputs(
    stage_outputs: DecisionBriefStageOutputs,
) -> str:
    tumor_state = stage_outputs.current_state.current_tumor_state
    treatment = _first_text(
        [
            item.therapy_name_or_class
            for item in stage_outputs.treatment_options.ranked_treatment_options
        ],
        fallback="no evidence-supported treatment option resolved",
    )
    treatment_rationale = _first_text(
        [item.why_it_fits for item in stage_outputs.treatment_options.ranked_treatment_options],
        fallback="current evidence requires clinician review before treatment logic is resolved",
    )
    escape = _first_text(
        [item.description for item in stage_outputs.resistance_forecast.resistance_forecast],
        fallback="no resistance route resolved beyond unresolved evidence",
    )
    biomarker = _first_text(
        [item.biomarker for item in stage_outputs.biomarker_watch.biomarker_watch_list],
        fallback="no specific biomarker watch item resolved",
    )
    trigger = _first_text(
        [item.clinical_event for item in stage_outputs.retesting_triggers.retesting_triggers],
        fallback="no specific re-testing trigger resolved",
    )
    next_test = _first_text(
        [item.test_type for item in stage_outputs.next_tests.next_test_recommendations],
        fallback="no next test resolved",
    )
    translational_assessment = (
        stage_outputs.translational_assessment
        or _fallback_translational_assessment_from_stage_outputs(stage_outputs)
    )
    target_answer = translational_assessment.target_relevance.answer
    evidence_answer = translational_assessment.evidence_resolution.answer
    drivers = _joined_or_fallback(
        tumor_state.dominant_drivers,
        fallback="source-backed tumor drivers requiring review",
    )
    return (
        f"Current tumor state centers on {drivers}. "
        f"The top staged treatment logic is {treatment}: {treatment_rationale}. "
        f"Monitor escape risk as {escape}. "
        f"Priority monitoring includes {biomarker}. "
        f"Re-test trigger: {trigger}. "
        f"Next test to consider for clinician review: {next_test}. "
        f"Target relevance check: {target_answer}. "
        f"Evidence resolution check: {evidence_answer}."
    )


def _evidence_limitations_from_stage_outputs(
    stage_outputs: DecisionBriefStageOutputs,
) -> list[EvidenceLimitation]:
    limitations = [
        EvidenceLimitation(
            limitation=value,
            impact=f"Unresolved evidence in {stage_name} limits final confidence.",
            needed_resolution="Clinician review or additional source evidence is required.",
            source_artifact_ids=[artifact_id],
        )
        for stage_name, artifact_id, unresolved in _stage_unresolved_evidence(
            stage_outputs
        )
        for value in unresolved
        if value.strip()
    ]
    limitations.extend(
        EvidenceLimitation(
            limitation=value,
            impact=f"Unresolved row evidence in {row_group} limits final confidence.",
            needed_resolution=(
                "Add source evidence for this row or keep it marked "
                "as unresolved for clinician review."
            ),
            source_artifact_ids=list(source_ids),
        )
        for row_group, source_ids, unresolved in _row_unresolved_evidence(
            stage_outputs
        )
        for value in unresolved
        if value.strip()
    )
    if limitations:
        return limitations
    return [
        EvidenceLimitation(
            limitation="Clinician review is required before clinical use.",
            impact="The brief is decision support and not an autonomous medical decision.",
            needed_resolution=(
                "Review source-backed treatment logic, resistance risks, "
                "biomarker watch items, and re-testing triggers."
            ),
            source_artifact_ids=stage_outputs.artifact_ids(),
        )
    ]


def _row_unresolved_evidence(
    stage_outputs: DecisionBriefStageOutputs,
) -> list[tuple[str, Sequence[str], Sequence[str]]]:
    return [
        (
            "ranked_treatment_options",
            item.source_artifact_ids,
            item.unresolved_evidence,
        )
        for item in stage_outputs.treatment_options.ranked_treatment_options
    ] + [
        (
            "treatment_pressure",
            item.source_artifact_ids,
            item.unresolved_evidence,
        )
        for item in stage_outputs.treatment_pressure.treatment_pressure_map
    ] + [
        (
            "resistance_forecast",
            item.source_artifact_ids,
            item.unresolved_evidence,
        )
        for item in stage_outputs.resistance_forecast.resistance_forecast
    ] + [
        (
            "biomarker_watch_list",
            item.source_artifact_ids,
            item.unresolved_evidence,
        )
        for item in stage_outputs.biomarker_watch.biomarker_watch_list
    ] + [
        (
            "retesting_triggers",
            item.source_artifact_ids,
            item.unresolved_evidence,
        )
        for item in stage_outputs.retesting_triggers.retesting_triggers
    ] + [
        (
            "next_test_recommendations",
            item.source_artifact_ids,
            item.unresolved_evidence,
        )
        for item in stage_outputs.next_tests.next_test_recommendations
    ] + (
        [
            (
                "translational_assessment",
                item.source_artifact_ids,
                item.unresolved_evidence,
            )
            for item in _translational_questions(stage_outputs.translational_assessment)
        ]
        if stage_outputs.translational_assessment is not None
        else []
    )


def _stage_unresolved_evidence(
    stage_outputs: DecisionBriefStageOutputs,
) -> list[tuple[str, str, Sequence[str]]]:
    return [
        (
            "current_tumor_state",
            stage_outputs.current_state.artifact_id,
            stage_outputs.current_state.unresolved_evidence,
        ),
        (
            "actionable_biology",
            stage_outputs.actionable_biology.artifact_id,
            stage_outputs.actionable_biology.unresolved_evidence,
        ),
        (
            "ranked_treatment_options",
            stage_outputs.treatment_options.artifact_id,
            stage_outputs.treatment_options.unresolved_evidence,
        ),
        (
            "treatment_pressure",
            stage_outputs.treatment_pressure.artifact_id,
            stage_outputs.treatment_pressure.unresolved_evidence,
        ),
        (
            "resistance_forecast",
            stage_outputs.resistance_forecast.artifact_id,
            stage_outputs.resistance_forecast.unresolved_evidence,
        ),
        (
            "biomarker_watch_list",
            stage_outputs.biomarker_watch.artifact_id,
            stage_outputs.biomarker_watch.unresolved_evidence,
        ),
        (
            "retesting_triggers",
            stage_outputs.retesting_triggers.artifact_id,
            stage_outputs.retesting_triggers.unresolved_evidence,
        ),
        (
            "next_test_recommendations",
            stage_outputs.next_tests.artifact_id,
            stage_outputs.next_tests.unresolved_evidence,
        ),
        *(
            [
                (
                    "translational_assessment",
                    stage_outputs.translational_assessment.artifact_id,
                    stage_outputs.translational_assessment.unresolved_evidence,
                )
            ]
            if stage_outputs.translational_assessment is not None
            else []
        ),
    ]


def _translational_questions(
    assessment: TranslationalAssessmentOutput | None,
) -> list[object]:
    """Return five translational question assessments in UI/report order."""
    if assessment is None:
        return []
    return [
        assessment.target_relevance,
        assessment.biomarker_evidence,
        assessment.resistance_mechanisms,
        assessment.patient_population_alignment,
        assessment.evidence_resolution,
    ]


def _first_text(values: Sequence[str], *, fallback: str) -> str:
    for value in values:
        if value.strip():
            return value.strip()
    return fallback


def _joined_or_fallback(values: Sequence[str], *, fallback: str) -> str:
    stripped = [value.strip() for value in values if value.strip()]
    if not stripped:
        return fallback
    return ", ".join(stripped)


def decision_stage_source_ids(
    *,
    context: EvidenceContextBundle,
    phenotype: MolecularPhenotypeOutput,
    matrix: TherapyEvidenceMatrixOutput,
    sankey: MechanismSankeyOutput,
    confirmatory: ConfirmatoryTestingOutput,
    tumor_behavior: TumorBehaviorModelOutput,
    stage_artifact_ids: Sequence[str],
) -> list[str]:
    """Return ordered source IDs for decision-brief provenance."""
    values = [
        *_context_source_ids(context),
        phenotype.artifact_id,
        matrix.artifact_id,
        sankey.artifact_id,
        confirmatory.artifact_id,
        tumor_behavior.artifact_id,
        *stage_artifact_ids,
    ]
    return list(dict.fromkeys(value for value in values if value.strip()))



def require_decision_stage_outputs_evidence_grounded(
    *,
    current_state: CurrentTumorStateOutput,
    actionable_biology: ActionableBiologyOutput,
    treatment_options: RankedTreatmentOptionsOutput,
    treatment_pressure: TreatmentPressureMapOutput,
    resistance_forecast: ResistanceForecastOutput,
    biomarker_watch: BiomarkerWatchListOutput,
    retesting_triggers: RetestingTriggersOutput,
    next_tests: NextTestRecommendationsOutput,
    translational_assessment: TranslationalAssessmentOutput,
) -> None:
    """Fail unless all decision-brief stages carry usable evidence.

    Acceptance criteria:
        1. Determinism: Same stage outputs either pass or raise the same error.
        2. No mutation: Stage outputs are never modified.
        3. Evidence: Every clinical row carries sources or unresolved_evidence.
        4. Utility: Empty row groups must be explained by unresolved evidence.
        5. Safety: Unsupported certainty language is rejected before synthesis.

    Args:
        current_state: Current tumor state stage output.
        actionable_biology: Actionable biology stage output.
        treatment_options: Ranked treatment option stage output.
        treatment_pressure: Treatment pressure stage output.
        resistance_forecast: Resistance forecast stage output.
        biomarker_watch: Biomarker watch-list stage output.
        retesting_triggers: Re-testing trigger stage output.
        next_tests: Next-test recommendation stage output.

    Raises:
        StructuredArtifactGenerationError: If evidence, utility, or safety
            requirements are not met.
    """
    stages = [
        current_state,
        actionable_biology,
        treatment_options,
        treatment_pressure,
        resistance_forecast,
        biomarker_watch,
        retesting_triggers,
        next_tests,
        translational_assessment,
    ]
    for stage in stages:
        if stage is None:
            continue
        _require_stage_artifact_id(stage.artifact_id, type(stage).__name__)
        _require_safe_output(stage.model_dump_json(), type(stage).__name__)

    _require_sources(
        current_state.current_tumor_state.source_artifact_ids,
        "current_tumor_state.source_artifact_ids",
    )
    _require_any_text(
        [
            *current_state.current_tumor_state.dominant_drivers,
            *current_state.current_tumor_state.active_pathways,
            *current_state.current_tumor_state.actionable_alterations,
            *current_state.current_tumor_state.resistance_or_uncertain_alterations,
            *current_state.current_tumor_state.missing_data,
            *current_state.unresolved_evidence,
        ],
        "CurrentTumorStateOutput",
    )
    _require_row_group_or_unresolved(
        actionable_biology.actionable_biology,
        actionable_biology.unresolved_evidence,
        "ActionableBiologyOutput.actionable_biology",
    )
    for index, item in enumerate(actionable_biology.actionable_biology):
        prefix = f"ActionableBiologyOutput.actionable_biology[{index}]"
        _require_sources(item.source_artifact_ids, f"{prefix}.source_artifact_ids")
        _require_text(item.biology, f"{prefix}.biology")
        _require_text(item.alteration_or_marker, f"{prefix}.alteration_or_marker")
        _require_text(item.rationale, f"{prefix}.rationale")
        _require_text(item.evidence_level, f"{prefix}.evidence_level")

    _require_row_group_or_unresolved(
        treatment_options.ranked_treatment_options,
        treatment_options.unresolved_evidence,
        "RankedTreatmentOptionsOutput.ranked_treatment_options",
    )
    for index, item in enumerate(treatment_options.ranked_treatment_options):
        prefix = f"RankedTreatmentOptionsOutput.ranked_treatment_options[{index}]"
        _require_evidence_or_unresolved(
            item.source_artifact_ids,
            item.unresolved_evidence,
            f"{prefix}.source_artifact_ids",
        )
        _require_text(item.therapy_name_or_class, f"{prefix}.therapy_name_or_class")
        _require_text(item.therapy_class, f"{prefix}.therapy_class")
        _require_text(item.why_it_fits, f"{prefix}.why_it_fits")
        _require_text(item.evidence_level, f"{prefix}.evidence_level")
        _require_text_list(item.required_before_use_tests, f"{prefix}.required_before_use_tests")
        _require_text_list(item.limitations, f"{prefix}.limitations")

    _require_row_group_or_unresolved(
        treatment_pressure.treatment_pressure_map,
        treatment_pressure.unresolved_evidence,
        "TreatmentPressureMapOutput.treatment_pressure_map",
    )
    for index, item in enumerate(treatment_pressure.treatment_pressure_map):
        prefix = f"TreatmentPressureMapOutput.treatment_pressure_map[{index}]"
        _require_evidence_or_unresolved(
            item.source_artifact_ids,
            item.unresolved_evidence,
            f"{prefix}.source_artifact_ids",
        )
        _require_text(item.therapy_name_or_class, f"{prefix}.therapy_name_or_class")
        _require_text(item.target_or_pathway, f"{prefix}.target_or_pathway")
        _require_text(item.selective_pressure, f"{prefix}.selective_pressure")
        _require_text_list(item.likely_escape_routes, f"{prefix}.likely_escape_routes")
        _require_text_list(item.biomarkers_to_watch, f"{prefix}.biomarkers_to_watch")
        _require_text_list_or_unresolved(
            item.evidence_basis,
            item.unresolved_evidence,
            f"{prefix}.evidence_basis",
        )

    _require_row_group_or_unresolved(
        resistance_forecast.resistance_forecast,
        resistance_forecast.unresolved_evidence,
        "ResistanceForecastOutput.resistance_forecast",
    )
    for index, item in enumerate(resistance_forecast.resistance_forecast):
        prefix = f"ResistanceForecastOutput.resistance_forecast[{index}]"
        _require_evidence_or_unresolved(
            item.source_artifact_ids,
            item.unresolved_evidence,
            f"{prefix}.source_artifact_ids",
        )
        _require_text(item.description, f"{prefix}.description")
        _require_text(
            item.associated_treatment_pressure,
            f"{prefix}.associated_treatment_pressure",
        )
        _require_text_list_or_unresolved(
            item.supporting_evidence,
            item.unresolved_evidence,
            f"{prefix}.supporting_evidence",
        )
        _require_text_list(item.biomarkers_to_monitor, f"{prefix}.biomarkers_to_monitor")

    _require_row_group_or_unresolved(
        biomarker_watch.biomarker_watch_list,
        biomarker_watch.unresolved_evidence,
        "BiomarkerWatchListOutput.biomarker_watch_list",
    )
    for index, item in enumerate(biomarker_watch.biomarker_watch_list):
        prefix = f"BiomarkerWatchListOutput.biomarker_watch_list[{index}]"
        _require_evidence_or_unresolved(
            item.source_artifact_ids,
            item.unresolved_evidence,
            f"{prefix}.source_artifact_ids",
        )
        _require_text(item.biomarker, f"{prefix}.biomarker")
        _require_text(item.alteration_type, f"{prefix}.alteration_type")
        _require_text(item.why_watch, f"{prefix}.why_watch")
        _require_text(item.trigger, f"{prefix}.trigger")

    _require_row_group_or_unresolved(
        retesting_triggers.retesting_triggers,
        retesting_triggers.unresolved_evidence,
        "RetestingTriggersOutput.retesting_triggers",
    )
    for index, item in enumerate(retesting_triggers.retesting_triggers):
        prefix = f"RetestingTriggersOutput.retesting_triggers[{index}]"
        _require_evidence_or_unresolved(
            item.source_artifact_ids,
            item.unresolved_evidence,
            f"{prefix}.source_artifact_ids",
        )
        _require_text(item.clinical_event, f"{prefix}.clinical_event")
        _require_text(item.rationale, f"{prefix}.rationale")
        _require_text(item.what_result_changes, f"{prefix}.what_result_changes")

    _require_row_group_or_unresolved(
        next_tests.next_test_recommendations,
        next_tests.unresolved_evidence,
        "NextTestRecommendationsOutput.next_test_recommendations",
    )
    for index, item in enumerate(next_tests.next_test_recommendations):
        prefix = f"NextTestRecommendationsOutput.next_test_recommendations[{index}]"
        _require_evidence_or_unresolved(
            item.source_artifact_ids,
            item.unresolved_evidence,
            f"{prefix}.source_artifact_ids",
        )
        _require_text(item.timing, f"{prefix}.timing")
        _require_text(item.rationale, f"{prefix}.rationale")
        _require_text(
            item.result_that_would_change_management,
            f"{prefix}.result_that_would_change_management",
        )
        _require_text_list(
            item.biomarkers_or_questions,
            f"{prefix}.biomarkers_or_questions",
        )
        _require_text_list(item.limitations, f"{prefix}.limitations")

    if translational_assessment is not None:
        for item in _translational_questions(translational_assessment):
            prefix = f"TranslationalAssessmentOutput.{item.question_key}"
            _require_evidence_or_unresolved(
                item.source_artifact_ids,
                item.unresolved_evidence,
                f"{prefix}.source_artifact_ids",
            )
            _require_text(item.question, f"{prefix}.question")
            _require_text(item.answer, f"{prefix}.answer")
            _require_text_list_or_unresolved(
                item.supporting_evidence,
                item.unresolved_evidence,
                f"{prefix}.supporting_evidence",
            )
            _require_text_list(item.validation_next, f"{prefix}.validation_next")



def require_decision_brief_matches_stage_outputs(
    *,
    brief: OncologistDecisionBrief,
    current_state: CurrentTumorStateOutput,
    actionable_biology: ActionableBiologyOutput,
    treatment_options: RankedTreatmentOptionsOutput,
    treatment_pressure: TreatmentPressureMapOutput,
    resistance_forecast: ResistanceForecastOutput,
    biomarker_watch: BiomarkerWatchListOutput,
    retesting_triggers: RetestingTriggersOutput,
    next_tests: NextTestRecommendationsOutput,
    translational_assessment: TranslationalAssessmentOutput,
) -> None:
    """Fail if final synthesis changes staged clinical rows.

    Acceptance criteria:
        1. Determinism: Same brief and stages produce the same outcome.
        2. No mutation: Inputs are only read.
        3. Grounding: Final row groups must exactly match staged outputs.
        4. Lineage: Final source IDs must include every stage artifact ID.
        5. Safety: Unsupported certainty language is rejected.

    Args:
        brief: Final oncologist decision brief.
        current_state: Current tumor state stage output.
        actionable_biology: Actionable biology stage output.
        treatment_options: Ranked treatment option stage output.
        treatment_pressure: Treatment pressure stage output.
        resistance_forecast: Resistance forecast stage output.
        biomarker_watch: Biomarker watch-list stage output.
        retesting_triggers: Re-testing trigger stage output.
        next_tests: Next-test recommendation stage output.

    Raises:
        StructuredArtifactGenerationError: If final rows introduce, drop, or
            alter clinical facts from staged outputs.
    """
    _require_safe_output(brief.model_dump_json(), "OncologistDecisionBrief")
    _require_equal_payload(
        brief.current_tumor_state.model_dump(mode="json"),
        current_state.current_tumor_state.model_dump(mode="json"),
        "brief.current_tumor_state",
    )
    _require_equal_payload(
        [item.model_dump(mode="json") for item in brief.actionable_biology],
        [item.model_dump(mode="json") for item in actionable_biology.actionable_biology],
        "brief.actionable_biology",
    )
    _require_equal_payload(
        [item.model_dump(mode="json") for item in brief.ranked_treatment_options],
        [item.model_dump(mode="json") for item in treatment_options.ranked_treatment_options],
        "brief.ranked_treatment_options",
    )
    _require_equal_payload(
        [item.model_dump(mode="json") for item in brief.treatment_pressure_map],
        [item.model_dump(mode="json") for item in treatment_pressure.treatment_pressure_map],
        "brief.treatment_pressure_map",
    )
    _require_equal_payload(
        [item.model_dump(mode="json") for item in brief.resistance_forecast],
        [item.model_dump(mode="json") for item in resistance_forecast.resistance_forecast],
        "brief.resistance_forecast",
    )
    _require_equal_payload(
        [item.model_dump(mode="json") for item in brief.biomarker_watch_list],
        [item.model_dump(mode="json") for item in biomarker_watch.biomarker_watch_list],
        "brief.biomarker_watch_list",
    )
    _require_equal_payload(
        [item.model_dump(mode="json") for item in brief.retesting_triggers],
        [item.model_dump(mode="json") for item in retesting_triggers.retesting_triggers],
        "brief.retesting_triggers",
    )
    _require_equal_payload(
        [item.model_dump(mode="json") for item in brief.next_test_recommendations],
        [item.model_dump(mode="json") for item in next_tests.next_test_recommendations],
        "brief.next_test_recommendations",
    )
    if translational_assessment is not None:
        _require_equal_payload(
            brief.translational_assessment.model_dump(mode="json"),
            translational_assessment.model_dump(mode="json"),
            "brief.translational_assessment",
        )
    stage_ids = [
        current_state.artifact_id,
        actionable_biology.artifact_id,
        treatment_options.artifact_id,
        treatment_pressure.artifact_id,
        resistance_forecast.artifact_id,
        biomarker_watch.artifact_id,
        retesting_triggers.artifact_id,
        next_tests.artifact_id,
        *(
            [translational_assessment.artifact_id]
            if translational_assessment is not None
            else []
        ),
    ]
    missing_ids = [item for item in stage_ids if item not in brief.source_artifact_ids]
    if missing_ids:
        raise StructuredArtifactGenerationError(
            "OncologistDecisionBrief is missing stage source_artifact_ids: "
            + ", ".join(missing_ids)
        )


def require_decision_brief_rows_carry_evidence_or_unresolved(
    brief: OncologistDecisionBrief,
) -> None:
    """Fail unless every decision row has evidence or unresolved evidence.

    Acceptance criteria:
        1. Determinism: Same brief returns the same pass/fail outcome.
        2. No mutation: The brief is only inspected.
        3. Provenance: Each clinician-facing row has source IDs when sourced.
        4. Reviewability: Unsourced rows must carry row-level unresolved_evidence.
        5. Safety: Unsupported certainty language is rejected.

    Args:
        brief: Final oncologist decision brief.

    Raises:
        StructuredArtifactGenerationError: If a row lacks both evidence and an
            unresolved-evidence explanation.
    """
    _require_safe_output(brief.model_dump_json(), "OncologistDecisionBrief")
    for index, item in enumerate(brief.ranked_treatment_options):
        _require_evidence_or_unresolved(
            item.source_artifact_ids,
            item.unresolved_evidence,
            f"brief.ranked_treatment_options[{index}].source_artifact_ids",
        )
    for index, item in enumerate(brief.treatment_pressure_map):
        _require_evidence_or_unresolved(
            item.source_artifact_ids,
            item.unresolved_evidence,
            f"brief.treatment_pressure_map[{index}].source_artifact_ids",
        )
        _require_text_list_or_unresolved(
            item.evidence_basis,
            item.unresolved_evidence,
            f"brief.treatment_pressure_map[{index}].evidence_basis",
        )
    for index, item in enumerate(brief.resistance_forecast):
        _require_evidence_or_unresolved(
            item.source_artifact_ids,
            item.unresolved_evidence,
            f"brief.resistance_forecast[{index}].source_artifact_ids",
        )
        _require_text_list_or_unresolved(
            item.supporting_evidence,
            item.unresolved_evidence,
            f"brief.resistance_forecast[{index}].supporting_evidence",
        )
    for index, item in enumerate(brief.biomarker_watch_list):
        _require_evidence_or_unresolved(
            item.source_artifact_ids,
            item.unresolved_evidence,
            f"brief.biomarker_watch_list[{index}].source_artifact_ids",
        )
    for index, item in enumerate(brief.retesting_triggers):
        _require_evidence_or_unresolved(
            item.source_artifact_ids,
            item.unresolved_evidence,
            f"brief.retesting_triggers[{index}].source_artifact_ids",
        )
    for index, item in enumerate(brief.next_test_recommendations):
        _require_evidence_or_unresolved(
            item.source_artifact_ids,
            item.unresolved_evidence,
            f"brief.next_test_recommendations[{index}].source_artifact_ids",
        )
    if brief.translational_assessment is not None:
        for item in _translational_questions(brief.translational_assessment):
            _require_evidence_or_unresolved(
                item.source_artifact_ids,
                item.unresolved_evidence,
                f"brief.translational_assessment.{item.question_key}.source_artifact_ids",
            )
            _require_text(item.answer, f"brief.translational_assessment.{item.question_key}.answer")
            _require_text_list(item.validation_next, f"brief.translational_assessment.{item.question_key}.validation_next")


def _require_safe_output(serialized_output: str, artifact_name: str) -> None:
    try:
        _validate_safety(serialized_output)
    except SafetyLanguageError as error:
        raise StructuredArtifactGenerationError(
            f"{artifact_name} contains unsupported certainty language: {error}"
        ) from error


def _validate_ranked_treatment_options_output(
    treatment_options: RankedTreatmentOptionsOutput,
) -> None:
    """Validate ranked treatment options before dependent stages run.

    Acceptance criteria:
        1. Determinism: Same treatment-options artifact always validates or
           raises the same error.
        2. No mutation: The artifact and nested rows are not mutated.
        3. Safety: Every populated treatment row must include evidence or
           unresolved evidence, required text fields, before-use tests, and
           limitations.
        4. Scope: This mirrors the ranked-treatment subsection of staged
           decision-brief validation without validating unrelated stages.

    Args:
        treatment_options: Ranked treatment options stage output.

    Raises:
        StructuredArtifactGenerationError: If the stage output is incomplete or
            contains unsupported certainty language.
    """
    _require_stage_artifact_id(
        treatment_options.artifact_id,
        "RankedTreatmentOptionsOutput",
    )
    _require_safe_output(
        treatment_options.model_dump_json(),
        "RankedTreatmentOptionsOutput",
    )
    _require_row_group_or_unresolved(
        treatment_options.ranked_treatment_options,
        treatment_options.unresolved_evidence,
        "RankedTreatmentOptionsOutput.ranked_treatment_options",
    )
    for index, item in enumerate(treatment_options.ranked_treatment_options):
        prefix = f"RankedTreatmentOptionsOutput.ranked_treatment_options[{index}]"
        _require_evidence_or_unresolved(
            item.source_artifact_ids,
            item.unresolved_evidence,
            f"{prefix}.source_artifact_ids",
        )
        _require_text(item.therapy_name_or_class, f"{prefix}.therapy_name_or_class")
        _require_text(item.therapy_class, f"{prefix}.therapy_class")
        _require_text(item.why_it_fits, f"{prefix}.why_it_fits")
        _require_text(item.evidence_level, f"{prefix}.evidence_level")
        _require_text_list(
            item.required_before_use_tests,
            f"{prefix}.required_before_use_tests",
        )
        _require_text_list(item.limitations, f"{prefix}.limitations")


def _normalize_ranked_treatment_required_lists(
    treatment_options: RankedTreatmentOptionsOutput,
    *,
    matrix: TherapyEvidenceMatrixOutput,
    actionable_biology: ActionableBiologyOutput,
) -> RankedTreatmentOptionsOutput:
    """Return treatment options with required tests and limitations populated.

    Acceptance criteria:
        1. Determinism: Same treatment options, matrix, and actionable biology
           return equivalent normalized output.
        2. No mutation: The stage artifact and source artifacts are not mutated.
        3. Scope: Only empty `required_before_use_tests` and `limitations`
           lists are populated.
        4. Safety: Candidates come from source-derived validation, uncertainty,
           or limitation text before conservative clinician-review fallbacks.

    Args:
        treatment_options: Model-generated ranked treatment options.
        matrix: Molecular-fit matrix with validation requirements.
        actionable_biology: Actionable biology stage with uncertainty text.

    Returns:
        A copied ranked-treatment artifact with required lists populated.
    """
    fallback_tests = _ranked_treatment_before_use_candidates(
        matrix=matrix,
        actionable_biology=actionable_biology,
    )
    fallback_limitations = _ranked_treatment_limitation_candidates(
        matrix=matrix,
        actionable_biology=actionable_biology,
    )
    rows = []
    for item in treatment_options.ranked_treatment_options:
        updates: dict[str, list[str]] = {}
        if not any(value.strip() for value in item.required_before_use_tests):
            updates["required_before_use_tests"] = fallback_tests
        if not any(value.strip() for value in item.limitations):
            row_limitations = _dedupe_nonempty_texts(
                [*item.unresolved_evidence, *fallback_limitations],
                max_items=12,
                max_chars=220,
            )
            updates["limitations"] = row_limitations
        rows.append(item.model_copy(update=updates) if updates else item)
    return treatment_options.model_copy(update={"ranked_treatment_options": rows})


def _is_empty_required_before_use_tests_error(
    error: BaseException,
) -> bool:
    """Return whether a treatment-option validation error is repairable.

    Acceptance criteria:
        1. Determinism: Same exception message returns the same boolean.
        2. Scope: Match only empty `required_before_use_tests` failures for
           ranked treatment options.
        3. No mutation: Does not mutate exception state.
    """
    return (
        "RankedTreatmentOptionsOutput.ranked_treatment_options["
        in str(error)
        and ".required_before_use_tests must not be empty" in str(error)
    )


def _ranked_treatment_options_repair_payload(
    payload: Mapping[str, object],
    *,
    error: BaseException,
    matrix: TherapyEvidenceMatrixOutput,
    actionable_biology: ActionableBiologyOutput,
) -> dict[str, object]:
    """Return treatment-options payload with before-use-test repair guidance.

    Acceptance criteria:
        1. Determinism: Same payload, error, matrix, and biology artifact return
           the same repair payload.
        2. No mutation: The original payload mapping and source artifacts are
           not mutated.
        3. Scope: Adds only repair instructions and candidate validation text.
        4. Safety: Requires non-empty before-use tests without adding treatment
           recommendations, probabilities, or unsupported certainty.

    Args:
        payload: Original ranked-treatment prompt payload.
        error: Validation error from the first ranked-treatment output.
        matrix: Molecular-fit matrix that may contain before-use tests.
        actionable_biology: Actionable biology stage output for validation
            context.

    Returns:
        Prompt payload with a bounded repair instruction.
    """
    return {
        **dict(payload),
        "repair_instruction": {
            "previous_validation_error": str(error),
            "repair_scope": (
                "Revise only ranked_treatment_options rows whose "
                "required_before_use_tests list is empty. Each populated "
                "treatment option must include at least one before-use test or "
                "validation requirement derived from allowed_before_use_tests. "
                "If no specific biomarker test applies, use a conservative "
                "clinician/pathology review requirement from the allowed list. "
                "Do not add new therapy recommendations, probabilities, or "
                "deterministic response claims."
            ),
            "allowed_before_use_tests": _ranked_treatment_before_use_candidates(
                matrix=matrix,
                actionable_biology=actionable_biology,
            ),
        },
    }


def _ranked_treatment_before_use_candidates(
    *,
    matrix: TherapyEvidenceMatrixOutput,
    actionable_biology: ActionableBiologyOutput,
) -> list[str]:
    """Return bounded before-use-test candidates for treatment repair.

    Acceptance criteria:
        1. Determinism: Candidate order follows matrix rows, actionable biology
           rows, then conservative fallback text.
        2. No mutation: Input artifacts are not mutated.
        3. Boundedness: Empty strings are removed, duplicates are collapsed,
           and text is capped for prompt size.
        4. Safety: Always includes a conservative clinician-review fallback.

    Args:
        matrix: Molecular-fit matrix that may name required tests.
        actionable_biology: Actionable biology output that may name validation
            uncertainty.

    Returns:
        Non-empty candidate before-use-test strings for repair prompts.
    """
    candidates: list[str] = []
    for row in matrix.rows:
        candidates.extend(row.required_before_use_tests)
        if row.required_validation.strip():
            candidates.append(row.required_validation)
    for item in actionable_biology.actionable_biology:
        if item.uncertainty.strip():
            candidates.append(item.uncertainty)
    candidates.append(
        "Clinician/pathology review of source report findings and treatment "
        "eligibility before use."
    )
    return _dedupe_nonempty_texts(candidates, max_items=12, max_chars=220)


def _ranked_treatment_limitation_candidates(
    *,
    matrix: TherapyEvidenceMatrixOutput,
    actionable_biology: ActionableBiologyOutput,
) -> list[str]:
    """Return bounded, source-derived limitation candidates.

    Acceptance criteria:
        1. Determinism: Candidate order follows matrix then biology rows.
        2. No mutation: Source artifacts are not modified.
        3. Source priority: Non-empty source limitations precede fallback text.
        4. Safety: A conservative clinician-review limitation is always present.
    """
    candidates = [
        row.limitations
        for row in matrix.rows
        if row.limitations.strip()
    ]
    candidates.extend(
        item.uncertainty
        for item in actionable_biology.actionable_biology
        if item.uncertainty.strip()
    )
    candidates.append(
        "Evidence remains incomplete; clinician review is required before "
        "treatment selection."
    )
    return _dedupe_nonempty_texts(candidates, max_items=12, max_chars=220)


def _dedupe_nonempty_texts(
    values: Sequence[str],
    *,
    max_items: int,
    max_chars: int,
) -> list[str]:
    """Return bounded unique non-empty text values.

    Acceptance criteria:
        1. Determinism: First occurrence order is preserved.
        2. No mutation: The caller-owned sequence is not mutated.
        3. Validation: Invalid bounds raise `ValueError`.
        4. Boundedness: Empty values are removed and kept values are truncated.

    Args:
        values: Candidate text values.
        max_items: Maximum number of values to return.
        max_chars: Maximum characters retained per value.

    Returns:
        Unique, stripped, bounded text values.

    Raises:
        ValueError: If either bound is less than one.
    """
    if max_items < 1:
        raise ValueError("max_items must be positive")
    if max_chars < 1:
        raise ValueError("max_chars must be positive")
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        stripped = value.strip()
        if not stripped:
            continue
        key = stripped.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(stripped[:max_chars])
        if len(result) >= max_items:
            break
    return result


def _require_stage_artifact_id(artifact_id: str, stage_name: str) -> None:
    if not artifact_id.strip():
        raise StructuredArtifactGenerationError(f"{stage_name} is missing artifact_id")


def _require_row_group_or_unresolved(
    rows: Sequence[object],
    unresolved_evidence: Sequence[str],
    field_name: str,
) -> None:
    if rows:
        return
    if any(value.strip() for value in unresolved_evidence):
        return
    raise StructuredArtifactGenerationError(
        f"{field_name} is empty without unresolved_evidence"
    )


def _require_sources(values: Sequence[str], field_name: str) -> None:
    if not any(value.strip() for value in values):
        raise StructuredArtifactGenerationError(f"{field_name} must not be empty")


def _require_evidence_or_unresolved(
    source_artifact_ids: Sequence[str],
    unresolved_evidence: Sequence[str],
    field_name: str,
) -> None:
    if any(value.strip() for value in source_artifact_ids):
        return
    if any(value.strip() for value in unresolved_evidence):
        return
    raise StructuredArtifactGenerationError(
        f"{field_name} must include source_artifact_ids or unresolved_evidence"
    )


def _require_text_list_or_unresolved(
    values: Sequence[str],
    unresolved_evidence: Sequence[str],
    field_name: str,
) -> None:
    if any(value.strip() for value in values):
        return
    if any(value.strip() for value in unresolved_evidence):
        return
    raise StructuredArtifactGenerationError(
        f"{field_name} must include evidence text or unresolved_evidence"
    )


def _require_text(value: str, field_name: str) -> None:
    if not value.strip():
        raise StructuredArtifactGenerationError(f"{field_name} must not be empty")


def _require_text_list(values: Sequence[str], field_name: str) -> None:
    if not any(value.strip() for value in values):
        raise StructuredArtifactGenerationError(f"{field_name} must not be empty")


def _require_any_text(values: Sequence[str], artifact_name: str) -> None:
    if any(value.strip() for value in values):
        return
    raise StructuredArtifactGenerationError(
        f"{artifact_name} must include a clinical signal or unresolved evidence"
    )


def _require_equal_payload(actual: object, expected: object, field_name: str) -> None:
    if actual != expected:
        raise StructuredArtifactGenerationError(
            f"OncologistDecisionBrief synthesis altered staged output: {field_name}"
        )



def _with_prompt_budget(stage_name: str, packet: Mapping[str, object]) -> dict[str, object]:
    """Return a prompt packet sized for local vLLM execution.

    The decision brief pipeline intentionally uses many small packets instead of
    one large context. This helper gives every packet a stage-specific character
    budget, compacts nested text/list payloads when needed, and records budget
    metadata so operators can audit whether the local model received a full or
    compacted context.
    """
    budget = _DECISION_STAGE_PROMPT_CHAR_BUDGETS.get(
        stage_name,
        _DEFAULT_DECISION_STAGE_PROMPT_CHAR_BUDGET,
    )
    original = dict(packet)
    original_chars = _json_chars(original)
    compacted = original if original_chars <= budget else _compact_payload_to_budget(
        original,
        budget,
    )
    compacted_chars = _json_chars(compacted)
    compacted = dict(compacted)
    compacted["prompt_budget"] = {
        "stage_name": stage_name,
        "char_budget": budget,
        "original_chars": original_chars,
        "final_chars": compacted_chars,
        "approx_original_tokens": _approx_tokens(original_chars),
        "approx_final_tokens": _approx_tokens(compacted_chars),
        "compacted": compacted_chars < original_chars,
        "within_budget": compacted_chars <= budget,
        "operator_note": (
            "Decision-brief stages are intentionally decomposed into smaller "
            "model calls for local GPU execution; final synthesis aggregates "
            "validated structured outputs."
        ),
    }
    return compacted


def _compact_payload_to_budget(
    packet: Mapping[str, object],
    budget: int,
) -> dict[str, object]:
    """Compact nested payloads without fabricating replacement evidence."""
    settings = [
        (4000, 24),
        (2400, 18),
        (1600, 14),
        (1000, 10),
        (700, 8),
        (420, 6),
    ]
    compacted: object = dict(packet)
    for max_string_chars, max_list_items in settings:
        compacted = _bounded_json_value(
            packet,
            max_string_chars=max_string_chars,
            max_list_items=max_list_items,
        )
        if _json_chars(compacted) <= budget:
            break
    if not isinstance(compacted, dict):
        return {"compacted_payload": compacted}
    if _json_chars(compacted) > budget:
        compacted = dict(compacted)
        compacted["budget_warning"] = (
            "Prompt packet still exceeds configured budget after deterministic "
            "compaction. Consider reducing upstream retrieval breadth or model "
            "context requirements for this stage."
        )
    return compacted


def _bounded_json_value(
    value: object,
    *,
    max_string_chars: int,
    max_list_items: int,
) -> object:
    if isinstance(value, str):
        if len(value) <= max_string_chars:
            return value
        return value[: max_string_chars - 80].rstrip() + " … [truncated for stage prompt budget]"
    if isinstance(value, Mapping):
        return {
            str(key): _bounded_json_value(
                child,
                max_string_chars=max_string_chars,
                max_list_items=max_list_items,
            )
            for key, child in value.items()
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        items = list(value)
        kept = [
            _bounded_json_value(
                item,
                max_string_chars=max_string_chars,
                max_list_items=max_list_items,
            )
            for item in items[:max_list_items]
        ]
        if len(items) > max_list_items:
            kept.append(
                {
                    "truncated_items": len(items) - max_list_items,
                    "reason": "stage prompt budget",
                }
            )
        return kept
    return value


def _json_chars(value: object) -> int:
    return len(json.dumps(value, sort_keys=True, default=str))


def _approx_tokens(chars: int) -> int:
    return max(1, chars // 4)


def _tool_outputs_by_workflow(
    tool_outputs: object,
    workflows: set[str],
) -> list[Mapping[str, object]]:
    if not isinstance(tool_outputs, Sequence) or isinstance(tool_outputs, str):
        return []
    return [
        item
        for item in tool_outputs
        if isinstance(item, Mapping)
        and str(item.get("workflow", "")) in workflows
    ]


def _test_modalities() -> list[str]:
    return [
        "ctDNA",
        "tissue_NGS",
        "IHC",
        "FISH",
        "RNA_fusion_testing",
        "pathology_review",
        "focused_biomarker_test",
        "other",
    ]




def _require_translational_assessment(brief: OncologistDecisionBrief) -> None:
    assessment = brief.translational_assessment
    for question in _translational_questions(assessment):
        prefix = f"brief.translational_assessment.{question.question_key}"
        _require_text(question.question, f"{prefix}.question")
        _require_text(question.answer, f"{prefix}.answer")
        _require_text_list_or_unresolved(
            question.supporting_evidence,
            question.unresolved_evidence,
            f"{prefix}.supporting_evidence",
        )
        _require_text_list(question.validation_next, f"{prefix}.validation_next")
        _require_evidence_or_unresolved(
            question.source_artifact_ids,
            question.unresolved_evidence,
            f"{prefix}.source_artifact_ids",
        )



def _require_therapy_escape_sankey_paths(brief: OncologistDecisionBrief) -> None:
    """Validate explicit therapy-to-escape Sankey paths for the report UI."""
    if not brief.therapy_escape_sankey_paths:
        raise StructuredArtifactGenerationError(
            "OncologistDecisionBrief must include therapy_escape_sankey_paths"
        )
    for index, item in enumerate(brief.therapy_escape_sankey_paths):
        prefix = f"brief.therapy_escape_sankey_paths[{index}]"
        _require_text(item.therapy_display_name, f"{prefix}.therapy_display_name")
        _require_text(item.molecular_target_or_pathway, f"{prefix}.molecular_target_or_pathway")
        _require_text(item.target_driver_status, f"{prefix}.target_driver_status")
        _require_text(item.predicted_behavior_state, f"{prefix}.predicted_behavior_state")
        _require_text(item.escape_pathway, f"{prefix}.escape_pathway")
        _require_text(item.monitoring_timing, f"{prefix}.monitoring_timing")
        _require_evidence_or_unresolved(
            item.source_artifact_ids,
            item.unresolved_evidence,
            f"{prefix}.source_artifact_ids",
        )
        if _looks_like_unresolved_agent(item.therapy_display_name):
            _require_text_list(
                item.unresolved_evidence,
                f"{prefix}.unresolved_evidence",
            )


def _looks_like_unresolved_agent(value: str) -> bool:
    lowered = value.casefold()
    return "actual agent unresolved" in lowered or "therapy class" in lowered
def _validate_decision_brief(brief: OncologistDecisionBrief) -> None:
    """Validate final decision brief safety and minimum clinical utility."""
    if brief.validation_status != "needs_review":
        raise StructuredArtifactGenerationError(
            "OncologistDecisionBrief validation_status must be needs_review"
        )
    if not brief.clinical_decision_summary.strip():
        raise StructuredArtifactGenerationError(
            "OncologistDecisionBrief is missing clinical_decision_summary"
        )
    if not brief.source_artifact_ids:
        raise StructuredArtifactGenerationError(
            "OncologistDecisionBrief is missing source_artifact_ids"
        )
    if not brief.evidence_limitations:
        raise StructuredArtifactGenerationError(
            "OncologistDecisionBrief must surface evidence limitations"
        )
    _require_translational_assessment(brief)
    _require_therapy_escape_sankey_paths(brief)
    require_decision_brief_rows_carry_evidence_or_unresolved(brief)
    _require_safe_output(brief.model_dump_json(), "OncologistDecisionBrief")
