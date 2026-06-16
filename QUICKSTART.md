# Translume MVP Quickstart

This quickstart is only for bringing up the Translume MVP stack, configuring `.env`, running Docker, and using the Gradio app.

## 1. Prerequisites

Install these on the target VM:

```bash
nvidia-smi
docker --version
docker compose version
```

You need:

```text
Docker Engine
Docker Compose v2
NVIDIA driver visible through nvidia-smi
NVIDIA Container Toolkit configured for Docker GPU containers
A real local/Hugging Face model ID for VLLM_MODEL
A real oncology PDF report path for TRANSLUME_E2E_REPORT_PATH
```

## 2. Create `.env`

From the project root:

```bash
cp .env.example .env
nano .env
```

Use this template and replace the two required values:

```bash
TRANSLUME_ENV=local
TRANSLUME_STORAGE_ROOT=/data/uploads
TRANSLUME_ARTIFACT_ROOT=/data/artifacts

POSTGRES_DSN=postgresql://translume:translume@postgres:5432/translume
POSTGRES_PUBLIC_DSN=postgresql://translume:translume@localhost:5432/translume
POSTGRES_CONNECT_TIMEOUT_SECONDS=10
TRANSLUME_REQUIRE_POSTGRES=true

OPENSEARCH_URL=http://opensearch:9200
OPENSEARCH_PUBLIC_URL=http://localhost:9200
OPENSEARCH_TIMEOUT_SECONDS=30
TRANSLUME_REQUIRE_OPENSEARCH=true
TRANSLUME_VECTOR_DIMENSION=384

VLLM_BASE_URL=http://vllm-clinical:8000/v1
VLLM_PUBLIC_BASE_URL=http://localhost:8000/v1
VLLM_MODEL=<SET_A_REAL_MODEL_ID_HERE>

DOCLING_SERVICE_URL=http://docling-service:8090
DOCLING_PUBLIC_URL=http://localhost:8090
DOCLING_TIMEOUT_SECONDS=240
TRANSLUME_REQUIRE_DOCLING=true
DOCLING_EXTRACTION_METHOD=docling

OPTIMUSKG_SERVICE_URL=http://optimuskg-service:8091
OPTIMUSKG_PUBLIC_URL=http://localhost:8091
OPTIMUSKG_VENDOR_DIR=/app/third_party/upstream/OptimusKG
OPTIMUSKG_CACHE_DIR=/data/optimuskg_cache
OPTIMUSKG_USE_LCC=true
OPTIMUSKG_MAX_EDGES=500
OPTIMUSKG_FORCE_DOWNLOAD=false

TOOLUNIVERSE_SERVICE_URL=http://tooluniverse-service:8092
TOOLUNIVERSE_PUBLIC_URL=http://localhost:8092
TOOLUNIVERSE_VENDOR_DIR=/app/third_party/upstream/ToolUniverse
TOOLUNIVERSE_WORKFLOW_CONFIG=/app/configs/local/tooluniverse_workflows.json
TOOLUNIVERSE_MODULE_NAMES=tooluniverse

MEDEA_SERVICE_URL=http://medea-service:8093
MEDEA_PUBLIC_URL=http://localhost:8093
MEDEA_VENDOR_DIR=/app/third_party/upstream/Medea
MEDEA_MODULE_NAMES=medea

MIMS_TIMEOUT_SECONDS=240
TRANSLUME_REQUIRE_MIMS=true
TRANSLUME_TOOL_WORKFLOWS=target_context
BLOCK_REMOTE_MODEL_PROVIDERS=true

TRANSLUME_MAX_CHUNK_CHARS=2400
TRANSLUME_API_URL=http://localhost:8080
TRANSLUME_API_BASE_URL=http://translume-api:8080
TRANSLUME_UI_HOST=0.0.0.0
TRANSLUME_UI_PORT=7860
TRANSLUME_UI_URL=http://localhost:7860

TRANSLUME_E2E_REPORT_PATH=/absolute/path/to/real/oncology_report.pdf
TRANSLUME_E2E_REPORT_TYPE=NGS
```

`VLLM_MODEL` must not be blank, `mock`, `dummy`, `placeholder`, or `local-clinical-model`.

Example:

```bash
VLLM_MODEL=Qwen/Qwen2.5-7B-Instruct
```

Use a model your GPU can actually serve.

## 3. Vendor the Harvard MIMS repos

If the repos are already present under `third_party/upstream/`, run:

```bash
make catalog-vendor-repos
make audit-vendor-model-calls
```

If the repos are not present and the VM has internet access:

```bash
make vendor-repos
make catalog-vendor-repos
make audit-vendor-model-calls
```

The expected vendor directories are:

```text
third_party/upstream/OptimusKG
third_party/upstream/ToolUniverse
third_party/upstream/Medea
```

## 4. Preflight check

Run:

```bash
make preflight-full-stack
```

This checks:

```text
Docker
Docker Compose
GPU visibility
required .env values
real oncology PDF path
vendored MIMS repos
non-placeholder VLLM_MODEL
```

## 5. Start the full stack

Run:

```bash
make integration-full-stack-up
```

This starts:

```text
Postgres
OpenSearch
vLLM clinical model
vLLM Docling model
Docling service
OptimusKG service
ToolUniverse service
Medea service
Translume FastAPI
Translume Gradio UI
Translume worker
```

## 6. Initialize persistence

After containers are healthy, run:

```bash
make init-opensearch
make init-postgres
```

## 7. Run the full-stack integration test

Run:

```bash
make integration-full-stack
```

This uploads the PDF configured in `TRANSLUME_E2E_REPORT_PATH`, processes it through the MVP workflow, validates generated artifacts, checks OpenSearch and Postgres persistence, tests claim validation, and fetches the final review-packet export.


The Gradio container launches with `python -m translume_ui.app`. If you need to
check only the UI after the stack is running, use:

```bash
make check-ui-health
```

This command performs a real HTTP request to the running Gradio app. It does not
mock or fabricate UI readiness.

## 8. Open the Gradio app

Open:

```text
http://localhost:7860
```

If running on a remote VM, use the VM IP or SSH port forwarding:

```bash
ssh -L 7860:localhost:7860 -L 8080:localhost:8080 -L 9200:localhost:9200 user@your-vm
```

Then open:

```text
http://localhost:7860
```

## 9. Use the Gradio app

### Step 1 — Upload report

In the Upload panel:

```text
Select report type: NGS
Upload a real oncology molecular PDF
Click Process Report
```

### Step 2 — Review extracted findings

After processing, review:

```text
Disease / report context
Genes
Variants
Copy-number events
Expression signals
Negative findings
Assay limitations
Source page/source text
```

This is the first trust checkpoint: confirm Translume extracted what the report actually says.

### Step 3 — Review molecular-fit matrix

Review the matrix for:

```text
Molecular fit
Why from omics
Evidence basis
Limitations
Required validation
```

Rows are for expert review only. They are not treatment recommendations.

### Step 4 — Review mechanism Sankey

Use the Sankey to inspect:

```text
Finding → Mechanism → Molecular Fit → Validation Test
```

### Step 5 — Review tumor-behavior hypothesis

Review the tumor-behavior section for:

```text
Proliferative state evidence
Stress-adapted survival evidence
Plastic / dedifferentiated evidence
Dormant / quiescent uncertainty
Transition hypotheses
Validation needs
```

No probabilities, outcome predictions, or treatment directions should appear.

### Step 6 — Validate claims

In the validation-card panel:

```text
Choose a claim
Select validated, rejected, or needs_review
Add reviewer note
Submit validation
```

The decision is persisted to Postgres, re-indexed to OpenSearch, and added to the ledger.

### Step 7 — Export review packet

Click export/fetch review packet.

The export includes:

```text
raw file reference
document chunks
structured artifacts
OptimusKG graph evidence
ToolUniverse outputs
Medea reasoning
claim evidence cards
validation decisions
artifact provenance
ledger events
final narrative
```

## 10. Useful operational commands

Check logs:

```bash
make integration-full-stack-logs
```

Stop the stack:

```bash
make integration-full-stack-down
```

Run unit tests:

```bash
make test
```

Check Docker Compose config:

```bash
make docker-config
```

Check Docling health:

```bash
make docling-health
```

Direct API health check:

```bash
curl -fsS http://localhost:8080/health
```

Direct UI URL:

```text
http://localhost:7860
```

## 11. Direct API processing command

You can process a report without the UI:

```bash
curl -fsS -X POST http://localhost:8080/api/v1/reports/process \
  -F "report_type=NGS" \
  -F "file=@/absolute/path/to/real/oncology_report.pdf" \
  -o translume_review_packet.json
```

Fetch validation cards:

```bash
curl -fsS http://localhost:8080/api/v1/review-packets/<SESSION_ID>/validation-cards
```

Submit a validation decision:

```bash
curl -fsS -X POST http://localhost:8080/api/v1/review-packets/<SESSION_ID>/claims/<CLAIM_ID>/validation \
  -H "Content-Type: application/json" \
  -d '{"status":"needs_review","reviewer_note":"Needs clinician source review."}'
```

Export the review packet:

```bash
curl -fsS http://localhost:8080/api/v1/review-packets/<SESSION_ID>/export \
  -o translume_review_packet_export.json
```

## 11. Live VM validation and diagnostics

After the stack is configured, run the production runtime validation:

```bash
make live-vm-validate
```

This command performs the real deployment validation path:

```text
preflight → docker compose config → docker compose up → full-stack integration
```

It writes JSON and Markdown diagnostic reports under:

```text
data/exports/runtime_diagnostics/
```

If validation fails and you want all diagnostic commands to continue after the
first required failure, run:

```bash
make live-vm-validate-diagnostics
```

To inspect logs directly:

```bash
make live-vm-logs
```

The live validation does not fake service readiness. It fails if Docker, GPU,
vLLM, OpenSearch, Postgres, Docling, OptimusKG, ToolUniverse, Medea, upload
processing, validation-card roundtrip, or export persistence fail.

## Updating Harvard MIMS Repositories

Before running the production-style MVP stack, install or update the upstream Harvard MIMS repositories as real Git clones:

```bash
make vendor-repos
make vendor-status
```

To update manually:

```bash
git -C third_party/upstream/Medea pull --ff-only
git -C third_party/upstream/OptimusKG pull --ff-only
git -C third_party/upstream/ToolUniverse pull --ff-only
make vendor-status
```

`make vendor-status` must pass before live VM validation. Zip-extracted repositories are allowed only for offline inspection with `make vendor-bootstrap-from-zips`; they are not production-updateable and will fail vendor status.

## Validate production/demo readiness gate

Before starting the live VM validation, run the PRIME_DIRECTIVES gate:

```bash
cp .env.example .env
# edit .env; VLLM_MODEL must be a real model id, not blank
make vendor-repos
make vendor-status
make validate-prime-directives
```

If the command fails, fix the first reported error. Do not disable required services or replace missing MIMS repos with zip-extracted folders to make the gate pass. The required vendor update path is:

```bash
git -C third_party/upstream/Medea pull --ff-only
git -C third_party/upstream/OptimusKG pull --ff-only
git -C third_party/upstream/ToolUniverse pull --ff-only
```

Those commands only work after `make vendor-repos` has created real Git clones.


## Failure audit trail behavior

During report processing, Translume now records the raw upload, case session, source-file metadata, and upload ledger event before clinical processing begins. Major workflow stages write started, succeeded, and failed ledger events. If a live-stack run fails, inspect the Postgres ledger tables and `data/exports/runtime_diagnostics/` to see which real service or stage failed.


## Tutorial 6 — Convert clinical artifacts to local vLLM structured outputs

The production workflow now requires a configured local structured-output model provider for clinical artifact generation. Report extraction, molecular phenotype, molecular-fit matrix, mechanism Sankey, confirmatory testing, tumor-behavior model, claim evidence, and the final clinical narrative are generated through the local vLLM provider and validated against their Pydantic schemas. Deterministic code remains only for source alignment, validation, safety checks, provenance, ledger events, persistence, and service orchestration.

This does not prove Docker/GPU/vLLM runtime in this sandbox. In demo or production mode, `VLLM_MODEL` and `VLLM_BASE_URL` must point to a real local vLLM service configured for structured outputs. Missing local model configuration must fail loudly; no placeholder model output is allowed in the product path.

## Tutorial 8: narrative fact containment enforcement

The production workflow now validates the generated clinical narrative before review-packet export. `ClinicalNarrativeCompilerOutput` must be contained by the structured artifacts in the bundle: report extraction, normalized entities, graph evidence, ToolUniverse outputs, Medea reasoning, phenotype, matrix, Sankey, confirmatory tests, tumor-behavior model, claim cards, and provenance. Unsupported gene-like terms, therapy-like terms, alteration-like phrases, or unknown source artifact IDs fail loudly instead of being returned as a polished narrative. A passing narrative creates a `NarrativeContainmentReport` and containment provenance; a failing narrative records a workflow failure event and blocks export.

# OptimusKG real parquet client settings
OPTIMUSKG_USE_LCC=true
OPTIMUSKG_MAX_EDGES=500
OPTIMUSKG_FORCE_DOWNLOAD=false
OPTIMUSKG_CACHE_DIR=data/optimuskg_cache


## OptimusKG update and graph-data note

OptimusKG context now comes from the real OptimusKG Python client and parquet graph tables. Run `make vendor-repos` to clone/pull `third_party/upstream/OptimusKG`, then configure `OPTIMUSKG_CACHE_DIR` so the OptimusKG client can find or download its parquet files. Translume does not use generic CSV/JSON edge files as a substitute for OptimusKG.
