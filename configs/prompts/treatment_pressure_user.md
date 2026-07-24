Generate TreatmentPressureMapOutput.

The artifact_id must be exactly:
{planned_artifact_id}

Payload JSON:
{payload_json}

For each ranked treatment option, explain what tumor pathway or target it pressures, why that fits the supplied biology, likely escape routes to monitor, biomarkers to watch, evidence_basis, source_artifact_ids, and confidence. Use risk/watch language, not deterministic predictions. Each row must include source_artifact_ids or row-level unresolved_evidence; evidence_basis must be source-backed or explicitly unresolved.
