Generate TranslationalAssessmentOutput.

The artifact_id must be exactly:
{planned_artifact_id}

Payload JSON:
{payload_json}

Answer the five translational MVP questions exactly once each:
1. target_relevance — Is the target actually relevant to this tumor's behavior?
2. biomarker_evidence — Does the biomarker evidence support action, or is it weak/incomplete?
3. resistance_mechanisms — Are resistance mechanisms already present or likely to emerge?
4. patient_population_alignment — Is the patient population aligned with the evidence behind the treatment?
5. evidence_resolution — What evidence is strong, what is unresolved, and what needs validation next?

Every question answer must include question_key, question, answer, status, evidence_strength, supporting_evidence, unresolved_evidence, validation_next, source_artifact_ids, and confidence. Use patient_population_alignment as unresolved unless the supplied evidence explicitly contains enough patient-context and evidence-population context to compare tumor type, disease setting, line of therapy, prior treatment, biomarker definition, and assay context. Do not resolve dose, exposure, toxicity, or therapeutic window in this MVP; if that context matters and is absent, surface it in evidence_resolution unresolved_evidence.
