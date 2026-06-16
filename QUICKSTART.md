# Translume MVP Quickstart

This file gives only the setup order, `.env` configuration, Docker/Make commands, Harvard MIMS update commands, and a short Gradio usage tutorial.

Translume is strict by design. In production/demo mode, missing Docker, GPU, vLLM, Docling, OpenSearch, Postgres, OptimusKG, ToolUniverse, Medea, or required configuration must fail loudly. Do not replace missing services with local fixtures or static JSON.

## 1. Install VM prerequisites

On the target GPU VM, confirm:

```bash
nvidia-smi
docker --version
docker compose version
git --version
```

You need Docker Engine, Docker Compose v2, NVIDIA drivers, NVIDIA Container Toolkit, GitHub access for the MIMS repos, a real local/Hugging Face model ID for `VLLM_MODEL`, and a real oncology PDF path for `TRANSLUME_E2E_REPORT_PATH`.

## 2. Create `.env`

```bash
cp .env.example .env
nano .env
```

Set at least these values:

```bash
TRANSLUME_ENV=local
TRANSLUME_ENFORCE_PRIME_DIRECTIVES=false

POSTGRES_DSN=postgresql://translume:translume@postgres:5432/translume
POSTGRES_PUBLIC_DSN=postgresql://translume:translume@localhost:5432/translume
TRANSLUME_REQUIRE_POSTGRES=true

OPENSEARCH_URL=http://opensearch:9200
OPENSEARCH_PUBLIC_URL=http://localhost:9200
TRANSLUME_REQUIRE_OPENSEARCH=true

VLLM_BASE_URL=http://vllm-clinical:8000/v1
VLLM_PUBLIC_BASE_URL=http://localhost:8000/v1
VLLM_MODEL=<SET_A_REAL_MODEL_ID_HERE>
TRANSLUME_REQUIRE_LOCAL_VLLM=true

DOCLING_SERVICE_URL=http://docling-service:8090
DOCLING_PUBLIC_URL=http://localhost:8090
TRANSLUME_REQUIRE_DOCLING=true

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

TRANSLUME_REQUIRE_MIMS=true
TRANSLUME_TOOL_WORKFLOWS=literature_validation,pathway_context,target_context,variant_context,trial_context_review
MIMS_TIMEOUT_SECONDS=240
BLOCK_REMOTE_MODEL_PROVIDERS=true

TRANSLUME_API_URL=http://localhost:8080
TRANSLUME_API_BASE_URL=http://translume-api:8080
TRANSLUME_UI_HOST=0.0.0.0
TRANSLUME_UI_PORT=7860
TRANSLUME_UI_URL=http://localhost:7860

TRANSLUME_E2E_REPORT_PATH=/absolute/path/to/real/oncology_report.pdf
TRANSLUME_E2E_REPORT_TYPE=NGS
```

`VLLM_MODEL` must be a real model ID your GPU can serve. It must not be blank, `mock`, `dummy`, `placeholder`, `test`, or `local-clinical-model`.

## 3. Pull the Harvard MIMS repos as real Git clones

Assume the third-party repos are not present. From the project root:

```bash
make vendor-repos
make vendor-status
make audit-vendor-model-calls
make catalog-vendor-repos
```

Expected directories:

```text
third_party/upstream/Medea
third_party/upstream/OptimusKG
third_party/upstream/ToolUniverse
```

These must be real Git repositories with `.git` directories. Zip-extracted folders are only for offline inspection through `make vendor-bootstrap-from-zips`; they are not production-updateable and fail `make vendor-status`.

## 4. Update Harvard MIMS repos later

To safely pull updates:

```bash
git -C third_party/upstream/Medea pull --ff-only
git -C third_party/upstream/OptimusKG pull --ff-only
git -C third_party/upstream/ToolUniverse pull --ff-only
make vendor-status
make audit-vendor-model-calls
make test
```

If an upstream change breaks Translume, update Translume adapters, not the MIMS repos.

## 5. How Translume extends MIMS without modifying MIMS code

The MIMS repos stay clean under `third_party/upstream/`. Translume does not scatter changes through Medea, OptimusKG, or ToolUniverse. Instead, Translume owns stable ports and adapters:

```text
packages/translume-ports       # stable Translume contracts
packages/translume-adapters    # wrappers around MIMS and local vLLM behavior
services/*-service             # isolated service containers for MIMS runtime
```

The pattern is:

```text
Translume port → Translume adapter → real MIMS repo/API/client → structured Translume artifact
```

This lets MIMS repos be updated with `git pull --ff-only`, while Translume keeps control over local vLLM routing, remote provider blocking, schema validation, evidence normalization, provenance, and human review. If a MIMS repo tries to use a remote model API, the Translume service must block it or fail loudly.

## 6. Validate production/demo gate

After `.env` and vendor repos are configured:

```bash
make validate-prime-directives
```

If this fails, fix the first reported issue. Do not disable required services to make it pass.

## 7. Start the stack

```bash
make integration-full-stack-up
```

This starts Postgres, OpenSearch, vLLM, Docling, OptimusKG service, ToolUniverse service, Medea service, FastAPI, Gradio, and the worker.

Initialize persistence after the containers are healthy:

```bash
make init-opensearch
make init-postgres
```

## 8. Run full-stack validation

```bash
make integration-full-stack
```

For production-style runtime validation and diagnostics:

```bash
make live-vm-validate
```

If you need diagnostics to continue after the first failure:

```bash
make live-vm-validate-diagnostics
```

Inspect logs:

```bash
make live-vm-logs
```

## 9. Open the Gradio app

Local VM:

```text
http://localhost:7860
```

Remote VM through SSH port forwarding:

```bash
ssh -L 7860:localhost:7860 -L 8080:localhost:8080 -L 9200:localhost:9200 user@your-vm
```

Then open:

```text
http://localhost:7860
```

## 10. Use the Gradio app

1. Select report type, for example `NGS`.
2. Upload a real oncology molecular PDF.
3. Click process.
4. Review extracted findings first: disease, genes, variants, copy-number events, expression signals, negative findings, limitations, source page, and source text.
5. Review normalized entities and MIMS evidence context.
6. Review molecular phenotype, molecular-fit matrix, mechanism Sankey, confirmatory tests, tumor-behavior hypotheses, and evidence-classified claims.
7. Validate, reject, or mark claims as `needs_review`.
8. Export the review packet.

The review packet is for clinician review and translational research support only. It must not produce treatment recommendations, outcome predictions, or unsupported clinical claims.

## 11. API commands

Process a report:

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

Export the packet:

```bash
curl -fsS http://localhost:8080/api/v1/review-packets/<SESSION_ID>/export \
  -o translume_review_packet_export.json
```

## 12. Stop the stack

```bash
make integration-full-stack-down
```
