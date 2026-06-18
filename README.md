# Translume 

<p align="center"> <img src="docs/translume-logo.png" alt="Translume logo" width="900"/> </p> <p align="center"> <strong>Turning oncology reports into near-time, explainable, clinician-reviewable tumor-behavior intelligence</strong> </p> <p style="font-weight:lighter;" align="center">The future foundation for Adaptive Precision Oncology</p><p align="center"> <img alt="UV" src="https://img.shields.io/badge/UV-0.5.18-6f2c91?style=for-the-badge&logo=python&logoColor=white"/> <img alt="AgentLite" src="https://img.shields.io/badge/AgentLite-0.1.2-2d9cdb?style=for-the-badge"/> <img alt="OpenRouter API" src="https://img.shields.io/badge/OpenRouter-API-5f6368?style=for-the-badge"/> <img alt="Paper on arXiv & Cell.com" src="https://img.shields.io/badge/Paper%20on-arXiv-4c8eda?style=for-the-badge"/> <img alt="Project Website" src="https://img.shields.io/badge/Project-Website-4c8eda?style=for-the-badge"/> <img alt="Datasets" src="https://img.shields.io/badge/Datasets-Hugging%20Face-4c8eda?style=for-the-badge"/> </p> 

[![Project Website](https://img.shields.io/badge/Project-Website-4c8eda?style=for-the-badge)](https://translume.github.io/web/index.html)
[![Research](https://img.shields.io/badge/Research-Papers-7b61ff?style=for-the-badge)](https://translume.github.io/web/papers.html)
[![Platform](https://img.shields.io/badge/Platform-Overview-00bcd4?style=for-the-badge)](https://translume.github.io/web/platform.html)
[![Tutorials](https://img.shields.io/badge/Tutorials-Demos-14b8a6?style=for-the-badge)](https://translume.github.io/web/tutorials.html)

Translume is a clinical output compiler for translational oncology. It ingests an oncology molecular report, extracts structured molecular findings, maps them into biological axes, ranks molecular fits for expert review, explains “why from omics,” builds a Finding → Mechanism → Molecular Fit → Validation Test chain, identifies confirmatory testing needs, and produces a source-backed tumor-behavior hypothesis without making treatment recommendations. Modern oncology teams do not lack molecular data. They lack a fast, defensible way to turn NGS, WGS, FISH, IHC, RNA, pathology, and research reports into reviewable clinical-translational reasoning. Molecular reports surface variants, copy-number changes, expression signals, limitations, and negative findings, but those facts usually remain disconnected from mechanism, evidence strength, validation needs, and disease behavior. Translume closes that gap by converting raw report content into a structured review surface where every major claim is tied to source text, evidence class, uncertainty, provenance, and human validation. 

The MVP focuses on one high-value workflow: one oncology report becomes one structured, explainable, clinician-reviewable tumor-behavior intelligence packet. The output shows what the report found, why each finding may matter biologically, what is unsupported, what must be validated next, which claims are facts versus hypotheses, and who accepted, rejected, or flagged each claim. This reduces tumor-board and translational review burden while creating reusable structured reasoning that can later support longitudinal disease modeling. The system is intentionally not a treatment recommendation engine, diagnostic device, outcome predictor, or adaptive precision oncology platform yet. It is the foundation those future systems require: accurate document extraction, source-backed chunks, local structured model outputs, biomedical graph context, governed scientific-tool evidence, bounded omics/literature reasoning, human validation controls, and a provenance-backed ledger. 

## Current MVP Scope
```
→ PDF report of NGS, WGS, FISH, IHC, etc...
→ Docling / Granite Docling document extraction
→ section-aware chunks
→ OpenSearch indexing
→ local vLLM structured clinical extraction
→ normalized molecular entities
→ KG graph context
→ Governed evidence workflows
→ Bounded omics/literature reasoning
→ molecular phenotype
→ molecular-fit matrix
→ mechanism Sankey
→ confirmatory testing plan
→ tumor-behavior model
→ evidence-classified claim cards
→ human validation
→ clinical ledger export
```
---


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


## Medea local-vLLM runtime enforcement

Medea is now routed through Translume-owned service code that validates local model configuration, blocks remote model-provider credentials, and patches Medea LLM call sites from outside the vendored repository. The Harvard Medea source under `third_party/upstream/Medea` remains clean and updateable; Translume applies local-vLLM behavior through `services/medea-service` and adapter/service boundaries rather than editing Medea files. Runtime validation now checks `/runtime-contract` on the Medea service and requires local routing fields before the full-stack report workflow can proceed. This code path is unit-validated, but Docker/GPU/vLLM/Medea runtime still requires live VM execution.


## Evidence-derived tumor behavior validation

TumorBehaviorModelOutput is generated through the local vLLM structured-output path and then validated for case-derived evidence support. The fixed state vocabulary is allowed, but selected states, transition hypotheses, rationale, and supporting artifacts must come from the current report extraction, normalized entities, OptimusKG graph evidence, ToolUniverse artifacts, Medea reasoning, molecular phenotype, molecular-fit matrix, mechanism Sankey, and confirmatory testing gaps. Generic hardcoded transitions, unsupported support IDs, transition probabilities, outcome predictions, and treatment-directing language fail the production workflow instead of being returned as a polished review packet.

## Artifact provenance enforcement

Every review-packet artifact must carry artifact-specific provenance before export. Translume records which schema validated the artifact, which model or provider produced it, which prompt/schema hash was used when applicable, which source chunks and upstream artifacts informed it, and whether generation completed successfully. If provenance is missing or generic, production packet export fails loudly rather than returning an unverifiable clinical review packet.


## Tutorial 14 completed: lexical retrieval scope enforcement

The MVP retrieval scope is now explicit and enforced. Translume uses OpenSearch lexical and metadata-scoped retrieval for source document chunks, filtered by case ID, session ID, and source file ID. The document chunk index no longer emits `knn_vector` mappings or accepts embeddings in the production path. If `TRANSLUME_RETRIEVAL_MODE` is set to `vector`, `hybrid`, `hnsw`, or `knn`, the production gate and retrieval functions fail loudly because there is not yet a real local embedding generation and indexing path. This prevents the project from claiming vector or HNSW retrieval before embeddings are actually produced, indexed, retrieved, and live-validated.

Future vector retrieval should be added only by implementing a real local embedding provider, generating embeddings for every indexed chunk, storing the vectors in OpenSearch, and proving vector queries in live VM validation. Until then, docs, runtime reports, and UI language must describe retrieval as lexical/metadata-grounded.

## Clinician-facing artifact panels

The Gradio cockpit now renders the exact persisted `ReviewPacketExport` returned by FastAPI as clinician-facing panels rather than using raw JSON as the primary experience. The UI performs the real report-processing API call, then reloads the packet through the persisted export endpoint before rendering it. If the persisted packet is incomplete, lacks provenance, or has failed narrative containment, the cockpit blocks rendering and shows the actual error.

The clinical surface includes source-backed findings, normalized entities, molecular phenotype, molecular-fit review matrix, the mechanism Sankey, confirmatory tests, case-derived tumor-state evidence, transition hypotheses, OptimusKG graph context, ToolUniverse evidence, Medea bounded reasoning, claim validation, provenance, and the discovery ledger. The technical JSON remains available in a separate tab for audit inspection, but it is not the primary clinical surface.

Claim-validation actions call the real validation API, then reload the persisted packet from Postgres so the UI does not update optimistically. Review-packet downloads also come from the persisted export endpoint; the UI does not reconstruct or fabricate export content locally.

---

# Important Notice: Intended Use, Human Oversight, and Ethical Use Statement

Translume is an information-processing, evidence-compilation, and clinical review support platform. It is designed to assist qualified professionals in organizing, reviewing, and tracing information derived from oncology and related biomedical documents. It is not intended to function as a diagnostic system, treatment recommendation engine, medical device, autonomous clinical decision-maker, or substitute for professional medical judgment.

All outputs generated by Translume—including findings, hypotheses, tumor-behavior models, evidence summaries, biological interpretations, validation suggestions, reasoning artifacts, and visualizations—are intended solely to support human review and discussion. These outputs may contain inaccuracies, omissions, incomplete evidence, or interpretations that require further verification.

Clinical decisions, diagnoses, prognoses, treatment selections, patient management decisions, research conclusions, regulatory submissions, and other consequential actions must never be based solely on system-generated output. All information produced by the platform must be independently reviewed, interpreted, and validated by appropriately qualified and credentialed healthcare professionals, researchers, laboratory personnel, or other authorized subject-matter experts.

Translume does not establish clinical truth, determine standards of care, predict outcomes, guarantee completeness of evidence, or replace multidisciplinary review processes. The presence of supporting evidence, literature references, graph relationships, computational reasoning, or generated hypotheses should not be interpreted as proof of clinical validity, efficacy, safety, causality, or medical appropriateness.

Users are responsible for ensuring compliance with all applicable laws, regulations, institutional policies, ethical standards, privacy requirements, data-governance frameworks, and professional practice obligations governing the use of clinical, biomedical, research, or patient-related information.

The platform is intended to augment human expertise by improving transparency, traceability, reviewability, and evidence organization. Human judgment remains the final authority for all interpretations, conclusions, recommendations, and actions derived from information presented by the system.

By using Translume, users acknowledge that the platform serves as a decision-support and evidence-review aid only, and that appropriately qualified human oversight is required for all clinical, research, operational, and regulatory use cases.

# Intended Use, Limitations, and Ethical Use Statement

Translume is designed to support clinical and translational oncology teams by organizing complex oncology reports into structured, source-backed, reviewable information. It helps extract findings, surface evidence, identify uncertainty, show possible biological mechanisms, and support expert review.

## What Translume Does

Translume helps convert oncology reports into structured review packets that may include:

Source-backed molecular findings from uploaded reports.

Normalized clinical and biological entities.

Evidence summaries from approved knowledge sources and tools.

Mechanism-oriented views that help explain why a finding may matter biologically.

Tumor-behavior hypotheses derived from the specific case evidence.

Evidence-classified claim cards for expert review.

Human validation workflows that allow qualified reviewers to accept, reject, or flag claims.

Provenance records showing where outputs came from and what supported them.

Ledger records that preserve review history, decisions, and traceability.

Exportable review packets for clinical, translational, research, or operational review.

The purpose is to improve clarity, transparency, traceability, and review efficiency.

## What Translume Does Not Do

Translume does not diagnose disease.

Translume does not recommend treatment.

Translume does not determine a standard of care.

Translume does not predict patient outcomes.

Translume does not replace oncologists, pathologists, molecular tumor boards, genetic counselors, laboratory directors, or other qualified professionals.

Translume does not make autonomous clinical decisions.

Translume does not establish clinical truth.

Translume does not guarantee that evidence is complete, current, or clinically sufficient.

Translume does not determine whether a therapy is safe, effective, appropriate, available, reimbursable, or indicated for a specific patient.

Any output from Translume should be treated as informational, preliminary, and subject to expert review.

## Human Review Requirement

All Translume outputs must be reviewed by appropriately qualified and credentialed clinical, scientific, or laboratory personnel before they are used in any clinical, research, operational, regulatory, or patient-related context.

A human-in-the-loop review process is required. Final responsibility for interpretation, validation, communication, and action remains with qualified professionals.

## Foundation for Adaptive Precision Oncology

Translume is not itself an adaptive precision oncology platform today. It is a foundation for moving toward that future.

By creating structured, traceable, source-backed, and human-validated records from oncology reports, Translume helps build the data and reasoning layer needed for future systems that may support longitudinal tumor modeling, evidence learning, cohort analysis, adaptive research workflows, and more personalized oncology review.

The near-term goal is not autonomous medicine. The goal is to make complex oncology information more usable, reviewable, auditable, and scalable so that expert teams can work faster and with greater confidence.

