# Developer guide: CPU application, remote OpenAI inference

## Runtime architecture

The end-user entry point is `docker compose up --build -d`. The UI is an API client; it does not execute Docker or shell commands. FastAPI orchestrates document extraction, source alignment, entity normalization, graph/tool retrieval, Medea reasoning, structured clinical artifacts, Postgres persistence, and lexical OpenSearch indexing. The downstream runners compile the precision-oncology packet, pathway analysis, research memo, and tumor-board causal summary.

All learned inference uses the official `https://api.openai.com/v1` service. The reasoning/document default is `gpt-6-astra`, sent with `reasoning.mode=pro`. The embedding default is `text-embedding-3-large`, 1,536 dimensions. The local runtime performs deterministic text extraction, JSON/schema validation, source-data retrieval, array math, indexing, and ReportLab PDF rendering. Local inference is prohibited by configuration and the startup gate.

The name `docling-service` remains an internal network/API compatibility name. It runs the new OpenAI PDF converter; the Docling ML package is no longer installed. Existing upstream archive snapshots are preserved byte-for-byte. Only the narrow source modules needed for actual graph/retrieval behavior are loaded; upstream local-model packages are not installed or executed.

## Source paths and responsibilities

| Path | Implemented responsibility |
| --- | --- |
| `packages/translume-clients/src/translume_clients/openai_client.py` | Shared sync/async authenticated HTTP transport, remote token counting, Responses/embeddings requests, finite retries, typed failures, request receipts, and durable audit journal. |
| `packages/translume-adapters/src/translume_adapters/model_providers/openai_provider.py` | Astra Pro structured-output requests, strict wire schemas, bounded output recovery, and task-local request provenance. |
| `packages/translume-adapters/src/translume_adapters/embedding_providers/` | Real remote embedding batches, response/vector validation, and dimension consistency. |
| `packages/translume-core/src/translume_core/compiler/` | Artifact schemas, source-aware extraction splitting, final-request token budgets, clinical validation, and generation provenance. |
| `packages/translume-core/src/translume_core/workflow.py` | Remote-provider requirement, per-session correlation, document receipts, sibling-task cancellation, actual service orchestration, and persistence. |
| `apps/translume-api/src/translume_api/config.py` | OpenAI-only settings, bounded input/output budgets, and startup validation. |
| `apps/translume-api/src/translume_api/main.py` | Real model-access readiness checks, request-scoped client lifetime, and error-to-HTTP boundary. |
| `services/docling-service/src/docling_service/` | Actual per-page PDF input to OpenAI, strict extraction schema, source-page identity, native-text coverage checks, and extraction audit metadata. |
| `services/medea-service/src/medea_service/` | Original DepMap lookup/OpenScholar logic through narrow imports, real literature retrieval, OpenAI relevance judging, and remote embedding reranking. |
| `packages/translume-adapters/src/translume_adapters/graph_providers/optimuskg_runtime.py` | Real OptimusKG Parquet lookup with bounded node batches and streamed endpoint retrieval. |
| `packages/translume-adapters/src/translume_adapters/tool_providers/tooluniverse_runtime.py` | Explicit biomedical tool allowlist and blocking retrieval moved off the ASGI event loop. |
| `precision_oncology_json_pipeline/` | Four-stage remote precision pipeline, real required web-search completion, effective effort/mode-aware cache identity, and audited failures. |
| `dynamic_pathway_analyzer/` | Remote research/analysis/synthesis, bounded shared run deadline, and a common OpenAI request helper. |
| `scripts/initialize_runtime.py` | Actual scientific-data provisioning plus repeatable Postgres and OpenSearch initialization. |
| `packages/translume-core/src/translume_core/vendor/packaged.py` | SHA-256 verification, safe archive installation, and exact installed-source validation. |
| `third_party/vendor_archives.lock.json` | Exact bundled archive identity; no fabricated Git metadata. |
| `docker-compose.yml`, `docker/*.Dockerfile` | CPU-only services, ordered readiness, persistent volumes, loopback UI/API access, and no GPU reservations. |
| `docker/runtime-requirements.txt`, `docker/test-requirements.txt`, `uv.lock` | Pinned CPU dependencies; Docker installs hashes for the full dependency closure. |
| `scripts/run_full_stack_integration.py` | Live OpenAI + actual report + persistence/review + downstream verification. |

## OpenAI boundary and errors

Requests use the Responses API with strict JSON Schema under `text.format`, `store=false`, and explicit output-token limits. They do not send Chat Completions-only parameters or unsupported sampling controls. Token budgeting calls the remote input-token endpoint with the actual rendered prompt, schema, instructions, and reasoning settings. The configured operational context budget is conservative; it is a limit imposed by this application, not a claim about the model's maximum context.

Transport retries are finite and restricted to transient connection/server/rate-limit failures. Authentication, permissions, insufficient quota, refusals, invalid requests, and content filters terminate the affected operation. Incomplete output is never treated as a completed artifact. Output-limit recovery is bounded; report extraction splits source batches only while preserving source identities and explicit budgets. Failed services and empty/invalid required results are surfaced rather than replaced with generated evidence.

The shared client journals real request attempts with correlation IDs, requested and observed model identity, endpoint, response/request IDs when supplied, effective mode/effort, usage, request/schema hashes, timings, and failure status. It does not put API keys or full clinical prompts into the journal. Per-artifact capture uses task-local scopes so concurrent decision/claims generation cannot mix receipts. The JSONL audit writes are flushed and synchronized; a failed audit write is an error.

`store=false` controls response storage at the API layer. It is not a claim of zero retention. Review the applicable OpenAI account/data controls for your deployment.

## Scientific behavior retained and changed

Medea keeps the bundled source implementation for DepMap lookup and OpenScholar synthesis/ranking structure. Active correlation files are memory mapped. Its literature path retrieves actual sources and preserves their identifiers and citations. A failed literature endpoint is represented as unavailable; it is not clinical negative evidence.

The old local neural reranker is replaced by real OpenAI embedding vectors and deterministic CPU cosine ranking, together with remote relevance judging. This is a substantive ranking change, so identical literature ordering or identical clinical prose is not promised. The packet schema, downstream artifact roles, source attribution, and human-review controls are retained. Validation with representative real reports remains necessary before operational use.

The setup downloads only the five active DepMap files, not unrelated learned checkpoints. It resolves an actual Hugging Face repository revision and records that revision. OptimusKG uses its bundled official Dataverse client and validates the resulting Parquet columns. Reactome runs the official Release97 graph database in a CPU container. Its image is configured for amd64 and requires emulation on Apple Silicon.

The package includes immutable upstream source archives, not an updateable Git checkout. `scripts/install_packaged_vendors.py` verifies each archive hash, rejects unsafe paths/links, extracts safely, and verifies every installed source file against the archive. The startup gate accepts this verified packaging contract. An unrelated preexisting directory or modified vendor file fails validation.

## Containers, persistence, and secrets

Only inference services receive `OPENAI_API_KEY`: API, document, Medea, precision, dynamic, and the optional live-verification container. The UI, worker, graph/tool wrappers, setup, and databases do not receive it. `.env` is excluded from Docker build context.

The databases and internal wrappers have no published host ports. UI/API listen on the host loopback interface. This is a single-user laptop deployment; adding multiuser network exposure requires authentication and transport controls appropriate to that deployment.

`data-init` must finish successfully before data-dependent services start. It prepares writable upload/audit directories, provisions scientific data, validates it, and initializes persistence. Named volumes hold Postgres, OpenSearch, DepMap, OptimusKG, uploads, and audit journals. Downstream artifacts are bind-mounted at `data/artifacts` so the user can access the complete files.

The workflow stores the exact review packet in Postgres. Downstream runners receive that packet through the internal API and write validated session/run paths. They verify nonempty required artifacts before returning success. API/UI request limits cover the long remote runs; the precision subprocess and combined dynamic/synthesis stages retain finite deadlines.

## Development and verification

For repeatable CPU tests with Docker:

```sh
docker build -f docker/test.Dockerfile -t translume-tests .
docker run --rm --network none translume-tests python scripts/run_unit_tests.py
```

This runs the main, precision, and dynamic suites separately. Unit/API-boundary tests use explicit test fixtures and controlled HTTP transports; they do not certify live model behavior or network availability. Production entry points do not use those fixtures.

For real integration, follow the README's verification step with your own API key, report PDF, and diagnosis:

```sh
docker compose --profile verification run --rm verify
```

That command issues actual model calls, invokes the complete report workflow, checks persisted data and provenance, performs a `needs_review` reviewer round trip, and runs the downstream report services. There is no bundled fake success report.

The checked-in dependency files were resolved together. To deliberately update dependencies, edit `docker/runtime-requirements.in` and the matching workspace manifests, regenerate the hashed runtime/test files with `uv pip compile --generate-hashes --python-version 3.12`, regenerate `uv.lock`, then rerun the suites. Do not install an upstream vendor's broad dependency list: it reintroduces unrelated local models.

See `VALIDATION.md` for the exact checks executed for this delivery and the checks that could not be executed here. Database credentials in the private Compose network are the existing development defaults; remote deployment hardening is outside the laptop launch procedure.
