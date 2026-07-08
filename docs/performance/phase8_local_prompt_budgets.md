# Phase 8 local prompt budgeting

The decision-brief workflow is intentionally split into small staged prompts for local vLLM deployment on an 8x L4 GPU profile. Each stage receives only the evidence needed for one clinical task and records prompt-budget metadata in its payload.

The backend uses stage-specific character budgets for current tumor state, actionable biology, treatment options, treatment pressure, resistance forecast, biomarker watch list, re-testing triggers, next-test recommendations, and the five-question translational assessment. If a packet exceeds its local budget, it is compacted deterministically by capping long text and evidence lists. If it still exceeds budget, low-priority graph/tool details are omitted and the prompt tells the model to treat omitted context as unresolved rather than absent.

This keeps the local model workload bounded while preserving the workflow design: many small prompts, REST/provider calls for MIMS evidence, then deterministic aggregation into the final report.
