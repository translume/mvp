# Translume

<p align="center">
  <img src="docs/translume-logo.png" alt="Translume logo" width="900"/>
</p>

<p align="center">
  <strong>Turning oncology reports into near-time, explainable, clinician-reviewable tumor-behavior intelligence.</strong>
</p>

<p align="center">
  <img alt="UV" src="https://img.shields.io/badge/UV-0.5.18-6f2c91?style=for-the-badge&logo=python&logoColor=white"/>
  <img alt="AgentLite" src="https://img.shields.io/badge/AgentLite-0.1.2-2d9cdb?style=for-the-badge"/>
  <img alt="OpenRouter API" src="https://img.shields.io/badge/OpenRouter-API-5f6368?style=for-the-badge"/>
  <img alt="Paper on arXiv" src="https://img.shields.io/badge/Paper%20on-arXiv-4c8eda?style=for-the-badge"/>
  <img alt="Project Website" src="https://img.shields.io/badge/Project-Website-4c8eda?style=for-the-badge"/>
  <img alt="Datasets" src="https://img.shields.io/badge/Datasets-Hugging%20Face-4c8eda?style=for-the-badge"/>
</p>


Translume is a clinical output compiler for translational oncology. It ingests an oncology molecular report, extracts structured molecular findings, maps them into biological axes, ranks molecular fits for expert review, explains “why from omics,” builds a Finding → Mechanism → Molecular Fit → Validation Test chain, identifies confirmatory testing needs, and produces a source-backed tumor-behavior hypothesis without making treatment recommendations.

Modern oncology teams do not lack molecular data. They lack a fast, defensible way to turn NGS, WGS, FISH, IHC, RNA, pathology, and research reports into reviewable clinical-translational reasoning. Molecular reports surface variants, copy-number changes, expression signals, limitations, and negative findings, but those facts usually remain disconnected from mechanism, evidence strength, validation needs, and disease behavior. Translume closes that gap by converting raw report content into a structured review surface where every major claim is tied to source text, evidence class, uncertainty, provenance, and human validation.

The MVP focuses on one high-value workflow: one oncology report becomes one structured, explainable, clinician-reviewable tumor-behavior intelligence packet. The output shows what the report found, why each finding may matter biologically, what is unsupported, what must be validated next, which claims are facts versus hypotheses, and who accepted, rejected, or flagged each claim. This reduces tumor-board and translational review burden while creating reusable structured reasoning that can later support longitudinal disease modeling.

The system is intentionally not a treatment recommendation engine, diagnostic device, outcome predictor, or adaptive precision oncology platform yet. It is the foundation those future systems require: accurate document extraction, source-backed chunks, local structured model outputs, biomedical graph context, governed scientific-tool evidence, bounded omics/literature reasoning, human validation controls, and a provenance-backed ledger.

## Current MVP Scope

```text
PDF report
→ Docling / Granite Docling document extraction
→ section-aware chunks
→ OpenSearch indexing
→ local vLLM structured clinical extraction
→ normalized molecular entities
→ OptimusKG graph context
→ ToolUniverse governed evidence workflows
→ Medea bounded omics/literature reasoning
→ molecular phenotype
→ molecular-fit matrix
→ mechanism Sankey
→ confirmatory testing plan
→ tumor-behavior model
→ evidence-classified claim cards
→ human validation
→ ledger export
```

## What Translume Produces

Translume produces a reviewable packet containing:

```text
source-backed molecular findings
normalized biomedical entities
graph/evidence-enriched biological context
patient-specific omics readout
molecular phenotype
molecular-fit review matrix
mechanism Sankey
confirmatory testing plan
tumor-behavior state hypotheses
evidence-classified claim cards
human validation decisions
provenance-backed ledger export
```

## What Translume Does Not Claim

Translume does not claim to diagnose cancer, recommend treatment, predict survival, select therapy, replace a tumor board, or prove adaptive precision oncology from a single report. Its outputs are hypothesis-generating, evidence-labeled, and clinician-reviewable. Every clinically meaningful statement must remain tied to source text, retrieved evidence, structured artifacts, or human validation.

## Future Direction

The near-term MVP is a single-report clinical output compiler. The next expansion is archived-sample and lesion-sample comparison, followed by clonal lineage reconstruction, niche-risk modeling, and a DDCS/cartilage-lesion registry. Only after sufficient longitudinal data exists should Translume add Markov-state learning, clone-survival simulation, early-warning surveillance, and adaptive precision oncology workflows.

The future research path is:

```text
report or lesion sample
→ structured reasoning packet
→ expert validation
→ cartilage-lesion / DDCS registry
→ longitudinal imaging, ctDNA, proteomic, fibrotic-niche, and bioelectric signals
→ Markov-state early-warning model
→ prospective validation
→ adaptive precision oncology infrastructure
```

For DDCS and suspicious cartilage/bone lesions, the long-term model is best framed as a hypothesis-generating surveillance architecture. Plasma proteomics may provide systemic or cell-type stress signals, fibrotic-niche biology may indicate a tumor-permissive microenvironment, bioelectricity may represent local tissue quality-control failure, and a Markov model can integrate those signals with imaging, symptoms, pathology, ctDNA, and molecular findings over time. This does not prove DDCS diagnosis or prevention today; it defines a safe research pathway for identifying dangerous transitions earlier and routing cases to sarcoma-board review, biopsy, molecular validation, or local intervention when warranted.

## Core Thesis

Translume’s durable value is not that it summarizes oncology reports faster. Its value is that it turns fragmented molecular findings, biological evidence, literature, pathway knowledge, expert interpretation, validation decisions, and tumor-behavior hypotheses into a structured translational reasoning process that can be reviewed, reused, audited, and improved over time.

Translume turns one-off expert reasoning into a compounding institutional asset.


### Translume MVP Production Workflow

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
