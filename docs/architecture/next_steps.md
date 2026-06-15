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
