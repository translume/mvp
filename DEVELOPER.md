# Developer Guide

## Architecture

Translume uses ports and adapters. Domain logic lives under `packages/translume-core`. Stable protocols live under `packages/translume-ports`. External systems and Harvard MIMS repos are isolated behind adapters under `packages/translume-adapters` or service wrappers under `services`.

## Dependency direction

Allowed:

```text
apps -> packages
services -> packages
adapters -> ports + clients + schemas
core -> schemas + ports
clients -> schemas
ports -> schemas only
schemas -> no internal package dependencies
```

Forbidden:

```text
core -> third_party
apps -> third_party
schemas -> third_party
```

## Harvard MIMS workflow

```bash
make vendor-repos
make audit-vendor-model-calls
make catalog-vendor-repos
```

Vendor repos are expected at:

```text
third_party/upstream/OptimusKG
third_party/upstream/ToolUniverse
third_party/upstream/Medea
```

Translume-specific behavior should be implemented in adapters, not by deeply modifying upstream source. Patches under `third_party/patches` are allowed only when provider injection cannot be achieved externally.

## Testing

```bash
make test
```

Tests intentionally focus on pure functions, structured schemas, provider boundaries, safety language, provenance, and the review-packet compiler path.

## OpenSearch persistence layer

The production workflow uses `OpenSearchVectorStore` from
`packages/translume-clients` as the real HTTP boundary to OpenSearch. Domain code
builds index specs and document batches in pure functions under
`packages/translume-core/src/translume_core/indexing`.

Important files:

```text
packages/translume-core/src/translume_core/indexing/index_specs.py
packages/translume-core/src/translume_core/indexing/documents.py
packages/translume-core/src/translume_core/indexing/persistence.py
packages/translume-clients/src/translume_clients/opensearch.py
scripts/init_opensearch.py
```

Runtime defaults:

```text
OPENSEARCH_URL=http://opensearch:9200
TRANSLUME_REQUIRE_OPENSEARCH=true
TRANSLUME_VECTOR_DIMENSION=384
```

The API constructs a real OpenSearch client and passes it into the workflow via
`TranslumeWorkflowProviders.vector_store`. If OpenSearch is required and the
store is not configured, the workflow fails explicitly instead of returning an
unpersisted packet.

## Postgres ledger/artifact metadata layer

The production workflow uses `PostgresLedgerStore` from `packages/translume-clients`
as the real durable metadata boundary. Domain code builds table specs and row
batches in pure functions under `packages/translume-core/src/translume_core/persistence`.

Important files:

```text
packages/translume-core/src/translume_core/persistence/postgres_schema.py
packages/translume-core/src/translume_core/persistence/postgres_records.py
packages/translume-core/src/translume_core/persistence/postgres_persistence.py
packages/translume-core/src/translume_core/persistence/ledger_events.py
packages/translume-clients/src/translume_clients/postgres.py
packages/translume-ports/src/translume_ports/ledger_store.py
scripts/init_postgres.py
```

Runtime defaults:

```text
POSTGRES_DSN=postgresql://translume:translume@postgres:5432/translume
POSTGRES_CONNECT_TIMEOUT_SECONDS=10
TRANSLUME_REQUIRE_POSTGRES=true
```

The API constructs a real Postgres client and passes it into the workflow through
`TranslumeWorkflowProviders.ledger_store`. If Postgres is required and the store
is not configured, the workflow fails explicitly instead of returning an
unpersisted packet. The implementation uses Psycopg 3, the current-generation
PostgreSQL adapter with asyncio support.

## Docling / Granite Docling integration

The MVP now treats layout-aware document extraction as a required production
boundary. The API constructs a `DoclingServiceClient` from `DOCLING_SERVICE_URL`
and the workflow runs Docling extraction plus a PyMuPDF baseline before section
chunking. If `TRANSLUME_REQUIRE_DOCLING=true`, missing or failing Docling
extraction fails explicitly instead of silently falling back to a lower-fidelity
path.

Docling is used only for document conversion: pages, blocks, tables, bounding
boxes, OCR/layout confidence, extraction warnings, and source text. It does not
produce clinical findings, mechanisms, validations, tumor-behavior hypotheses,
or evidence claims. Clinical artifacts are generated only after document chunks
are source-backed and indexed.

Relevant environment variables:

```text
DOCLING_SERVICE_URL=http://docling-service:8090
DOCLING_TIMEOUT_SECONDS=240
TRANSLUME_REQUIRE_DOCLING=true
DOCLING_EXTRACTION_METHOD=docling
```

Operational flow:

```text
PDF upload
→ raw file storage
→ Docling service `/extract`
→ DocumentExtractionOutput
→ PyMuPDF baseline extraction
→ extraction quality scoring
→ best extraction selection
→ section-aware chunks
→ OpenSearch/Postgres persistence
→ structured clinical compiler
```

## Real MIMS service execution

The production API no longer imports file-backed MIMS adapters. It calls the
MIMS services through `packages/translume-clients/src/translume_clients/mims.py`.
Those clients implement the existing GraphProvider, ToolProvider, and
ReasoningProvider contracts over HTTP.

Important files:

```text
packages/translume-clients/src/translume_clients/mims.py
services/optimuskg-service/src/optimuskg_service/main.py
services/tooluniverse-service/src/tooluniverse_service/main.py
services/medea-service/src/medea_service/main.py
configs/local/tooluniverse_workflows.json
third_party/vendor_repos.json
scripts/vendor_repos.py
```

MIMS runtime rules:

```text
1. OptimusKG service must import the vendored OptimusKG package and load real edge data.
2. ToolUniverse service must import the vendored ToolUniverse registry and execute configured tools.
3. Medea service must import the vendored Medea package and route model configuration to local vLLM.
4. Remote model provider environment variables are blocked.
5. Missing MIMS dependencies raise explicit errors.
6. No service fabricates successful evidence artifacts.
```

The default ToolUniverse workflow config includes `target_context` because the
Medea/ToolUniverse usage notes identify `load_disease_targets` as a ToolUniverse
registry tool. If your vendored ToolUniverse version uses different tool names,
update `configs/local/tooluniverse_workflows.json` rather than editing Translume
core code.

## Human validation-card workflow

Human validation is now part of the production MVP workflow. The core pure logic
lives in:

```text
packages/translume-core/src/translume_core/validation/review.py
```

API endpoints live in:

```text
apps/translume-api/src/translume_api/main.py
```

UI actions live in:

```text
apps/translume-ui/src/translume_ui/app.py
```

Persistence behavior:

```text
1. Fetch the current review packet from Postgres `review_packets`.
2. Require the target claim to exist.
3. Build a schema-valid `ValidationDecision`.
4. Apply it to the packet without mutating the original packet.
5. Append a `claim_validation_decision_recorded` ledger event.
6. Persist the updated packet to Postgres.
7. Re-index the updated packet into OpenSearch.
```

No validation-card endpoint creates claims or packets from partial state. Missing
sessions or claim IDs fail explicitly.


## Full-stack integration workflow

The final MVP hardening target is the real Docker/GPU/local-vLLM integration
path. Use it to validate the production workflow, not an isolated unit-test path.

Required environment:

```text
VLLM_MODEL=<real model id>
TRANSLUME_E2E_REPORT_PATH=<absolute path to real oncology report PDF>
```

Commands:

```bash
make preflight-full-stack
make integration-full-stack-up
make integration-full-stack
make integration-full-stack-logs
make integration-full-stack-down
```

The runner lives in `scripts/run_full_stack_integration.py`. It checks API,
Docling, OptimusKG, ToolUniverse, Medea, OpenSearch, Postgres, and vLLM, then
uploads the real report to `/api/v1/reports/process`, validates non-empty MVP
artifacts, applies a `needs_review` validation decision to one real claim, and
confirms the decision is persisted in the export.

## Live VM runtime validation

The live VM validation path is implemented in:

```text
scripts/live_vm_runtime_validate.py
packages/translume-core/src/translume_core/runtime_validation.py
configs/integration/live_vm_runtime_validation.json
```

The script executes real commands and writes both JSON and Markdown diagnostic
reports. It does not mock Docker, GPU, vLLM, Docling, MIMS services,
OpenSearch, Postgres, or API behavior.

Commands:

```bash
make live-vm-validate
make live-vm-validate-diagnostics
make live-vm-logs
```

The normal validation command stops at the first required failure to avoid
hiding the root cause. The diagnostics command continues through optional log
and system checks so an operator can inspect the failure surface.

The failure classifier is config-driven through
`configs/integration/live_vm_runtime_validation.json`. Keep repair guidance in
that config instead of hardcoding failure advice in Python logic.
