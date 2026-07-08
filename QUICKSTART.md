# Translume MVP Quickstart

Use these commands from the repository root on a Linux VM with an NVIDIA GPU. This setup assumes the Harvard MIMS repositories are not present yet.

## 1. Verify host prerequisites

```bash
nvidia-smi
docker --version
docker compose version
git --version
uv --version
```

The VM also needs outbound internet access for GitHub, Hugging Face model download, OptimusKG data download, and the public biomedical services used by ToolUniverse.

If `uv` is missing:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source "$HOME/.local/bin/env"
```

## 2. Install the host-side CLI and test dependencies

```bash
uv sync --all-groups --all-packages
source .venv/bin/activate
```

## 3. Clone the Harvard MIMS repositories

```bash
make vendor-repos
make vendor-status
make audit-vendor-model-calls
make catalog-vendor-repos
```

The command creates real Git checkouts at:

```text
third_party/upstream/Medea
third_party/upstream/OptimusKG
third_party/upstream/ToolUniverse
```

Do not use zip-extracted copies for a demo or production-style run. `make vendor-status` must report all three repositories as clean and updateable.

## 4. Create and configure `.env`

```bash
cp .env.example .env
nano .env
```

Replace the file contents with the following, then set the two required values marked with angle brackets:

```dotenv
TRANSLUME_ENV=demo
TRANSLUME_ENFORCE_PRIME_DIRECTIVES=true
TRANSLUME_STORAGE_ROOT=/data/uploads

TRANSLUME_REQUIRE_MIMS=true
TRANSLUME_REQUIRE_DOCLING=true
TRANSLUME_REQUIRE_OPENSEARCH=true
TRANSLUME_REQUIRE_POSTGRES=true
TRANSLUME_REQUIRE_LOCAL_VLLM=true
BLOCK_REMOTE_MODEL_PROVIDERS=true
TRANSLUME_RETRIEVAL_MODE=lexical

POSTGRES_DSN=postgresql://translume:translume@postgres:5432/translume
POSTGRES_PUBLIC_DSN=postgresql://translume:translume@localhost:5432/translume
POSTGRES_CONNECT_TIMEOUT_SECONDS=10

OPENSEARCH_URL=http://opensearch:9200
OPENSEARCH_PUBLIC_URL=http://localhost:9200
OPENSEARCH_TIMEOUT_SECONDS=30

VLLM_BASE_URL=http://vllm-clinical:8000/v1
VLLM_PUBLIC_BASE_URL=http://localhost:8000/v1
VLLM_MODEL=<REAL_PUBLIC_HUGGING_FACE_MODEL_ID>
VLLM_TIMEOUT_SECONDS=240
TRANSLUME_PROMPTS_ROOT=/app/configs/prompts

DOCLING_SERVICE_URL=http://docling-service:8090
DOCLING_PUBLIC_URL=http://localhost:8090
DOCLING_TIMEOUT_SECONDS=240
DOCLING_EXTRACTION_METHOD=docling

OPTIMUSKG_SERVICE_URL=http://optimuskg-service:8091
OPTIMUSKG_PUBLIC_URL=http://localhost:8091
OPTIMUSKG_VENDOR_DIR=/app/third_party/upstream/OptimusKG
OPTIMUSKG_DATA_HOST_DIR=./data/optimuskg_cache
OPTIMUSKG_CACHE_DIR=./data/optimuskg_cache
OPTIMUSKG_USE_LCC=true
OPTIMUSKG_MAX_EDGES=500
OPTIMUSKG_FORCE_DOWNLOAD=false

TOOLUNIVERSE_SERVICE_URL=http://tooluniverse-service:8092
TOOLUNIVERSE_PUBLIC_URL=http://localhost:8092
TOOLUNIVERSE_VENDOR_DIR=/app/third_party/upstream/ToolUniverse
TOOLUNIVERSE_WORKFLOW_CONFIG=/app/configs/local/tooluniverse_workflows.json
TOOLUNIVERSE_MODULE_NAMES=tooluniverse
TRANSLUME_TOOL_WORKFLOWS=literature_validation,pathway_context,target_context,variant_context,trial_context_review,therapy_context,resistance_mechanism_context,biomarker_retesting_context,guideline_context,clinical_trial_context,lineage_transformation_context,recent_therapy_agent_backfill_context
MIMS_TIMEOUT_SECONDS=240

MEDEA_SERVICE_URL=http://medea-service:8093
MEDEA_PUBLIC_URL=http://localhost:8093
MEDEA_VENDOR_DIR=/app/third_party/upstream/Medea
MEDEA_MODULE_NAMES=medea
MEDEA_DATA_HOST_DIR=./data/medea_cache
MEDEADB_PATH=./data/medea_cache/MedeaDB
MEDEA_REQUIRE_DATABASE=true
MEDEA_DB_MAX_GENE_PAIRS=10
MEDEA_DB_SIMILAR_GENES_PER_SINGLE_GENE=3
MEDEA_ALLOWED_LOCAL_MODEL_HOSTS=localhost,127.0.0.1,0.0.0.0,host.docker.internal,vllm,vllm-clinical
MEDEA_LOCAL_OPENAI_API_KEY=local-vllm
MEDEA_VLLM_TIMEOUT_SECONDS=240
MEDEA_ALLOW_REMOTE_STYLE_MODEL_NAMES=false

TRANSLUME_API_BASE_URL=http://translume-api:8080
TRANSLUME_API_URL=http://localhost:8080
TRANSLUME_UI_HOST=0.0.0.0
TRANSLUME_UI_PORT=7860
TRANSLUME_UI_URL=http://localhost:7860
TRANSLUME_UI_API_TIMEOUT_SECONDS=120
TRANSLUME_UI_PROCESS_TIMEOUT_SECONDS=900
TRANSLUME_UI_EXPORT_DIR=/tmp/translume-ui-exports

TRANSLUME_MAX_CHUNK_CHARS=2400
TRANSLUME_E2E_REPORT_PATH=<ABSOLUTE_HOST_PATH_TO_REAL_ONCOLOGY_PDF>
TRANSLUME_E2E_REPORT_TYPE=NGS

TRANSLUME_REQUIRE_MIMS=true
TRANSLUME_REQUIRE_DOCLING=true
TRANSLUME_REQUIRE_OPENSEARCH=true
TRANSLUME_REQUIRE_POSTGRES=true
TOOLUNIVERSE_WORKFLOW_CONFIG=./configs/local/tooluniverse_workflows.json
```

`VLLM_MODEL` must be a real model identifier that fits the VM GPU. The current Compose file does not pass a Hugging Face token into the vLLM container, so use a public model or update the deployment separately before using a gated model.

Do not set real remote-model credentials in this shell or `.env`. Clear inherited credentials before validation:

```bash
unset OPENAI_API_KEY OPENROUTER_API_KEY ANTHROPIC_API_KEY GEMINI_API_KEY GOOGLE_API_KEY AZURE_OPENAI_API_KEY AZURE_OPENAI_ENDPOINT NVIDIA_API_KEY NVIDIA_API_BASE
```

Load `.env` for host-side CLI commands:

```bash
set -a
source .env
set +a
```

## 5. Download and validate the Harvard MIMS data

```bash
make mims-data
make mims-data-status
```

This stores MedeaDB at `data/medea_cache/MedeaDB` and the OptimusKG client cache at `data/optimuskg_cache`. Compose bind-mounts those exact `MEDEADB_PATH` and `OPTIMUSKG_CACHE_DIR` host paths into the services; the data is not copied into Docker images. The combined target is cache-aware, so rerunning it reuses complete downloads.

## 6. Validate configuration before starting Docker

```bash
make vendor-status
make validate-prime-directives
make docker-config
make test
```

Fix the first reported error instead of disabling a required service.

## 7. Start the real MVP stack

The command below intentionally starts one GPU-backed vLLM service. It does not start the unused `vllm-docling` or worker services.

```bash
export COMPOSE_PROFILES=gpu,docling

docker compose up --build -d --wait --wait-timeout 1800 \
  postgres \
  opensearch \
  vllm-clinical \
  docling-service \
  optimuskg-service \
  tooluniverse-service \
  medea-service \
  translume-api \
  translume-ui
```

Check container state:

```bash
docker compose ps
```

Initialize and verify persistence through host-accessible endpoints:

```bash
OPENSEARCH_URL="$OPENSEARCH_PUBLIC_URL" uv run python scripts/init_opensearch.py
uv run python scripts/init_postgres.py --dsn "$POSTGRES_PUBLIC_DSN"
```

Check every required service:

```bash
curl -fsS "$VLLM_PUBLIC_BASE_URL/models"
curl -fsS "$DOCLING_PUBLIC_URL/health"
curl -fsS "$OPTIMUSKG_PUBLIC_URL/health"
curl -fsS "$TOOLUNIVERSE_PUBLIC_URL/health"
curl -fsS "$MEDEA_PUBLIC_URL/runtime-contract"
curl -fsS "$TRANSLUME_API_URL/health"
uv run python scripts/check_ui_health.py --url "$TRANSLUME_UI_URL"
```

## 8. Run the real end-to-end CLI validation

This command uploads the PDF from `TRANSLUME_E2E_REPORT_PATH`, checks the real services, validates the persisted review packet, persists a human-review decision, and verifies Postgres and OpenSearch side effects.

```bash
uv run python scripts/run_full_stack_integration.py
```

Inspect failures without replacing them with fallback output:

```bash
docker compose logs --tail=300 vllm-clinical docling-service optimuskg-service tooluniverse-service medea-service translume-api translume-ui
```

Follow one service live:

```bash
docker compose logs -f translume-api
```

## 9. Use the Gradio Oncologist Cockpit

Open on the VM:

```text
http://localhost:7860
```

For a remote VM, create a tunnel from your local machine:

```bash
ssh -L 7860:localhost:7860 -L 8080:localhost:8080 ubuntu@ec2-34-202-237-191.compute-1.amazonaws.com
```

Then open:

```text
http://localhost:7860
```

In the cockpit:

1. Select `NGS`, `WGS`, `FISH`, `IHC`, `RESEARCH_PDF`, `XT`, `XR`, or `RNA`.
2. Upload a real oncology PDF.
3. Click **Generate persisted review packet**.
4. Review the source-backed findings, normalized entities, phenotype, molecular-fit matrix, mechanism Sankey, confirmatory tests, tumor-behavior hypotheses, and clinical narrative.
5. Open **Evidence and validation**, select a real claim, choose `validated`, `rejected`, or `needs_review`, enter the reviewer information, and click **Persist validation decision**.
6. Open **Provenance and ledger** and click **Fetch persisted review packet export**.

The UI reloads the exact packet persisted by FastAPI/Postgres before rendering. A missing service, invalid provenance record, or failed containment check is shown as a real error; the UI does not substitute demo data.

## 10. Use the REST API

Process a real report:

```bash
curl --fail-with-body --max-time 1800 \
  -X POST "$TRANSLUME_API_URL/api/v1/reports/process" \
  -F "report_type=NGS" \
  -F "file=@$TRANSLUME_E2E_REPORT_PATH;type=application/pdf" \
  -o translume_review_packet.json
```

Read the generated session and first claim IDs:

```bash
SESSION_ID=$(uv run python -c 'import json; print(json.load(open("translume_review_packet.json"))["session_id"])')
CLAIM_ID=$(uv run python -c 'import json; print(json.load(open("translume_review_packet.json"))["bundle"]["claims"][0]["claim_id"])')
printf 'SESSION_ID=%s\nCLAIM_ID=%s\n' "$SESSION_ID" "$CLAIM_ID"
```

Fetch validation cards:

```bash
curl --fail-with-body \
  "$TRANSLUME_API_URL/api/v1/review-packets/$SESSION_ID/validation-cards"
```

Persist a human validation decision:

```bash
curl --fail-with-body \
  -X POST "$TRANSLUME_API_URL/api/v1/review-packets/$SESSION_ID/claims/$CLAIM_ID/validation" \
  -H 'Content-Type: application/json' \
  -d '{"status":"needs_review","reviewer_id":"reviewer-1","reviewer_note":"Requires clinician source review."}'
```

Export the exact persisted packet:

```bash
curl --fail-with-body \
  "$TRANSLUME_API_URL/api/v1/review-packets/$SESSION_ID/export" \
  -o translume_review_packet_export.json
```

## 11. Update the Harvard MIMS repositories safely

Translume does not modify the upstream MIMS source trees. The upstream repositories remain under `third_party/upstream/`; Translume-specific behavior lives in `packages/translume-ports`, `packages/translume-adapters`, and `services/*-service`. Those wrappers enforce local vLLM routing, block remote model-provider escape, normalize outputs into Translume schemas, and preserve provenance.

Before pulling, confirm the upstream trees are clean:

```bash
make vendor-status
```

Pull fast-forward-only updates:

```bash
git -C third_party/upstream/Medea pull --ff-only
git -C third_party/upstream/OptimusKG pull --ff-only
git -C third_party/upstream/ToolUniverse pull --ff-only
```

The equivalent all-repository command is:

```bash
make vendor-repos
```

Validate the updated upstream code against Translume boundaries:

```bash
make vendor-status
make audit-vendor-model-calls
make catalog-vendor-repos
make test
```

Rebuild the MIMS service images because Docker copies the Git checkouts into those images:

```bash
docker compose up --build -d --wait --wait-timeout 1800 \
  optimuskg-service \
  tooluniverse-service \
  medea-service \
  translume-api \
  translume-ui
```

Recheck the service contracts and end-to-end workflow:

```bash
curl -fsS "$OPTIMUSKG_PUBLIC_URL/health"
curl -fsS "$TOOLUNIVERSE_PUBLIC_URL/health"
curl -fsS "$MEDEA_PUBLIC_URL/runtime-contract"
uv run python scripts/run_full_stack_integration.py
```

If an upstream update changes an API, update the Translume adapter or service wrapper. Do not edit the Harvard repository to make the integration pass.

## 12. Stop or reset the stack

Stop containers and preserve Postgres/OpenSearch volumes:

```bash
docker compose down
```

Remove containers and all persisted Postgres/OpenSearch data:

```bash
docker compose down -v
```
