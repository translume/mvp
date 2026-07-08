Generate TumorBehaviorModelOutput for the Translume MVP.

The artifact_id must be exactly:
{planned_artifact_id}

Payload JSON:
{payload_json}

Use only these state labels when supported by evidence or explicit missing-evidence reasoning:
- driver_dependency
- bypass_signaling_risk
- secondary_resistance_mutation_risk
- copy_number_evolution_risk
- fusion_rearrangement_risk
- dna_repair_restoration_risk
- immune_escape_risk
- histologic_transformation_risk
- resistant_subclone_expansion_risk
- proliferative
- stress_adapted_survival
- plastic_dedifferentiated
- dormant_quiescent
- apoptotic_eliminated

Rules:
- State evidence must cite supporting finding IDs, graph node/edge IDs, ToolUniverse artifact IDs, Medea evidence, or explicit missing/speculative evidence.
- Every state evidence record must set validation_needed to true because tumor behavior output is always human-review gated.
- If a state has no support IDs, set evidence_class exactly to "missing_speculative_evidence", keep all support lists empty, and set validation_needed to true.
- Transition hypotheses must cite supporting artifacts from the payload.
- Every transition hypothesis must set hypothesis_generating to true and validation_status to "needs_review".
- Transition supporting_artifacts must not cite the TumorBehaviorModelOutput artifact_id itself.
- Transition rationales must mention case-derived evidence terms from the payload.
- Use risk-ranked, monitor-for, treatment-pressure, and possible escape-route language.
- Do not generate transition probabilities, exact response probabilities, survival predictions, cure claims, or deterministic outcomes.
- If evidence does not support a transition, omit that transition or mark the missing evidence in limitations.
