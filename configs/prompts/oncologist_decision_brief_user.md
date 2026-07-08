Generate OncologistDecisionBrief.

The artifact_id must be exactly:
{planned_artifact_id}

Payload JSON:
{payload_json}

Synthesize only from the staged outputs in the payload. Do not introduce genes, drugs, biomarkers, pathways, evidence, tests, guidelines, or trials that are absent from those staged outputs.

Copy these final structured fields exactly from the corresponding staged outputs, preserving row content and order:

- current_tumor_state from current_state_stage.current_tumor_state
- actionable_biology from actionable_biology_stage.actionable_biology
- ranked_treatment_options from ranked_treatment_options_stage.ranked_treatment_options
- treatment_pressure_map from treatment_pressure_stage.treatment_pressure_map
- resistance_forecast from resistance_forecast_stage.resistance_forecast
- biomarker_watch_list from biomarker_watch_stage.biomarker_watch_list
- retesting_triggers from retesting_trigger_stage.retesting_triggers
- next_test_recommendations from next_test_stage.next_test_recommendations

Use final synthesis only for clinical_decision_summary and evidence_limitations. Deduplicate overlapping ideas in the summary, reconcile conflicts into evidence_limitations, and produce a concise clinical_decision_summary that answers: what can be treated now, why it fits, how the tumor could escape, what to monitor, when to re-test, and what test to order next. Set validation_status to needs_review and include source_artifact_ids and source_chunk_ids. Every copied treatment, resistance, biomarker, retesting, and next-test row must retain its source_artifact_ids or row-level unresolved_evidence.
