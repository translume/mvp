# Translume MVP Production Workflow

The current product path is a real end-to-end workflow, not a cosmetic demo path.
It accepts a PDF, stores the raw source, extracts page/block text with PyMuPDF,
chunks by detected clinical sections, extracts source-backed molecular findings,
normalizes entities, requires configured MIMS evidence providers by default,
compiles molecular phenotype, molecular-fit matrix, mechanism Sankey,
confirmatory testing, tumor-behavior hypotheses, evidence-classified claims,
narrative, provenance, and a ledger-backed review packet export.

## Strict MIMS mode

`TRANSLUME_REQUIRE_MIMS=true` is the default. In this mode, missing OptimusKG,
ToolUniverse, or Medea evidence artifacts fail explicitly. This prevents hidden
scorecard inflation or fake enrichment.

Required real service inputs for strict mode:

- `third_party/upstream/OptimusKG`, a real git clone of OptimusKG.
- `OPTIMUSKG_CACHE_DIR`, containing or receiving OptimusKG parquet files through the real OptimusKG Python client.
- `TOOLUNIVERSE_WORKFLOW_CONFIG`, mapping allow-listed workflows to real ToolUniverse tools.
- `third_party/upstream/Medea`, a real git clone of Medea routed through local vLLM.

OptimusKG graph context must come from the OptimusKG client/parquet path. Generic CSV/JSON edge files are not accepted as a production substitute.

## API endpoint

```bash
curl -F "report_type=NGS" \
  -F "file=@/path/to/report.pdf" \
  http://localhost:8080/api/v1/reports/process
```

The response is a JSON review packet containing chunks, structured artifacts,
evidence context, claim cards, provenance, ledger events, and narrative.

## OpenSearch persistence

OpenSearch is the retrieval/evidence substrate. Source-backed document chunks
are indexed immediately after chunk construction and retrieved back from
OpenSearch before report extraction. After the review packet is compiled,
Translume also converts the full packet into index-specific document batches and
writes those artifacts to OpenSearch through the real HTTP client boundary.

Persisted indexes:

```text
translume_document_chunks
translume_report_findings
translume_artifacts
translume_normalized_entities
translume_graph_evidence
translume_tool_outputs
translume_medea_reasoning
translume_evidence_claims
translume_artifact_provenance
translume_validation_decisions
translume_ledger_events
```

## Postgres persistence

Postgres is the durable ledger/artifact metadata source of truth. The workflow
requires Postgres by default and persists:

```text
case_sessions
source_files
document_chunks
artifacts
report_findings
normalized_entities
graph_evidence
tool_outputs
medea_reasoning
evidence_claims
artifact_provenance
validation_decisions
ledger_events
review_packets
```

The workflow adds explicit `opensearch_persisted` and
`postgres_metadata_persisted` ledger events. If either required persistence layer
is unavailable, the API fails instead of returning a fake or unpersisted success.

## Development/degraded mode

`TRANSLUME_REQUIRE_MIMS=false`, `TRANSLUME_REQUIRE_OPENSEARCH=false`, or
`TRANSLUME_REQUIRE_POSTGRES=false` may be used only for isolated local component
development. These modes are not the target MVP validation path.

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

## Real MIMS execution from vendored repos

The production API uses HTTP clients for the three MIMS services:

```text
OptimusKGServiceClient → optimuskg-service /context
ToolUniverseServiceClient → tooluniverse-service /workflows
MedeaServiceClient → medea-service /reason
```

The API does not import MIMS packages directly. Each service owns the dependency
surface for its vendored repository and must fail explicitly if the vendor repo,
workflow configuration, graph data, or local model routing is unavailable.

MIMS evidence enters the compiler only as structured artifacts:

```text
GraphEvidenceArtifact
ToolRunArtifact[]
MedeaReasoningArtifact
```

Those artifacts are indexed into OpenSearch, persisted in Postgres metadata, and
included in the review-packet export. They are evidence inputs, not clinical
truth and not direct narrative text.

## Human validation-card persistence

After `/api/v1/reports/process` persists a review packet, the reviewer workflow
uses the stored packet as the source of truth:

```text
GET validation cards
→ reviewer selects claim/status/note
→ POST validation decision
→ load packet from Postgres
→ apply decision to existing claim
→ append validation decision and ledger event
→ persist updated packet to Postgres
→ re-index updated packet to OpenSearch
→ return updated claim cards
```

The API does not create packets or claims during validation. Validation requires
an existing persisted review packet and an existing claim ID. This keeps human
review aligned with the Translume MVP invariant: every clinical statement must
remain traceable to source text, structured artifacts, evidence, or human
validation.


## Early OpenSearch chunk indexing

Source-backed document chunks are now indexed into OpenSearch before report extraction and downstream artifact generation. In required OpenSearch mode, report extraction retrieves those chunks back from OpenSearch and will not continue if retrieval returns zero chunks. This makes OpenSearch part of the retrieval/evidence path rather than only a final packet persistence target. The current retrieval path is metadata/lexical scoped by case, session, and source file; vector/HNSW retrieval is not claimed as active until a real embedding generation path is implemented.
