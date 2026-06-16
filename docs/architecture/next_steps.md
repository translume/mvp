# Next Implementation Steps

1. Project structure and ports/adapters architecture — done.
2. Real PDF extraction + source chunking — done.
3. Real report extraction + entity normalization — done.
4. Strict MIMS evidence boundary — done.
5. Artifact compiler path — done.
6. API + UI entrypoint — done.
7. OpenSearch persistence — done.
8. Postgres ledger/artifact metadata — done.
9. Real Docling/Granite Docling service integration — done.
10. Real MIMS service execution from vendored repos — done.
11. Validation-card endpoints/UI actions — done.
12. Full Docker/GPU/local-vLLM integration test — next.

## Current production behavior

The report-processing workflow requires real service boundaries for OpenSearch,
Postgres, Docling, OptimusKG, ToolUniverse, and Medea when strict runtime flags
remain enabled. MIMS evidence is no longer loaded from local precomputed files
inside the API process.

The validation workflow now requires a previously persisted review packet in
Postgres. Claim decisions are applied to real claim cards, persisted to Postgres,
re-indexed into OpenSearch, and appended to the ledger. Missing sessions or
claims fail explicitly.

## Next step

Run the full Docker/GPU/local-vLLM integration test path on a VM with Docker and
GPU access. This should validate container startup, OpenSearch/Postgres schema
initialization, Docling service extraction, MIMS service execution from vendored
repos, report processing, claim validation, and final review-packet export.


## Current step: full Docker/GPU/local-vLLM integration test

Completed in this step:

```text
full-stack requirements config
preflight script
real integration runner
Docker Compose GPU/vLLM command hardening
service health checks
Make targets for full-stack validation
integration contract tests
```

Next step after this: run the integration on a real GPU VM with a real oncology
PDF and fix any runtime-specific failures from Docker, vLLM, Docling, OptimusKG,
ToolUniverse, or Medea.


## PRIME_DIRECTIVES repair tracker

1. Repair 1 — Gradio production launch path — done.
2. Repair 2 — Replace zip-vendored MIMS folders with real git clones — done.
3. Repair 3 — Add PRIME_DIRECTIVES production config gate — done.
4. Repair 4 — Persist upload/session metadata before clinical processing — done.
5. Repair 5 — Move OpenSearch chunk indexing before artifact generation — done.
6. Repair 6 — Convert clinical artifact generation to local vLLM structured outputs — done.
7. Repair 7 — Make report extraction source-grounded and model-driven — done.
8. Repair 8 — Enforce narrative containment in the production path — done.
9. Repair 9 — Replace generic OptimusKG edge-file loading with true OptimusKG usage — next.
10. Repair 10 — Configure all required ToolUniverse workflows — pending.
11. Repair 11 — Prove Medea local runtime and remote-provider blocking — pending.
12. Repair 12 — Generate tumor behavior dynamically from evidence — pending.
13. Repair 13 — Add artifact-specific provenance everywhere — pending.
14. Repair 14 — Decide and enforce vector retrieval scope — pending.
15. Repair 15 — Render real clinical artifact panels in the UI — pending.
16. Repair 16 — Run live VM validation and repair runtime failures — pending.

The current repair removed the broken Uvicorn UI launch path and added a real
Gradio module entrypoint plus a live UI health check.

The current repair split vendor management into production Git commands and
offline zip bootstrap. Production and live validation now require real Git
checkouts under `third_party/upstream`; zip-extracted folders fail vendor
status.

## Tutorial 3 completed: PRIME_DIRECTIVES production gate

A production/demo gate now fails loudly when runtime configuration would violate PRIME_DIRECTIVES. It validates required real services, MIMS Git checkouts, local-vLLM configuration, remote-provider blocking, ToolUniverse workflow presence, and the Gradio Docker entrypoint. The gate is used by `make validate-prime-directives`, API startup in production/demo/enforced mode, and live VM runtime validation.

Next repair remains Tutorial 4: persist upload/session metadata before clinical processing so failed runs still leave a durable audit trail.


## Tutorial 4 completed: early upload/session metadata persistence

The workflow now persists the case session, source-file metadata, and initial upload ledger event to Postgres immediately after the raw PDF is stored and before document extraction or clinical processing begins. Each major workflow stage now records started, succeeded, and failed ledger events, and failures are persisted when a ledger store is configured. This strengthens auditability by ensuring a failed Docling, MIMS, OpenSearch, vLLM, or compiler stage leaves a durable trace instead of disappearing behind an incomplete or polished partial packet.

Next repair is Tutorial 5: move OpenSearch chunk indexing earlier in the workflow so report chunks become the retrieval substrate before artifact generation.


## Tutorial 5 completed: early OpenSearch chunk indexing

The workflow now indexes source-backed document chunks into OpenSearch immediately after document extraction, section detection, and chunk construction. Report extraction no longer consumes only the in-memory chunk list when OpenSearch is required; it retrieves the indexed chunks back from OpenSearch before generating the report extraction artifact. If OpenSearch is required and chunk indexing or retrieval fails, the workflow fails loudly, records stage failure events, and does not continue with a polished review packet. Retrieval is currently metadata/lexical scoped by case, session, and source file; vector/HNSW retrieval is not claimed as active until real embeddings are generated and indexed.

Next repair is Tutorial 6: convert clinical artifact generation to local vLLM structured outputs so report extraction, phenotype, matrix, Sankey, confirmatory testing, tumor behavior, claims, and narrative are schema-constrained model artifacts rather than deterministic clinical compiler outputs.


## Tutorial 6 — Convert clinical artifacts to local vLLM structured outputs

The production workflow now requires a configured local structured-output model provider for clinical artifact generation. Report extraction, molecular phenotype, molecular-fit matrix, mechanism Sankey, confirmatory testing, tumor-behavior model, claim evidence, and the final clinical narrative are generated through the local vLLM provider and validated against their Pydantic schemas. Deterministic code remains only for source alignment, validation, safety checks, provenance, ledger events, persistence, and service orchestration.

This does not prove Docker/GPU/vLLM runtime in this sandbox. In demo or production mode, `VLLM_MODEL` and `VLLM_BASE_URL` must point to a real local vLLM service configured for structured outputs. Missing local model configuration must fail loudly; no placeholder model output is allowed in the product path.

## Tutorial 7 completed: source-grounded model-driven report extraction

Report extraction is now explicitly source-grounded and model-driven. The legacy deterministic report extraction function fails loudly if called, and the production path uses `generate_report_extraction_with_model` with OpenSearch-retrieved chunks, local vLLM structured output, schema validation, source alignment, and grounding validation. The report extraction prompt now requires source_chunk_id, source_page, and source_text when a source is identifiable and forbids graph, literature, treatment, and tumor-behavior inference at the extraction stage. Unsupported model-produced findings are downgraded to low confidence and kept human-reviewable instead of being presented as confident patient-specific facts.

Tutorial 8 is now complete: the production workflow validates the final clinical narrative against the structured source bundle before review-packet export. Unsupported genes, therapy-like terms, alteration phrases, or source artifact references fail loudly instead of being returned as polished narrative text. The containment report is stored as a structured artifact on the bundle and receives its own provenance record so the export can show that narrative containment was checked.

Next repair is Tutorial 9: replace generic OptimusKG edge-file loading with real OptimusKG package/data usage so graph evidence comes from the actual MIMS repository path.


## Tutorial 8 completed: narrative fact containment enforcement

The production workflow now validates `ClinicalNarrativeCompilerOutput` before packet export and persistence. The containment validator checks that gene-like, therapy-like, alteration-like, and source-artifact references in the narrative are present in the structured artifact bundle; unsupported content raises a hard failure and records a `narrative_fact_containment_failed` ledger event through the existing workflow stage machinery. Successful containment generates a `NarrativeContainmentReport`, adds deterministic containment provenance, stores the report in the review packet, and indexes it with the rest of the packet. This keeps the final narrative as a readable rendering of source-backed structured artifacts rather than a freeform chatbot answer.

Next repair is Tutorial 9: replace generic OptimusKG edge-file loading with true OptimusKG package/data usage so graph evidence comes from the actual MIMS repository path.


## Tutorial 8 — Replace generic OptimusKG edge-file loading with true OptimusKG usage

Code now routes OptimusKG context through the real OptimusKG Python client and parquet tables using Polars. Generic CSV/JSON/JSONL edge discovery is removed from the production path. Runtime still requires a real OptimusKG git checkout and available OptimusKG cache/download access; Docker/VM validation remains required.
