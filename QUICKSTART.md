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
OPTIMUSKG_EDGE_TABLE_PATH=
OPTIMUSKG_MODULE_NAMES=optimuskg,OptimusKG

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
