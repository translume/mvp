Generate ReportExtractionOutput from this page-ordered retrieved source batch.

The artifact_id must be exactly:
{planned_artifact_id}

Rules:
- Extract only what this batch explicitly says.
- The full report is processed across multiple batches; do not treat omitted pages as absent evidence.
- Preserve disease, specimen, tumor percentage, molecular findings, negative findings, assay limitations, VUS/negative molecular sections, clinical-trial/treatment implication text, xR/RNA negative findings, RNA expression findings, and research-use-only signals when present.
- Do not infer biological mechanism, graph context, literature context, clinical action, treatment, prognosis, or tumor behavior.
- Use source_chunk_id, source_page, and source_text when the source is identifiable.
- source_text must quote or excerpt the retrieved source text.
- Every molecular finding must have needs_human_review=true.
- Unsupported or ambiguous findings must be omitted or marked low confidence.
- The output source_file_id must be the supplied source_file_id.

Payload JSON:
{payload_json}
