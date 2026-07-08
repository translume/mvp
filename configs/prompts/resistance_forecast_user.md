Generate ResistanceForecastOutput.

The artifact_id must be exactly:
{planned_artifact_id}

Payload JSON:
{payload_json}

Forecast evidence-grounded resistance or escape routes from the treatment pressure map, tumor behavior model, graph context, ToolUniverse context, and Medea reasoning. Use only escape_route categories from the schema. For every item include description, associated_treatment_pressure, supporting_evidence, biomarkers_to_monitor, source_artifact_ids, and confidence. Each row must include source_artifact_ids or row-level unresolved_evidence; supporting_evidence must be source-backed or explicitly unresolved.
