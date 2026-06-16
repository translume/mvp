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


## Gradio UI production launch

The Gradio Oncologist Cockpit now launches directly through:

```bash
python -m translume_ui.app
```

The UI container no longer attempts to run Gradio as an ASGI app through
Uvicorn. Inside Docker, `TRANSLUME_API_BASE_URL` is set to
`http://translume-api:8080` so the upload and validation actions call the real
FastAPI service over the Compose network. The UI health check performs a real
HTTP request to `http://localhost:7860` and the live VM validator now includes a
required `ui_health` command.

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
TRANSLUME_TOOL_WORKFLOWS=literature_validation,pathway_context,target_context,variant_context,trial_context_review
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

`make vendor-repos` is Git-only. It clones missing repositories or runs
`git pull --ff-only` for existing Git checkouts. If GitHub is unavailable,
`make vendor-bootstrap-from-zips` can unpack local zip archives for offline
inspection only, but zip-extracted folders are not production-updateable and
will fail `make vendor-status`.

Strict behavior remains: if a required MIMS repository, workflow config, OptimusKG parquet data, ToolUniverse engine/tool, or Medea local-vLLM path is unavailable, the workflow fails explicitly. It does not fabricate graph evidence, tool evidence, or bounded reasoning. ToolUniverse must cover the full MVP evidence set: `literature_validation`, `pathway_context`, `target_context`, `variant_context`, and `trial_context_review`.

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

## Harvard MIMS Vendor Update Workflow

Production/demo validation requires `third_party/upstream/Medea`, `third_party/upstream/OptimusKG`, and `third_party/upstream/ToolUniverse` to be real Git clones, not zip-extracted folders. Clone or fast-forward pull them with:

```bash
make vendor-repos
make vendor-status
```

Manual update commands are ordinary Git:

```bash
git -C third_party/upstream/Medea pull --ff-only
git -C third_party/upstream/OptimusKG pull --ff-only
git -C third_party/upstream/ToolUniverse pull --ff-only
```

Zip bootstrap is available only for offline inspection via `make vendor-bootstrap-from-zips`; it does not satisfy production status because it cannot support `git pull`. Translume-owned extension logic stays outside Harvard repos in `packages/translume-ports`, `packages/translume-adapters`, and `services/*-service`.

## PRIME_DIRECTIVES production gate

The project now includes a hard production/demo gate that enforces the non-negotiable runtime contract for Translume. The gate does not prove the full Docker/GPU stack works; it prevents the stack from starting or being validated in production/demo mode when required real dependencies are disabled, missing, zip-bootstrapped, or configured to bypass local-model execution.

Run it before live validation:

```bash
cp .env.example .env
# edit .env with real values, including VLLM_MODEL and service URLs
make vendor-repos
make vendor-status
make validate-prime-directives
```

The gate fails if MIMS repos are not real Git checkouts, if remote model-provider credentials are active, if required services such as MIMS, Docling, OpenSearch, or Postgres are disabled, if `VLLM_MODEL` is blank or placeholder-like, or if the UI Dockerfile no longer runs the real Gradio entrypoint.

This gate is intentionally strict. Passing unit tests does not imply MVP readiness; live Docker/GPU/vLLM/MIMS validation is still required.


## Early upload/session metadata persistence

Tutorial 4 added a strict auditability change: after a PDF is stored, Translume immediately persists the case session, source-file metadata, and upload ledger event to Postgres before document extraction or clinical artifact generation begins. The workflow also records started, succeeded, and failed ledger events for major stages. If a required stage fails, the error is not hidden; a failure event is recorded when Postgres is configured and the exception propagates to the caller.

This change does not make the full MVP runtime-validated. It makes failed and partial runs inspectable, which is required before moving more logic into OpenSearch retrieval and local-vLLM structured artifact generation.


## Early OpenSearch chunk indexing

Source-backed document chunks are now indexed into OpenSearch before report extraction and downstream artifact generation. In required OpenSearch mode, report extraction retrieves those chunks back from OpenSearch and will not continue if retrieval returns zero chunks. This makes OpenSearch part of the retrieval/evidence path rather than only a final packet persistence target. The current retrieval path is metadata/lexical scoped by case, session, and source file; vector/HNSW retrieval is not claimed as active until a real embedding generation path is implemented.


## Tutorial 6 — Convert clinical artifacts to local vLLM structured outputs

The production workflow now requires a configured local structured-output model provider for clinical artifact generation. Report extraction, molecular phenotype, molecular-fit matrix, mechanism Sankey, confirmatory testing, tumor-behavior model, claim evidence, and the final clinical narrative are generated through the local vLLM provider and validated against their Pydantic schemas. Deterministic code remains only for source alignment, validation, safety checks, provenance, ledger events, persistence, and service orchestration.

This does not prove Docker/GPU/vLLM runtime in this sandbox. In demo or production mode, `VLLM_MODEL` and `VLLM_BASE_URL` must point to a real local vLLM service configured for structured outputs. Missing local model configuration must fail loudly; no placeholder model output is allowed in the product path.

## Tutorial 7 — Source-grounded model-driven report extraction

Report extraction is now constrained to the local structured-output model path. The old deterministic extractor no longer returns clinical findings; it fails loudly with migration guidance. In the product path, report extraction consumes OpenSearch-retrieved document chunks, asks the local vLLM provider for a schema-valid `ReportExtractionOutput`, source-aligns every molecular finding back to retrieved chunks, forces human review flags, and downgrades unsupported findings to low confidence.

This preserves the first trust checkpoint: Translume must show what the report says before adding graph, literature, tool, Medea, or tumor-behavior interpretation. Missing source chunks, invalid structured output, unsafe text, or unsupported confident findings fail explicitly rather than producing a polished but ungrounded packet.


## Narrative containment enforcement

The production workflow now runs deterministic narrative containment after `ClinicalNarrativeCompilerOutput` is generated and before `ReviewPacketExport` is built. The validator checks that gene-like symbols, therapy-like terms, alteration/signal phrases, and declared `source_artifact_ids` are present in the structured source artifacts. Unsupported content raises an explicit error, records a workflow failure event, and prevents a polished review packet from being exported with unsupported clinical claims. Passing containment creates a `NarrativeContainmentReport` on the bundle and adds artifact-specific provenance for the containment validation artifact.

## Tutorial 8: narrative fact containment enforcement

The production workflow now validates the generated clinical narrative before review-packet export. `ClinicalNarrativeCompilerOutput` must be contained by the structured artifacts in the bundle: report extraction, normalized entities, graph evidence, ToolUniverse outputs, Medea reasoning, phenotype, matrix, Sankey, confirmatory tests, tumor-behavior model, claim cards, and provenance. Unsupported gene-like terms, therapy-like terms, alteration-like phrases, or unknown source artifact IDs fail loudly instead of being returned as a polished narrative. A passing narrative creates a `NarrativeContainmentReport` and containment provenance; a failing narrative records a workflow failure event and blocks export.


### OptimusKG graph context

Translume now requires OptimusKG graph context to come from the real OptimusKG Python client and its parquet graph tables. The production path does not read arbitrary CSV/JSON edge files as a substitute. Configure `OPTIMUSKG_CACHE_DIR`, `OPTIMUSKG_USE_LCC`, `OPTIMUSKG_MAX_EDGES`, and `OPTIMUSKG_FORCE_DOWNLOAD` as needed. Missing OptimusKG package/data fails loudly.
