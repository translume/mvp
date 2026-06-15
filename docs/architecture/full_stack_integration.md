# Full Docker/GPU/local-vLLM Integration

This is the non-mocked MVP demo validation path. It checks the real containerized
workflow required for the Translume promise: one oncology report becomes
structured, explainable, clinician-reviewable tumor-behavior intelligence with
source evidence, graph/tool/Medea enrichment, validation cards, OpenSearch
persistence, Postgres ledger metadata, and a provenance-backed export.

## What this integration validates

The integration runner requires real services:

```text
translume-api
postgres
opensearch
docling-service
optimuskg-service
tooluniverse-service
medea-service
vllm-clinical
```

It does not start mock services and it does not fabricate evidence. If Docling,
MIMS, OpenSearch, Postgres, or vLLM is missing, the run fails explicitly.

## Required setup

Copy and edit the environment file:

```bash
cp .env.example .env
```

Set at minimum:

```text
VLLM_MODEL=<real local or Hugging Face model id served by vLLM>
TRANSLUME_E2E_REPORT_PATH=<absolute path to a real oncology report PDF>
```

The clinical vLLM model may be any local/Hugging Face model your VM can serve
with vLLM structured outputs. The integration preflight rejects blank values and
placeholder identifiers such as `local-clinical-model`.

Vendor repos must exist:

```bash
make vendor-repos
make audit-vendor-model-calls
make catalog-vendor-repos
```

## Run the full integration

```bash
make integration-full-stack
```

This performs:

```text
preflight checks
Docker Compose GPU stack startup
service health checks
OpenSearch index initialization
Postgres schema initialization
vLLM structured-output check
real PDF upload through /api/v1/reports/process
review packet artifact validation
OpenSearch persistence validation
Postgres persistence validation
validation-card API round trip
review-packet export validation
```

## Failure policy

The integration fails when any required production behavior is missing:

```text
missing real report PDF
blank/placeholder VLLM_MODEL
missing vendored MIMS repos
MIMS service health not available
Docling unavailable
OpenSearch unavailable
Postgres unavailable
vLLM structured output unavailable
review packet missing graph evidence
review packet missing ToolUniverse output
review packet missing Medea reasoning
review packet missing tumor-behavior state evidence
review packet containing treatment-directing language
validation-card decision not persisted
```

## Useful commands

```bash
make preflight-full-stack
make integration-full-stack-up
make integration-full-stack
make integration-full-stack-logs
make integration-full-stack-down
```

## Why this matters

This is the demo-quality acceptance path. Passing unit tests alone does not prove
Translume delivers reviewable tumor-behavior intelligence. This integration
checks the real composed system: document extraction, retrieval, evidence
context, bounded reasoning, artifact compilation, human review, and durable
export.

## Live VM validation and failure repair report

`make live-vm-validate` is the deployability gate for the MVP. It runs the real
containerized stack and then executes the same full-stack integration used for
runtime validation.

The command writes a diagnostic report with:

```text
command result table
captured stdout/stderr
classified failure categories
operator next actions
JSON and Markdown output paths
```

Failure repair is intentionally explicit rather than automatic. The script does
not silently patch the system or downgrade requirements. It tells the operator
which real service failed and which real command to run next.
