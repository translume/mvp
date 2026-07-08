Generate RetestingTriggersOutput.

The artifact_id must be exactly:
{planned_artifact_id}

Payload JSON:
{payload_json}

Create event-based re-testing triggers. Include radiographic progression, mixed response or oligoprogression, rapid progression on targeted therapy, rising tumor markers, new metastatic site, before switching systemic therapy, ctDNA-negative progression, and suspected transformation only when relevant to supplied evidence or monitoring needs. For each trigger include recommended_test, rationale, what_result_changes, urgency, and source_artifact_ids. Each trigger must include source_artifact_ids or row-level unresolved_evidence; do not create a trigger unless the upstream context or unresolved evidence justifies it.
