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

The default ToolUniverse workflow config includes `literature_validation`, `pathway_context`, `target_context`, `variant_context`, and `trial_context_review`. Each workflow maps to named ToolUniverse tools in `configs/local/tooluniverse_workflows.json`; the ToolUniverse service loads those tools through the real vendored `ToolUniverse` runtime and fails if a configured tool cannot be loaded or executed. If an upstream ToolUniverse update renames a tool, update the workflow configuration or Translume adapter mapping rather than editing the Harvard MIMS repository directly.


## Gradio UI production launch

The UI is a Gradio application, not an ASGI application. The production Docker
entrypoint is:

```bash
python -m translume_ui.app
```

Do not run `uvicorn translume_ui.app:app`; the module does not expose a FastAPI
ASGI app. Runtime configuration is validated by `api_base_url_from_environment`
and `ui_server_config_from_environment` in
`apps/translume-ui/src/translume_ui/app.py`. Docker Compose wires the UI to the
internal FastAPI service with:

```text
TRANSLUME_API_BASE_URL=http://translume-api:8080
TRANSLUME_UI_HOST=0.0.0.0
TRANSLUME_UI_PORT=7860
```

The live VM validation path runs `scripts/check_ui_health.py` after container
startup to prove the Gradio app is actually reachable.

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

## Vendor Repository Management

The Harvard MIMS repositories must remain clean upstream Git checkouts in `third_party/upstream/`. This keeps them updateable with `git pull --ff-only` while Translume-specific behavior lives in ports, adapters, and service wrappers.

Commands:

| Command | Purpose |
|---|---|
| `make vendor-repos` | Clone or fast-forward pull the configured upstream Git repos. |
| `make vendor-status` | Fail unless every upstream repo is a real, clean Git checkout with the configured origin. |
| `make vendor-bootstrap-from-zips` | Offline source inspection only; does not satisfy production validation. |

Production and live-VM validation fail if any MIMS repo is zip-extracted or missing `.git`. Do not place Translume runtime logic inside `third_party/upstream/*`; add integration behavior through `packages/translume-adapters` and stable contracts in `packages/translume-ports`.

## PRIME_DIRECTIVES production config gate

Tutorial 3 added the production config gate in `translume_core.prime_directives`. It is wired into API startup for production/demo/enforced mode and into full-stack preflight. The gate is inactive for ordinary local development unless `TRANSLUME_ENFORCE_PRIME_DIRECTIVES=true` or `--force` is used.

Key files:

```text
packages/translume-core/src/translume_core/prime_directives/gate.py
scripts/validate_prime_directives.py
configs/integration/live_vm_runtime_validation.json
apps/translume-api/src/translume_api/main.py
```

Run:

```bash
make validate-prime-directives
```

The command writes diagnostics to:

```text
data/exports/runtime_diagnostics/prime_directives_gate.json
data/exports/runtime_diagnostics/prime_directives_gate.md
```

The gate checks that production/demo mode cannot silently run without required real services, real MIMS Git clones, local-vLLM routing, remote-provider blocking, and the correct Gradio entrypoint. Do not weaken this gate to make demos pass; repair the underlying dependency or configuration.


## Early upload/session metadata persistence

Tutorial 4 added a strict auditability change: after a PDF is stored, Translume immediately persists the case session, source-file metadata, and upload ledger event to Postgres before document extraction or clinical artifact generation begins. The workflow also records started, succeeded, and failed ledger events for major stages. If a required stage fails, the error is not hidden; a failure event is recorded when Postgres is configured and the exception propagates to the caller.

This change does not make the full MVP runtime-validated. It makes failed and partial runs inspectable, which is required before moving more logic into OpenSearch retrieval and local-vLLM structured artifact generation.


## Early OpenSearch chunk indexing

Source-backed document chunks are now indexed into OpenSearch before report extraction and downstream artifact generation. In required OpenSearch mode, report extraction retrieves those chunks back from OpenSearch and will not continue if retrieval returns zero chunks. This makes OpenSearch part of the retrieval/evidence path rather than only a final packet persistence target. The current retrieval path is metadata/lexical scoped by case, session, and source file; vector/HNSW retrieval is not claimed as active until a real embedding generation path is implemented.


## Tutorial 6 — Convert clinical artifacts to local vLLM structured outputs

The production workflow now requires a configured local structured-output model provider for clinical artifact generation. Report extraction, molecular phenotype, molecular-fit matrix, mechanism Sankey, confirmatory testing, tumor-behavior model, claim evidence, and the final clinical narrative are generated through the local vLLM provider and validated against their Pydantic schemas. Deterministic code remains only for source alignment, validation, safety checks, provenance, ledger events, persistence, and service orchestration.

This does not prove Docker/GPU/vLLM runtime in this sandbox. In demo or production mode, `VLLM_MODEL` and `VLLM_BASE_URL` must point to a real local vLLM service configured for structured outputs. Missing local model configuration must fail loudly; no placeholder model output is allowed in the product path.

## Tutorial 7 — Source-grounded model-driven report extraction

The production report extraction path is `generate_report_extraction_with_model` in `translume_core.compiler.structured_model_artifacts`. It requires retrieved OpenSearch chunks and a local structured-output model provider. The legacy deterministic function `generate_report_extraction_from_chunks` in `translume_core.compiler.report_extraction` now raises `LegacyReportExtractionDisabledError` and must not be used in runtime code.

The source-grounding contract is enforced after schema validation. Each molecular finding is matched back to retrieved chunks by source_chunk_id, quoted source text, gene token, alteration terms, and alteration type. Findings that cannot be supported by a retrieved chunk are retained only as low-confidence human-review items. The extraction stage must not introduce graph, literature, treatment, or tumor-behavior inference.

Tests covering this behavior live in `tests/unit/test_source_grounded_report_extraction.py`.


## Narrative containment enforcement

The production workflow now runs deterministic narrative containment after `ClinicalNarrativeCompilerOutput` is generated and before `ReviewPacketExport` is built. The validator checks that gene-like symbols, therapy-like terms, alteration/signal phrases, and declared `source_artifact_ids` are present in the structured source artifacts. Unsupported content raises an explicit error, records a workflow failure event, and prevents a polished review packet from being exported with unsupported clinical claims. Passing containment creates a `NarrativeContainmentReport` on the bundle and adds artifact-specific provenance for the containment validation artifact.

## Tutorial 8: narrative fact containment enforcement

The production workflow now validates the generated clinical narrative before review-packet export. `ClinicalNarrativeCompilerOutput` must be contained by the structured artifacts in the bundle: report extraction, normalized entities, graph evidence, ToolUniverse outputs, Medea reasoning, phenotype, matrix, Sankey, confirmatory tests, tumor-behavior model, claim cards, and provenance. Unsupported gene-like terms, therapy-like terms, alteration-like phrases, or unknown source artifact IDs fail loudly instead of being returned as a polished narrative. A passing narrative creates a `NarrativeContainmentReport` and containment provenance; a failing narrative records a workflow failure event and blocks export.


### OptimusKG graph context

Translume now requires OptimusKG graph context to come from the real OptimusKG Python client and its parquet graph tables. The production path does not read arbitrary CSV/JSON edge files as a substitute. Configure `OPTIMUSKG_CACHE_DIR`, `OPTIMUSKG_USE_LCC`, `OPTIMUSKG_MAX_EDGES`, and `OPTIMUSKG_FORCE_DOWNLOAD` as needed. Missing OptimusKG package/data fails loudly.


## ToolUniverse workflow coverage

The default ToolUniverse workflow config includes `literature_validation`, `pathway_context`, `target_context`, `variant_context`, and `trial_context_review`. Each workflow maps to explicit ToolUniverse tool names and dynamic arguments derived from normalized entities and graph evidence. If your vendored ToolUniverse version changes tool names or parameters, update `configs/local/tooluniverse_workflows.json` and rerun `make validate-prime-directives`, `make vendor-status`, and `make test`; do not edit Translume core compiler code or the upstream ToolUniverse repo.
