# Translume MVP Production Workflow

Translume is a local-first clinical output compiler that turns one oncology molecular report into reviewable tumor-behavior intelligence: source-backed findings, evidence-classified claims, mechanism paths, validation tests, human review controls, and provenance-backed ledger export.

This repository is a modular MVP workflow, not a clinical device. It intentionally does not produce treatment recommendations, outcome predictions, transition probabilities, or autonomous clinical decisions.

## Stack

- Python packages managed by `uv` workspaces.
- FastAPI API workflow for upload → extraction → review-packet export.
- Gradio UI cockpit that calls the production API path.
- OpenSearch retrieval/index substrate.
- Postgres ledger/artifact metadata.
- Local vLLM structured output model provider.
- Docling / Granite Docling document extraction boundary.
- Harvard MIMS repos vendored under `third_party/upstream` and wrapped by Translume ports/adapters.

## Quick development commands

```bash
uv sync --all-packages --dev
make test
make docker-config
```

## MVP invariant

Every clinical statement must be traceable to source report text, a structured artifact, graph/tool/Medea evidence, or a human validation decision.


## Production workflow status

The API endpoint `/api/v1/reports/process` now runs the real MVP compiler path:
raw PDF storage, PyMuPDF document extraction, section-aware chunking, deterministic
source-backed report extraction, entity normalization, strict MIMS evidence
provider integration, clinical artifact compilation, claim cards, narrative,
provenance, and review-packet export.

`TRANSLUME_REQUIRE_MIMS=true` is the default. Missing OptimusKG, ToolUniverse, or
Medea artifacts fail explicitly rather than silently fabricating evidence. Set
`TRANSLUME_REQUIRE_MIMS=false` only for local development of the core compiler.

See `docs/architecture/production_workflow.md` and
`docs/architecture/next_steps.md`.

## OpenSearch persistence

The `/api/v1/reports/process` workflow now requires a real OpenSearch store by
default through `TRANSLUME_REQUIRE_OPENSEARCH=true`. The workflow creates the MVP
indexes and persists document chunks, report findings, structured artifacts,
normalized entities, graph evidence, ToolUniverse outputs, Medea reasoning,
claim cards, artifact provenance, validation decisions, and ledger events.

Initialize indexes manually when needed:

```bash
make init-opensearch
```

For local unit tests without a running OpenSearch process, the persistence layer
is exercised through a recording store. The product path uses the HTTP
OpenSearch client in `translume_clients.opensearch.OpenSearchVectorStore`.

## Postgres ledger/artifact metadata

The report-processing workflow now requires durable Postgres metadata by default
through `TRANSLUME_REQUIRE_POSTGRES=true`. Postgres is the source of truth for
case/session metadata, source-file references, document chunk metadata,
structured artifact metadata, report findings, normalized entities, graph/tool
/Medea evidence metadata, evidence claims, provenance, validation decisions,
ledger events, and the full review-packet payload.

Initialize Postgres tables manually when needed:

```bash
make init-postgres
```

Runtime defaults:

```text
POSTGRES_DSN=postgresql://translume:translume@postgres:5432/translume
POSTGRES_CONNECT_TIMEOUT_SECONDS=10
TRANSLUME_REQUIRE_POSTGRES=true
```

OpenSearch remains the retrieval/evidence index. Postgres is the durable ledger
and artifact metadata store.

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

The MVP now calls MIMS services over HTTP instead of reading precomputed evidence
files from the API process. `translume-api` constructs service clients for:

```text
OPTIMUSKG_SERVICE_URL=http://optimuskg-service:8091
TOOLUNIVERSE_SERVICE_URL=http://tooluniverse-service:8092
MEDEA_SERVICE_URL=http://medea-service:8093
MIMS_TIMEOUT_SECONDS=240
TRANSLUME_TOOL_WORKFLOWS=target_context
```

The service containers load vendored Harvard repositories from:

```text
third_party/upstream/OptimusKG
third_party/upstream/ToolUniverse
third_party/upstream/Medea
```

Run:

```bash
make vendor-repos
make audit-vendor-model-calls
make catalog-vendor-repos
```

If GitHub is unavailable, place repo zip files as:

```text
third_party/zips/OptimusKG.zip
third_party/zips/ToolUniverse.zip
third_party/zips/Medea.zip
```

then run `make vendor-repos`. The script copies zip contents into the matching
`third_party/upstream/<Repo>` directory and writes manifest lock files.

Strict behavior remains: if a required MIMS repository, workflow config, graph
edge data, ToolUniverse registry, or Medea local-vLLM path is unavailable, the
workflow fails explicitly. It does not fabricate graph evidence, tool evidence,
or bounded reasoning.

## Human validation-card workflow

The MVP now exposes real validation-card actions. Claims generated by the review
packet compiler can be marked `validated`, `rejected`, or `needs_review` by a
human reviewer. Decisions are loaded from and persisted back to Postgres, then
the updated packet is re-indexed into OpenSearch. The UI does not update claims
optimistically and the API does not fabricate missing packets or claims.

Endpoints:

```text
GET  /api/v1/review-packets/{session_id}/validation-cards
POST /api/v1/review-packets/{session_id}/claims/{claim_id}/validation
GET  /api/v1/review-packets/{session_id}/export
```

Example validation payload:

```json
{
  "status": "validated",
  "reviewer_id": "reviewer@example.org",
  "reviewer_note": "Source and evidence context reviewed."
}
```

The validation decision updates the claim status, appends a durable validation
decision, appends a `claim_validation_decision_recorded` ledger event, persists
the full updated packet to Postgres, and re-indexes updated claim, validation,
ledger, and review-packet documents in OpenSearch.


## Full Docker/GPU/local-vLLM integration

The repository now includes a real full-stack integration runner for the MVP demo
path. It requires Docker Compose, a visible NVIDIA GPU when using the GPU profile,
a real configured `VLLM_MODEL`, vendored MIMS repositories, and a real oncology
report PDF at `TRANSLUME_E2E_REPORT_PATH`.

```bash
cp .env.example .env
# edit .env: set VLLM_MODEL and TRANSLUME_E2E_REPORT_PATH
make vendor-repos
make integration-full-stack
```

The integration does not use mocks or fabricated evidence. It validates service
health, OpenSearch indexes, Postgres schema, local vLLM structured outputs, real
report upload, MIMS-enriched review-packet content, validation-card persistence,
and review-packet export. See `docs/architecture/full_stack_integration.md`.

## Live VM validation

Use this after `.env` is configured and the MIMS repositories are vendored:

```bash
make live-vm-validate
```

For a longer failure report that continues through diagnostics after the first
required failure:

```bash
make live-vm-validate-diagnostics
```

Reports are written to:

```text
data/exports/runtime_diagnostics/
```

This is the production MVP deployability gate. It verifies the real Docker/GPU
stack, local vLLM structured outputs, Docling, OpenSearch, Postgres, MIMS
services, report upload processing, validation-card roundtrip, and export.
