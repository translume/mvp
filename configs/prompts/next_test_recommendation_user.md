Generate NextTestRecommendationsOutput.

The artifact_id must be exactly:
{planned_artifact_id}

Payload JSON:
{payload_json}

Recommend next test types from the supplied biomarker watch list, retesting triggers, current test limitations, and confirmatory testing gaps. Include test_type, timing, rationale, biomarkers_or_questions, result_that_would_change_management, limitations, source_artifact_ids, and priority. Do not invent tests or biomarkers absent from upstream evidence. Each recommendation must include source_artifact_ids or row-level unresolved_evidence; do not claim a result will improve outcomes.
