from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

import pytest

from translume_core.compiler.decision_brief import (
    DecisionBriefStageOutputs,
    enforce_patient_population_alignment_and_evidence_labels,
    fill_resistance_forecast_biomarkers,
    generate_treatment_options_stage_with_model,
    require_decision_brief_matches_stage_outputs,
    require_decision_brief_rows_carry_evidence_or_unresolved,
    require_decision_stage_outputs_evidence_grounded,
    synthesize_oncologist_decision_brief_from_stage_outputs,
)
from translume_schemas.evidence import EvidenceContextBundle
from translume_schemas.extraction import MolecularFinding, ReportExtractionOutput
from translume_schemas.graph import GraphEvidenceArtifact
from translume_schemas.matrix import MolecularFitRow, TherapyEvidenceMatrixOutput
from translume_schemas.medea import MedeaReasoningArtifact
from translume_schemas.phenotype import BiologicalAxis, MolecularPhenotypeOutput
from translume_schemas.tools import ToolRunArtifact

from translume_core.compiler.structured_model_artifacts import (
    StructuredArtifactGenerationError,
)
from translume_schemas.decision_brief import (
    ActionableBiologyItem,
    ActionableBiologyOutput,
    BiomarkerWatchItem,
    BiomarkerWatchListOutput,
    CurrentTumorState,
    CurrentTumorStateOutput,
    EvidenceLimitation,
    EvidenceSentence,
    NextTestRecommendation,
    NextTestRecommendationsOutput,
    OncologistDecisionBrief,
    RankedTreatmentOption,
    RankedTreatmentOptionsOutput,
    ResistanceForecastItem,
    ResistanceForecastOutput,
    RetestingTrigger,
    RetestingTriggersOutput,
    TranslationalAssessmentOutput,
    TranslationalQuestionAssessment,
    TreatmentPressureMapOutput,
    TreatmentPressureMapRow,
)


_SOURCE_IDS = ["artifact_report", "artifact_graph"]
_CHUNK_IDS = ["chunk_1"]


class SequencedDecisionBriefProvider:
    """Test provider that returns one configured output per model call."""

    def __init__(self, outputs: list[dict[str, object]]) -> None:
        self.outputs = outputs
        self.schema_names: list[str] = []
        self.user_prompts: list[str] = []

    async def structured_completion(
        self,
        *,
        model_name: str,
        system_prompt: str,
        user_prompt: str,
        schema_name: str,
        json_schema: dict[str, object],
    ) -> dict[str, object]:
        self.schema_names.append(schema_name)
        self.user_prompts.append(user_prompt)
        output_index = min(len(self.schema_names), len(self.outputs)) - 1
        payload = deepcopy(self.outputs[output_index])
        payload["artifact_id"] = _planned_artifact_id(user_prompt)
        return payload


def test_decision_stage_outputs_pass_when_evidence_grounded() -> None:
    stages = _stage_outputs()

    require_decision_stage_outputs_evidence_grounded(**stages)



def test_deterministic_decision_brief_synthesis_copies_stage_rows() -> None:
    stages = _stage_outputs()
    stage_outputs = DecisionBriefStageOutputs(**stages)

    brief = synthesize_oncologist_decision_brief_from_stage_outputs(
        planned_artifact_id="artifact_decision_brief",
        stage_outputs=stage_outputs,
        source_artifact_ids=["artifact_report", *stage_outputs.artifact_ids()],
        source_chunk_ids=_CHUNK_IDS,
    )

    require_decision_brief_matches_stage_outputs(
        brief=brief,
        **stages,
    )
    assert brief.ranked_treatment_options == stages[
        "treatment_options"
    ].ranked_treatment_options
    assert brief.resistance_forecast == stages[
        "resistance_forecast"
    ].resistance_forecast
    assert brief.source_chunk_ids == _CHUNK_IDS
    assert "MTAP" in brief.clinical_decision_summary
    assert brief.evidence_limitations


def test_decision_brief_synthesis_adds_explicit_therapy_escape_paths() -> None:
    stages = _stage_outputs()
    stage_outputs = DecisionBriefStageOutputs(**stages)

    brief = synthesize_oncologist_decision_brief_from_stage_outputs(
        planned_artifact_id="artifact_decision_brief",
        stage_outputs=stage_outputs,
        source_artifact_ids=["artifact_report", *stage_outputs.artifact_ids()],
        source_chunk_ids=_CHUNK_IDS,
    )

    assert brief.therapy_escape_sankey_paths
    path = brief.therapy_escape_sankey_paths[0]
    assert path.molecular_target_or_pathway == "methylation dependency context"
    assert path.predicted_behavior_state
    assert "bypass" in path.escape_pathway
    assert path.monitoring_timing
    assert path.source_artifact_ids or path.unresolved_evidence


def test_therapy_escape_paths_use_actual_trial_agents_when_evidence_supports_them() -> None:
    stages = _stage_outputs()
    stage_outputs = DecisionBriefStageOutputs(
        **stages,
        evidence_sentence_map=(
            EvidenceSentence(
                evidence_id="evidence_trial_tng908",
                evidence_label="Clinical trial criterion",
                statement="Safety and tolerability of TNG908 in patients with MTAP-deleted solid tumors",
                source_type="clinical_trial",
                quote="TNG908 in patients with MTAP-deleted solid tumors",
                source_artifact_ids=["artifact_tool"],
            ),
        ),
    )

    brief = synthesize_oncologist_decision_brief_from_stage_outputs(
        planned_artifact_id="artifact_decision_brief",
        stage_outputs=stage_outputs,
        source_artifact_ids=["artifact_report", *stage_outputs.artifact_ids()],
        source_chunk_ids=_CHUNK_IDS,
    )

    assert brief.therapy_escape_sankey_paths
    assert "TNG908" in brief.therapy_escape_sankey_paths[0].therapy_display_name
    assert brief.therapy_escape_sankey_paths[0].therapy_source == "resolved_drug_or_trial_agent"


def test_therapy_escape_paths_mark_actual_agent_unresolved_without_agent_evidence() -> None:
    stages = _stage_outputs()
    stage_outputs = DecisionBriefStageOutputs(**stages)

    brief = synthesize_oncologist_decision_brief_from_stage_outputs(
        planned_artifact_id="artifact_decision_brief",
        stage_outputs=stage_outputs,
        source_artifact_ids=["artifact_report", *stage_outputs.artifact_ids()],
        source_chunk_ids=_CHUNK_IDS,
    )

    path = brief.therapy_escape_sankey_paths[0]
    assert path.therapy_display_name.startswith("Actual agent unresolved")
    assert path.unresolved_evidence


def test_patient_population_alignment_is_hard_unresolved_when_context_is_missing() -> None:
    stages = _stage_outputs()
    assessment = stages["translational_assessment"]
    supported_population = assessment.patient_population_alignment.model_copy(
        update={
            "answer": "Population fit appears supported.",
            "status": "supported",
            "evidence_strength": "strong",
            "supporting_evidence": ["Trial evidence appears relevant."],
            "source_artifact_ids": _SOURCE_IDS,
        }
    )
    assessment = assessment.model_copy(
        update={"patient_population_alignment": supported_population}
    )

    hardened = enforce_patient_population_alignment_and_evidence_labels(
        assessment,
        context=_minimal_context_missing_population_fit(),
        evidence_sentence_map=(),
    )

    population = hardened.patient_population_alignment
    assert population.status == "unresolved"
    assert population.evidence_strength == "unresolved"
    assert not population.supporting_evidence
    assert any("line-of-therapy" in item for item in population.unresolved_evidence)
    assert "Unresolved population fit" in population.evidence_labels

def test_decision_stage_outputs_allow_row_level_unresolved_evidence() -> None:
    stages = _stage_outputs()
    option = stages["treatment_options"].ranked_treatment_options[0]
    stages["treatment_options"] = stages["treatment_options"].model_copy(
        update={
            "ranked_treatment_options": [
                option.model_copy(
                    update={
                        "source_artifact_ids": [],
                        "unresolved_evidence": [
                            "No source-backed treatment evidence resolved for this row."
                        ],
                    }
                )
            ]
        }
    )

    require_decision_stage_outputs_evidence_grounded(**stages)


def test_decision_stage_outputs_fail_without_row_evidence_or_unresolved() -> None:
    stages = _stage_outputs()
    option = stages["treatment_options"].ranked_treatment_options[0]
    stages["treatment_options"] = stages["treatment_options"].model_copy(
        update={
            "ranked_treatment_options": [
                option.model_copy(
                    update={
                        "source_artifact_ids": [],
                        "unresolved_evidence": [],
                    }
                )
            ]
        }
    )

    with pytest.raises(
        StructuredArtifactGenerationError,
        match="source_artifact_ids or unresolved_evidence",
    ):
        require_decision_stage_outputs_evidence_grounded(**stages)


@pytest.mark.asyncio
async def test_treatment_options_fills_empty_required_before_use_tests() -> None:
    output = _treatment_options_output(required_before_use_tests=[])
    original = deepcopy(output)
    provider = SequencedDecisionBriefProvider([output])

    result = await generate_treatment_options_stage_with_model(
        context=_minimal_context_missing_population_fit(),
        phenotype=_phenotype(),
        matrix=_matrix(),
        actionable_biology=_stage_outputs()["actionable_biology"],
        model_provider=provider,
        model_name="local-test-model",
        prompts_root=Path("configs/prompts"),
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    assert provider.schema_names == ["RankedTreatmentOptionsOutput"]
    before_use_tests = result.ranked_treatment_options[0].required_before_use_tests
    assert before_use_tests[0] == "confirm MTAP status"
    assert "Confirm MTAP locus or protein status." in before_use_tests
    assert output == original


@pytest.mark.asyncio
async def test_treatment_options_uses_conservative_fallback_for_empty_tests() -> None:
    provider = SequencedDecisionBriefProvider(
        [_treatment_options_output(required_before_use_tests=[])]
    )
    matrix = _matrix().model_copy(update={"rows": []})
    actionable_biology = _stage_outputs()["actionable_biology"].model_copy(
        update={"actionable_biology": []}
    )

    result = await generate_treatment_options_stage_with_model(
        context=_minimal_context_missing_population_fit(),
        phenotype=_phenotype(),
        matrix=matrix,
        actionable_biology=actionable_biology,
        model_provider=provider,
        model_name="local-test-model",
        prompts_root=Path("configs/prompts"),
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    assert provider.schema_names == ["RankedTreatmentOptionsOutput"]
    assert result.ranked_treatment_options[0].required_before_use_tests == [
        "Clinician/pathology review of source report findings and treatment "
        "eligibility before use."
    ]


@pytest.mark.asyncio
async def test_treatment_options_fills_empty_limitations_from_sources() -> None:
    """Source-derived limitations should prevent incomplete-row failures."""
    output = _treatment_options_output(
        required_before_use_tests=["confirm MTAP status"],
        limitations=[],
    )
    original = deepcopy(output)
    provider = SequencedDecisionBriefProvider([output])

    result = await generate_treatment_options_stage_with_model(
        context=_minimal_context_missing_population_fit(),
        phenotype=_phenotype(),
        matrix=_matrix(),
        actionable_biology=_stage_outputs()["actionable_biology"],
        model_provider=provider,
        model_name="local-test-model",
        prompts_root=Path("configs/prompts"),
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    assert provider.schema_names == ["RankedTreatmentOptionsOutput"]
    assert result.ranked_treatment_options[0].limitations[0] == (
        "Requires human validation."
    )
    assert output == original


@pytest.mark.asyncio
async def test_treatment_options_fills_empty_limitations_in_third_row() -> None:
    """Normalization must cover every populated option, not only the first."""
    output = _treatment_options_output(
        required_before_use_tests=["confirm MTAP status"]
    )
    template = deepcopy(output["ranked_treatment_options"][0])
    second = {**template, "rank": 2}
    third = {**template, "rank": 3, "limitations": []}
    output["ranked_treatment_options"] = [template, second, third]

    result = await generate_treatment_options_stage_with_model(
        context=_minimal_context_missing_population_fit(),
        phenotype=_phenotype(),
        matrix=_matrix(),
        actionable_biology=_stage_outputs()["actionable_biology"],
        model_provider=SequencedDecisionBriefProvider([output]),
        model_name="local-test-model",
        prompts_root=Path("configs/prompts"),
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    assert result.ranked_treatment_options[2].limitations
    assert result.ranked_treatment_options[2].limitations[0] == (
        "Requires human validation."
    )


@pytest.mark.asyncio
async def test_treatment_options_unrelated_validation_error_is_not_repaired() -> None:
    provider = SequencedDecisionBriefProvider(
        [
            _treatment_options_output(
                required_before_use_tests=["confirm MTAP status"],
                therapy_name_or_class="",
            )
        ]
    )

    with pytest.raises(
        StructuredArtifactGenerationError,
        match="therapy_name_or_class must not be empty",
    ):
        await generate_treatment_options_stage_with_model(
            context=_minimal_context_missing_population_fit(),
            phenotype=_phenotype(),
            matrix=_matrix(),
            actionable_biology=_stage_outputs()["actionable_biology"],
            model_provider=provider,
            model_name="local-test-model",
            prompts_root=Path("configs/prompts"),
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )

    assert provider.schema_names == ["RankedTreatmentOptionsOutput"]


def test_decision_brief_rows_require_evidence_or_unresolved() -> None:
    stages = _stage_outputs()
    brief = _decision_brief(stages)
    option = brief.ranked_treatment_options[0]
    brief = brief.model_copy(
        update={
            "ranked_treatment_options": [
                option.model_copy(
                    update={
                        "source_artifact_ids": [],
                        "unresolved_evidence": [],
                    }
                )
            ]
        }
    )

    with pytest.raises(
        StructuredArtifactGenerationError,
        match="source_artifact_ids or unresolved_evidence",
    ):
        require_decision_brief_rows_carry_evidence_or_unresolved(brief)


def test_row_level_unresolved_evidence_surfaces_as_limitation() -> None:
    stages = _stage_outputs()
    option = stages["treatment_options"].ranked_treatment_options[0]
    stages["treatment_options"] = stages["treatment_options"].model_copy(
        update={
            "ranked_treatment_options": [
                option.model_copy(
                    update={
                        "source_artifact_ids": [],
                        "unresolved_evidence": ["Guideline support was not resolved."],
                    }
                )
            ]
        }
    )
    stage_outputs = DecisionBriefStageOutputs(**stages)

    brief = synthesize_oncologist_decision_brief_from_stage_outputs(
        planned_artifact_id="artifact_decision_brief",
        stage_outputs=stage_outputs,
        source_artifact_ids=["artifact_report", *stage_outputs.artifact_ids()],
        source_chunk_ids=_CHUNK_IDS,
    )

    assert any(
        limitation.limitation == "Guideline support was not resolved."
        for limitation in brief.evidence_limitations
    )


def test_decision_stage_outputs_reject_unsupported_certainty_language() -> None:
    stages = _stage_outputs()
    forecast = stages["resistance_forecast"].resistance_forecast[0]
    stages["resistance_forecast"] = stages["resistance_forecast"].model_copy(
        update={
            "resistance_forecast": [
                forecast.model_copy(
                    update={
                        "description": "This alteration will respond to therapy."
                    }
                )
            ]
        }
    )

    with pytest.raises(
        StructuredArtifactGenerationError,
        match="unsupported certainty",
    ):
        require_decision_stage_outputs_evidence_grounded(**stages)


def test_decision_stage_outputs_reject_treatment_unsupported_claims() -> None:
    stages = _stage_outputs()
    option = stages["treatment_options"].ranked_treatment_options[0]
    stages["treatment_options"] = stages["treatment_options"].model_copy(
        update={
            "ranked_treatment_options": [
                option.model_copy(
                    update={"why_it_fits": "This is a guaranteed response."}
                )
            ]
        }
    )

    with pytest.raises(
        StructuredArtifactGenerationError,
        match="unsupported certainty",
    ):
        require_decision_stage_outputs_evidence_grounded(**stages)


def test_decision_stage_outputs_reject_next_test_unsupported_claims() -> None:
    stages = _stage_outputs()
    test = stages["next_tests"].next_test_recommendations[0]
    stages["next_tests"] = stages["next_tests"].model_copy(
        update={
            "next_test_recommendations": [
                test.model_copy(
                    update={
                        "result_that_would_change_management": (
                            "This test gives a definitive cure path."
                        )
                    }
                )
            ]
        }
    )

    with pytest.raises(
        StructuredArtifactGenerationError,
        match="unsupported certainty",
    ):
        require_decision_stage_outputs_evidence_grounded(**stages)


def test_decision_brief_fails_if_final_synthesis_changes_stage_rows() -> None:
    stages = _stage_outputs()
    brief = _decision_brief(stages)
    option = brief.ranked_treatment_options[0]
    changed_brief = brief.model_copy(
        update={
            "ranked_treatment_options": [
                option.model_copy(update={"therapy_name_or_class": "new therapy"})
            ]
        }
    )

    with pytest.raises(
        StructuredArtifactGenerationError,
        match="synthesis altered staged output",
    ):
        require_decision_brief_matches_stage_outputs(
            brief=changed_brief,
            **stages,
        )


def test_decision_brief_requires_stage_source_ids() -> None:
    stages = _stage_outputs()
    brief = _decision_brief(stages).model_copy(
        update={"source_artifact_ids": ["artifact_report"]}
    )

    with pytest.raises(
        StructuredArtifactGenerationError,
        match="missing stage source_artifact_ids",
    ):
        require_decision_brief_matches_stage_outputs(
            brief=brief,
            **stages,
        )


def _stage_outputs() -> dict[str, object]:
    return {
        "current_state": CurrentTumorStateOutput(
            artifact_id="artifact_current_state",
            current_tumor_state=CurrentTumorState(
                dominant_drivers=["MTAP loss"],
                active_pathways=["methylation dependency context"],
                co_drivers=["CDKN2A loss"],
                actionable_alterations=["MTAP loss"],
                resistance_or_uncertain_alterations=["LYN gain"],
                immune_and_repair_context=["CHEK2 DNA repair context"],
                missing_data=["longitudinal resistance sample"],
                source_artifact_ids=_SOURCE_IDS,
            ),
        ),
        "actionable_biology": ActionableBiologyOutput(
            artifact_id="artifact_actionable_biology",
            actionable_biology=[
                ActionableBiologyItem(
                    biology="methylation dependency context",
                    alteration_or_marker="MTAP loss",
                    actionability="trial_option",
                    evidence_level="source-backed hypothesis requiring review",
                    rationale="Report and graph evidence support review.",
                    uncertainty="Clinical use requires clinician validation.",
                    source_artifact_ids=_SOURCE_IDS,
                )
            ],
        ),
        "treatment_options": RankedTreatmentOptionsOutput(
            artifact_id="artifact_treatment_options",
            ranked_treatment_options=[
                RankedTreatmentOption(
                    rank=1,
                    therapy_name_or_class="MTAP-loss clinical trial category",
                    clinical_use="trial_option",
                    therapy_class="methylation dependency context",
                    matched_biomarkers=["MTAP"],
                    why_it_fits="The uploaded report includes MTAP loss.",
                    evidence_level="source-backed hypothesis requiring review",
                    resistance_risks=["bypass signaling"],
                    required_before_use_tests=["confirm MTAP status"],
                    limitations=["No final therapy selection is made."],
                    source_artifact_ids=_SOURCE_IDS,
                )
            ],
        ),
        "treatment_pressure": TreatmentPressureMapOutput(
            artifact_id="artifact_treatment_pressure",
            treatment_pressure_map=[
                TreatmentPressureMapRow(
                    therapy_name_or_class="MTAP-loss clinical trial category",
                    target_or_pathway="methylation dependency context",
                    why_it_fits="MTAP loss maps to source-backed context.",
                    selective_pressure="Pathway pressure may select bypass signaling.",
                    likely_escape_routes=["bypass signaling"],
                    biomarkers_to_watch=["MTAP", "LYN"],
                    evidence_basis=_SOURCE_IDS,
                    source_artifact_ids=_SOURCE_IDS,
                )
            ],
        ),
        "resistance_forecast": ResistanceForecastOutput(
            artifact_id="artifact_resistance_forecast",
            resistance_forecast=[
                ResistanceForecastItem(
                    escape_route="bypass_signaling",
                    description="Monitor for bypass signaling under pathway pressure.",
                    associated_treatment_pressure="methylation dependency pressure",
                    supporting_evidence=_SOURCE_IDS,
                    biomarkers_to_monitor=["LYN", "MTAP"],
                    source_artifact_ids=_SOURCE_IDS,
                )
            ],
        ),
        "biomarker_watch": BiomarkerWatchListOutput(
            artifact_id="artifact_biomarker_watch",
            biomarker_watch_list=[
                BiomarkerWatchItem(
                    biomarker="LYN",
                    alteration_type="copy_number_gain",
                    why_watch="Potential bypass signaling marker.",
                    associated_treatment_pressure="methylation dependency pressure",
                    preferred_test="tissue_NGS",
                    trigger="progression or therapy switch",
                    priority="high",
                    source_artifact_ids=_SOURCE_IDS,
                )
            ],
        ),
        "retesting_triggers": RetestingTriggersOutput(
            artifact_id="artifact_retesting_triggers",
            retesting_triggers=[
                RetestingTrigger(
                    clinical_event="radiographic progression",
                    recommended_test="tissue_NGS",
                    rationale="Progression can reveal resistance evolution.",
                    what_result_changes="New actionable resistance signal.",
                    urgency="high",
                    source_artifact_ids=_SOURCE_IDS,
                )
            ],
        ),
        "next_tests": NextTestRecommendationsOutput(
            artifact_id="artifact_next_tests",
            next_test_recommendations=[
                NextTestRecommendation(
                    test_type="tissue_NGS",
                    timing="at progression or before next systemic therapy",
                    rationale="Tissue can evaluate CNV and transformation context.",
                    biomarkers_or_questions=["MTAP", "LYN", "new fusions"],
                    result_that_would_change_management="New resistance signal.",
                    limitations=["ctDNA can be considered if tissue is unavailable."],
                    source_artifact_ids=_SOURCE_IDS,
                    priority="high",
                )
            ],
        ),
        "translational_assessment": TranslationalAssessmentOutput(
            artifact_id="artifact_translational_assessment",
            target_relevance=_question(
                "target_relevance",
                "Is the target actually relevant to this tumor's behavior?",
                "MTAP loss is tied to the staged tumor behavior context.",
            ),
            biomarker_evidence=_question(
                "biomarker_evidence",
                "Does the biomarker evidence support action, or is it weak/incomplete?",
                "The biomarker signal is trial-category and requires validation.",
                status="weak_or_incomplete",
                evidence_strength="weak",
            ),
            resistance_mechanisms=_question(
                "resistance_mechanisms",
                "Are resistance mechanisms already present or likely to emerge?",
                "Bypass signaling is a staged resistance watch item.",
            ),
            patient_population_alignment=_question(
                "patient_population_alignment",
                "Is the patient population aligned with the evidence behind the treatment?",
                "Population fit is unresolved without stage, line, and cohort context.",
                status="unresolved",
                evidence_strength="unresolved",
                unresolved=["Patient population evidence was not resolved."],
            ),
            evidence_resolution=_question(
                "evidence_resolution",
                "What evidence is strong, what is unresolved, and what needs validation next?",
                "Validate MTAP status and repeat profiling at progression.",
            ),
        ),
    }


def _phenotype() -> MolecularPhenotypeOutput:
    return MolecularPhenotypeOutput(
        artifact_id="artifact_phenotype",
        axes=[
            BiologicalAxis(
                axis_id="axis_mtap",
                label="MTAP methylation dependency review axis",
                supporting_finding_ids=["finding_mtap"],
                evidence_class="model_derived_hypothesis",
                uncertainty="Requires validation before clinical interpretation.",
                validation_needed=True,
            )
        ],
    )


def _matrix() -> TherapyEvidenceMatrixOutput:
    return TherapyEvidenceMatrixOutput(
        artifact_id="artifact_matrix",
        rows=[
            MolecularFitRow(
                rank=1,
                molecular_fit="MTAP PRMT5 review context",
                fit_label="reviewable_molecular_fit",
                why_from_omics="MTAP copy-number loss is present in the report.",
                evidence_basis="source finding with graph support",
                limitations="Requires human validation.",
                required_validation="Confirm MTAP locus or protein status.",
                clinical_use="trial_option",
                therapy_class="methylation dependency context",
                matched_biomarkers=["MTAP"],
                resistance_risks=["Bypass context requires review."],
                required_before_use_tests=["confirm MTAP status"],
                confidence="needs_review",
                evidence_level="source-backed hypothesis requiring review",
            )
        ],
    )


def _treatment_options_output(
    *,
    required_before_use_tests: list[str],
    therapy_name_or_class: str = "MTAP-loss clinical trial category",
    limitations: list[str] | None = None,
) -> dict[str, object]:
    return {
        "ranked_treatment_options": [
            {
                "rank": 1,
                "therapy_name_or_class": therapy_name_or_class,
                "clinical_use": "trial_option",
                "therapy_class": "methylation dependency context",
                "matched_biomarkers": ["MTAP"],
                "why_it_fits": "The uploaded report includes MTAP loss.",
                "evidence_level": "source-backed hypothesis requiring review",
                "resistance_risks": ["bypass signaling"],
                "required_before_use_tests": required_before_use_tests,
                "limitations": (
                    ["No final therapy selection is made."]
                    if limitations is None
                    else limitations
                ),
                "source_artifact_ids": ["artifact_extraction"],
                "unresolved_evidence": [],
                "confidence": "needs_review",
            }
        ],
        "unresolved_evidence": [],
    }


def test_resistance_forecast_fills_empty_biomarkers_from_evidence() -> None:
    """Use pressure biomarkers and report genes without inventing values."""
    stages = _stage_outputs()
    original = stages["resistance_forecast"]
    forecast = original.model_copy(
        update={
            "resistance_forecast": [
                original.resistance_forecast[0].model_copy(
                    update={"biomarkers_to_monitor": []}
                )
            ]
        }
    )

    normalized = fill_resistance_forecast_biomarkers(
        forecast,
        context=_minimal_context_missing_population_fit(),
        treatment_pressure=stages["treatment_pressure"],
    )

    assert normalized.resistance_forecast[0].biomarkers_to_monitor == [
        "MTAP",
        "LYN",
    ]
    assert forecast.resistance_forecast[0].biomarkers_to_monitor == []


def _planned_artifact_id(user_prompt: str) -> str:
    marker = "The artifact_id must be exactly:\n"
    if marker not in user_prompt:
        raise AssertionError("planned artifact marker missing from prompt")
    return user_prompt.split(marker, 1)[1].split("\n", 1)[0].strip()


def _question(
    key: str,
    question: str,
    answer: str,
    *,
    status: str = "supported",
    evidence_strength: str = "moderate",
    unresolved: list[str] | None = None,
) -> TranslationalQuestionAssessment:
    return TranslationalQuestionAssessment(
        question_key=key,
        question=question,
        answer=answer,
        status=status,
        evidence_strength=evidence_strength,
        supporting_evidence=[answer] if status != "unresolved" else [],
        unresolved_evidence=list(unresolved or []),
        validation_next=["Clinician review and source validation are required."],
        source_artifact_ids=_SOURCE_IDS if status != "unresolved" else [],
        confidence="needs_review",
    )



def _minimal_context_missing_population_fit() -> EvidenceContextBundle:
    extraction = ReportExtractionOutput(
        artifact_id="artifact_extraction",
        report_type="ngs",
        disease="Dedifferentiated chondrosarcoma",
        specimen="soft tissue",
        tumor_percentage="80%",
        molecular_findings=[
            MolecularFinding(
                finding_id="finding_mtap",
                gene="MTAP",
                alteration="copy number loss",
                alteration_type="copy_number_loss",
                confidence=0.95,
                source_text="MTAP copy number loss",
            )
        ],
        source_file_id="file_ngs",
    )
    return EvidenceContextBundle(
        artifact_id="artifact_context",
        extraction=extraction,
        graph_evidence=GraphEvidenceArtifact(
            artifact_id="artifact_graph",
            source_entity_ids=[],
            nodes=[],
            edges=[],
        ),
        tool_outputs=[
            ToolRunArtifact(
                artifact_id="artifact_tool",
                workflow="therapy_context",
                input_entity_ids=[],
                summary="Therapy context without cohort or eligibility match.",
                evidence_items=[],
            )
        ],
        medea_reasoning=MedeaReasoningArtifact(
            artifact_id="artifact_medea",
            reasoning_mode="bounded_review_support",
            summary="Hypothesis support only.",
            supported_hypotheses=[],
            weakened_hypotheses=[],
        ),
    )


def _decision_brief(stages: dict[str, object]) -> OncologistDecisionBrief:
    stage_ids = [stage.artifact_id for stage in stages.values()]
    return OncologistDecisionBrief(
        artifact_id="artifact_decision_brief",
        clinical_decision_summary=(
            "MTAP loss creates a reviewable treatment logic signal with "
            "bypass signaling watch items and progression-based re-testing."
        ),
        current_tumor_state=stages["current_state"].current_tumor_state,
        actionable_biology=stages["actionable_biology"].actionable_biology,
        ranked_treatment_options=stages["treatment_options"].ranked_treatment_options,
        treatment_pressure_map=stages["treatment_pressure"].treatment_pressure_map,
        resistance_forecast=stages["resistance_forecast"].resistance_forecast,
        biomarker_watch_list=stages["biomarker_watch"].biomarker_watch_list,
        retesting_triggers=stages["retesting_triggers"].retesting_triggers,
        next_test_recommendations=stages["next_tests"].next_test_recommendations,
        translational_assessment=stages["translational_assessment"],
        evidence_limitations=[
            EvidenceLimitation(
                limitation="No longitudinal sample was available.",
                impact="Resistance paths remain watch items.",
                needed_resolution="Repeat molecular profiling at progression.",
                source_artifact_ids=_SOURCE_IDS,
            )
        ],
        source_artifact_ids=[*_SOURCE_IDS, *stage_ids],
        source_chunk_ids=_CHUNK_IDS,
    )
