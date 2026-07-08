Generate ClinicalNarrativeCompilerOutput for the Translume MVP.

The artifact_id must be exactly:
{planned_artifact_id}

Payload JSON:
{payload_json}

Write the narrative as a readable rendering of the structured packet only. Include a safety note. Do not introduce new genes, therapies, mechanisms, or claims absent from artifacts.
Use exact source-backed molecular phrases from the payload when naming findings.
Do not write vague alteration fragments such as "the mutation", "this amplification", "a variant", "that deletion", "identified variant", or "detected mutation"; write "the report finding" unless the exact source-backed phrase is present in the payload.
Avoid unexplained abbreviations in narrative prose; write "evidence ID" instead of "EID".
