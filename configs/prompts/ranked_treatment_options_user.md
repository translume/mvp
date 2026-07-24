Generate RankedTreatmentOptionsOutput for clinician review.

The artifact_id must be exactly:
{planned_artifact_id}

Payload JSON:
{payload_json}

Rules:
- Rank treatment options only when supported by report, graph, tool, guideline, trial, or upstream staged evidence.
- Prefer actual drugs or clinical-trial agents when supplied by the treatment implication, clinical trial, guideline, or recent therapy-agent backfill context.
- If only a class, pathway strategy, or trial category is supported, keep it as a category but mark unresolved_evidence with the missing actual drug/trial-agent gap.
- Clearly distinguish approved_option, guideline_supported, off_label_rationale, trial_option, avoid_or_deprioritize, and insufficient_evidence.
- Include matched_biomarkers, why_it_fits, evidence_level, resistance_risks, required_before_use_tests, limitations, source_artifact_ids, unresolved_evidence, and confidence.
- Do not claim certain response, cure, survival benefit, or deterministic outcome.
