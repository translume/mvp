Generate BiomarkerWatchListOutput.

The artifact_id must be exactly:
{planned_artifact_id}

Payload JSON:
{payload_json}

Create a biomarker watch list from current molecular findings, treatment pressure, and resistance forecasts. Every item must include biomarker, alteration_type, why_watch, associated_treatment_pressure, preferred_test, trigger, priority, and source_artifact_ids. Use only preferred_test modalities from the schema. Each item must include source_artifact_ids or row-level unresolved_evidence; do not infer biomarkers without supplied evidence.
