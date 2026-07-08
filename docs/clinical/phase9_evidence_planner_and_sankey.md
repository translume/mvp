# Phase 9 — Long NGS Evidence Planner, Population Gate, and Therapy-Escape Sankey

This phase hardens the Translume MVP around long NGS reports and the five-question oncologist report UI.

## Long-report extraction

Report extraction now processes all retrieved source chunks in bounded, page-ordered batches instead of sending only the first prompt window. Each batch asks the model to extract only from that batch; the compiler then deterministically merges the batch outputs, deduplicates molecular findings, preserves negative/RNA findings and assay caveats, and revalidates source grounding against the complete retrieved report.

The extraction prompt explicitly preserves clinically critical NGS sections: genomic variants, variant details, biologically relevant variants, therapy implications, clinical trials, immunotherapy markers, xR/RNA negative findings, RNA expression signals, assay limitations, and research-use-only disclaimers.

## Patient-population alignment gate

Patient-population alignment is now enforced after the model stage. It remains unresolved unless the evidence context contains enough information to compare the patient against the treatment evidence cohort: tumor type, disease setting, line of therapy, prior therapy, biomarker definition, assay/specimen context, and cohort or trial eligibility context.

This prevents the UI from implying that evidence from a different tumor population transfers cleanly to the uploaded case.

## Evidence sentence map

The decision brief now carries a backend evidence sentence map. Each evidence atom has a clinician-readable label such as Report finding, Clinical trial criterion, Graph context, Hypothesis only, Missing matched normal, RNA/xR negative finding, or RNA research-use-only caveat. The UI displays labels, statements, excerpts, and clinical relevance without exposing internal IDs.

## Explicit therapy-escape Sankey

The Sankey now uses explicit decision-brief paths rather than inferred legacy mechanism rows. Each path is represented as:

therapy or drug → molecular target/pathway → predicted tumor behavior state → escape/recombination pathway → monitoring timing

The compiler resolves actual drug or trial-agent names from report/tool evidence when available. If no actual agent is found, the row is marked unresolved and points to the recent therapy-agent backfill workflow for review.

## Recent therapy-agent backfill

ToolUniverse includes `recent_therapy_agent_backfill_context`, which queries recent PubMed-style evidence and clinical-trial search context for actual drugs or trial agents related to the disease, genes, therapy-pressure context, and graph evidence. The PubMed query includes a date-publication filter covering approximately the prior 18 months.
