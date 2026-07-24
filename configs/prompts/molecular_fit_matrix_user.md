Generate TherapyEvidenceMatrixOutput for the Translume MVP.

The artifact_id must be exactly:
{planned_artifact_id}

Payload JSON:
{payload_json}

Each row must include rank, molecular_fit, fit_label, why_from_omics, evidence_basis, limitations, required_validation, clinical_use, therapy_class, matched_biomarkers, resistance_risks, required_before_use_tests, confidence, and evidence_level.

Use clinical_use to categorize the evidence: approved_option, guideline_supported, off_label_rationale, trial_option, avoid_or_deprioritize, or insufficient_evidence. Do not use unsupported certainty language. If no before-use test is known from the payload, state what evidence is missing in required_before_use_tests or limitations rather than inventing a test.
