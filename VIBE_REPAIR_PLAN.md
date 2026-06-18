Tutorial 1 — Fix the Gradio production launch path
Gap being fixed

The current Docker UI command tries to run the Gradio app as if it were a FastAPI ASGI app. It calls uvicorn translume_ui.app:app, but the UI module launches Gradio directly through a build-and-launch pattern. That means the UI container can fail before the oncologist ever reaches the cockpit.

What the code should do

The UI Dockerfile should run the Gradio application directly through the module entrypoint. The Gradio app should expose a clear main function that builds the interface, launches it on the configured host and port, and exits with a real error if required API configuration is missing. The UI must call real FastAPI endpoints; it must not display static JSON, local fixture data, or fake status.

Intended runtime behavior

When the user runs Docker Compose, the Gradio container should start, listen on the configured port, and show the Oncologist Cockpit. The upload button must submit the PDF to the real API service. If the API is unavailable, the UI should show a real connection error rather than pretending the workflow succeeded.

Business outcome

This repairs the first visible demo failure. The product cannot demonstrate reviewable tumor-behavior intelligence unless a clinician can actually open the cockpit, upload a report, and see the generated review packet.

Acceptance criteria

The UI container starts through Docker Compose without requiring Uvicorn. The Gradio page loads in the browser. Upload actions call the real FastAPI endpoint. If the API is unreachable, the UI displays an explicit failure. No static demo response is rendered. The live VM validator verifies that the UI service is reachable.

Tutorial 2 — Replace zip-vendored MIMS folders with real git clones
Gap being fixed

The MIMS folders under third_party/upstream are zip-extracted directories, not git repositories. Because they lack .git, the promised git pull --ff-only update path cannot work. That violates the updateable MIMS strategy.

What the code should do

The vendor workflow should split offline zip bootstrap from production vendor management. A production vendor command should clone or pull the actual GitHub repositories into third_party/upstream/Medea, third_party/upstream/OptimusKG, and third_party/upstream/ToolUniverse. A separate offline bootstrap command may unpack zips, but production validation must fail if the folders are not real git clones.

Intended runtime behavior

When the operator runs the vendor update command, each MIMS repo is cloned if missing or pulled if already present. The system records the current commit hash in a manifest file. The Translume code remains outside those repos, so upstream updates do not overwrite Translume adapters.

Business outcome

This makes the MIMS integration maintainable. Translume can keep receiving Harvard MIMS updates while preserving its own safety, local-model routing, schemas, and clinical validation logic.

Acceptance criteria

Each upstream folder contains a .git directory. git -C third_party/upstream/<repo> pull --ff-only works for all three repos. The vendor status command fails if any repo is zip-extracted only. The vendor manifest records repo URL, branch, commit, and last update time. Translume-owned adapters remain in packages/translume-adapters, not inside Harvard repos.

Tutorial 3 — Add a PRIME_DIRECTIVES production gate
Gap being fixed

The codebase currently has many pieces that look correct structurally, but nothing enforces the “nothing fake” rule as a runtime or CI gate. Without a hard gate, fake success can re-enter the product path.

What the code should do

Add a production validation module and command that checks whether the runtime is allowed to start in production/demo mode. It should verify that required services are enabled, MIMS repos are real git clones, required environment variables are set, remote model provider variables are blocked, OpenSearch and Postgres are required, Docling is required, MIMS is required, and the UI Docker launch is correct.

Intended runtime behavior

When TRANSLUME_ENV=production or the live demo profile is enabled, the API should refuse to start if core dependencies are missing or configured as optional. The validator should fail loudly, produce a diagnostic report, and tell the operator exactly what needs to be fixed.

Business outcome

This prevents scorecard inflation. It protects the product from appearing demo-ready when core services are missing or fake paths are silently enabled.

Acceptance criteria

Production mode fails if OpenSearch, Postgres, Docling, MIMS, or vLLM requirements are disabled. Production mode fails if MIMS upstream directories are not git clones. Production mode fails if remote provider credentials are active. Production mode fails if the UI entrypoint is invalid. The failure report is written to diagnostics and shown clearly.

Tutorial 4 — Persist upload/session metadata before clinical processing
Gap being fixed

The workflow currently risks persisting metadata only after the review packet is mostly built. If processing fails halfway, the raw upload may exist but the ledger may not fully reflect the attempted run.

What the code should do

The workflow should persist the case session, source file metadata, and upload ledger event immediately after the raw PDF is stored. Every later step should append ledger events as it succeeds or fails. A failure should create a durable failure event with the stage, error type, and non-secret diagnostic message.

Intended runtime behavior

When the user uploads a PDF, the system immediately records that the report exists and that processing began. If Docling, OpenSearch, MIMS, vLLM, or Postgres later fails, the ledger still shows exactly where the workflow failed.

Business outcome

This strengthens auditability and review trust. A translational oncology review packet must be traceable from raw file to every downstream artifact, including failed or incomplete runs.

Acceptance criteria

The raw file is persisted first. The source file record is written to Postgres before extraction starts. The upload ledger event is written before extraction starts. Each major stage writes a started, succeeded, or failed event. A failed run can still be inspected. No failure is hidden behind a polished partial packet.

Tutorial 5 — Move OpenSearch earlier into the workflow
Gap being fixed

OpenSearch is currently used mostly as persistence after the review packet is built. But the intended MVP architecture requires OpenSearch to be the retrieval and evidence layer before artifact generation.

What the code should do

After document extraction and section-aware chunking, chunks should be indexed into OpenSearch immediately. Artifact generation should retrieve relevant chunks from OpenSearch by task: report extraction, biological relevance, molecular-fit review, mechanism reasoning, confirmatory testing, tumor-behavior modeling, and narrative containment.

Intended runtime behavior

The clinical compiler should not operate on a raw in-memory blob alone. It should ask OpenSearch for source chunks and evidence context. Each artifact should be generated from retrieved chunks and evidence, then indexed back into OpenSearch as it is created.

Business outcome

This makes Translume a real evidence-grounded review system rather than a one-pass summarizer. It also creates reusable indexed artifacts for future review, validation, and longitudinal modeling.

Acceptance criteria

Document chunks are indexed before report extraction. Artifact generation receives retrieved chunks, not just raw page text. Retrieval is filtered by case ID and session ID. Retrieved chunks include source text and provenance. Every generated artifact is indexed after validation. Empty retrieval fails or produces explicit missing-evidence artifacts, not hallucinated content.

Tutorial 6 — Convert clinical artifact generation to local vLLM structured outputs
Gap being fixed

The current production workflow still calls deterministic or rule-based functions for clinical artifacts. That violates the stated architecture where clinical artifacts must be generated through local vLLM structured outputs and validated schemas.

What the code should do

Create a structured artifact generation pipeline that calls LocalVLLMProvider for each major artifact. It should generate ReportExtractionOutput, MolecularPhenotypeOutput, TherapyEvidenceMatrixOutput, MechanismSankeyOutput, ConfirmatoryTestingOutput, TumorBehaviorModelOutput, ClaimEvidenceOutput, and ClinicalNarrativeCompilerOutput using JSON-schema constrained generation. Deterministic code should remain only for validation, source alignment, safety checks, provenance, ledger events, and persistence.

vLLM structured-output behavior must rely on schema-constrained generation with the structured-output backend enabled.

Intended runtime behavior

Each artifact is generated by the local model from source chunks and evidence context. The raw model output is rejected unless it validates against the expected schema. If the model returns unsupported clinical statements, the output fails containment or is marked as missing evidence or needs review.

Business outcome

This turns Translume into a real clinical output compiler rather than a hardcoded template engine. It allows the output to change dynamically when the uploaded report and evidence change.

Acceptance criteria

Every clinical artifact is generated through the local vLLM provider in the production path. Every artifact validates against its schema. Every artifact passes safety checks. Every artifact has artifact-specific provenance. Rule-based clinical interpretation functions are removed from the production path. Tests prove two different report fixtures produce different artifacts.

Tutorial 7 — Make report extraction source-grounded and model-driven
Gap being fixed

Current report extraction uses hardcoded extraction heuristics and clinical-ish rules. Some extraction helpers are acceptable for source alignment, but clinical extraction itself should be model-driven and schema-constrained.

What the code should do

The report extraction function should retrieve section-aware chunks from OpenSearch, send those chunks to local vLLM with the ReportExtractionOutput schema, validate the output, and then source-align each molecular finding back to the source chunks. Any unsupported finding should be downgraded to low confidence and marked for review.

Intended runtime behavior

The extraction output should reflect what the report actually says. If a finding cannot be traced to source text, it should not be treated as a confident patient-specific finding.

Business outcome

This creates the first trust checkpoint: the clinician can see what Translume thinks the report found before any interpretation occurs.

Acceptance criteria

Every molecular finding has source page and source text when available. Every finding is marked human-reviewable. Negative findings and limitations are captured. Research-use-only signals are labeled as such. Unsupported findings are low confidence. No graph, literature, or treatment inference appears in report extraction.

Tutorial 8 — Replace generic OptimusKG edge-file loading with real OptimusKG usage
Gap being fixed

The current OptimusKG service imports OptimusKG but mostly loads generic CSV, JSON, or JSONL edge files discovered by filename. That is too close to a graph-like substitute.

What the code should do

The OptimusKG adapter should call the real OptimusKG package or documented data-loading path. If OptimusKG exposes Parquet/dataframe loading, the adapter should use that. It should query neighbors or paths for normalized entities, normalize real nodes and edges into GraphEvidenceArtifact, and fail if OptimusKG data or cache is unavailable.

Intended runtime behavior

When report entities are normalized, the OptimusKG service retrieves real biomedical graph context for those entities. Missing graph context is recorded explicitly. Generic local edge-file discovery is not used in the production path.

Business outcome

This gives the tumor-behavior model graph-derived biomedical context instead of relying only on local model interpretation.

Acceptance criteria

The service imports real OptimusKG code. It loads graph data through a real OptimusKG-supported path. It returns graph nodes, edges, paths, relation types, and provenance. It fails if the graph data is unavailable. It does not read arbitrary edge-like files as a substitute for OptimusKG.

Tutorial 9 — Configure all required ToolUniverse workflows
Gap being fixed

ToolUniverse is wired, but only a narrow workflow appears configured. The MVP requires broader evidence coverage.

What the code should do

Create explicit workflow configuration for literature validation, pathway context, target context, variant context, and trial-context review. Each workflow must map to a real ToolUniverse tool, define input mapping from normalized entities and graph evidence, define output normalization into ToolRunArtifact, and define failure behavior.

Intended runtime behavior

When the compiler needs evidence, it calls only configured ToolUniverse workflows. If a workflow is not configured, the system fails or records an explicit unavailable workflow. It never runs arbitrary tools.

Business outcome

This makes evidence cards more credible and reduces manual literature/tool review burden for difficult oncology cases.

Acceptance criteria

All required workflows are configured or explicitly marked unavailable. Unconfigured workflow calls are rejected. Every tool call is logged. Every tool output is normalized and indexed in OpenSearch. Tool output never enters the narrative directly. Unsafe tool output is rejected or quarantined.

Tutorial 10 — Prove Medea local runtime and block remote provider escape
Gap being fixed

Medea is wired but unproven at runtime. It must be shown to import, execute, route through local vLLM, avoid remote model providers, and normalize output.

What the code should do

Add a Medea runtime contract test in the live VM validator. The Medea service should accept an evidence context bundle, run bounded literature or omics reasoning, route all model calls through local vLLM, block remote provider credentials, and return a schema-valid MedeaReasoningArtifact.

Intended runtime behavior

Medea should support Translume’s reasoning but not drive the final answer directly. If Medea cannot run locally, the system must report the failure clearly and block final MVP-grade packet generation if Medea is required.

Business outcome

This adds real omics/literature reasoning support while preserving safety and clinician review.

Acceptance criteria

Medea imports successfully in its container. Medea dependencies install successfully. Medea receives local vLLM configuration. Remote provider variables are blocked. A real /reason request returns a non-empty schema-valid reasoning artifact. Runtime logs show no remote model API usage. Failure is explicit if Medea cannot run.

Tutorial 11 — Generate tumor behavior dynamically from evidence
Gap being fixed

The current tumor behavior logic includes hardcoded state transitions, especially a default proliferative to stress-adapted survival transition. This violates the no-hardcoded-clinical-conclusion rule.

What the code should do

Tumor behavior generation should become a local vLLM structured-output artifact that consumes the report extraction, normalized entities, graph evidence, ToolUniverse outputs, Medea reasoning, molecular phenotype, molecular-fit matrix, and confirmatory gaps. The allowed state vocabulary can remain fixed, but selected states, state evidence, transition hypotheses, rationales, supporting artifacts, confidence labels, and validation status must be case-derived.

Intended runtime behavior

Different reports should produce different tumor-state hypotheses. If evidence does not support a state or transition, the model should mark missing evidence rather than invent a transition.

Business outcome

This is the core Translume differentiation: the report becomes a reviewable disease-behavior model, not just a variant summary.

Acceptance criteria

Every state has supporting evidence or explicit missing evidence. Every transition references supporting artifacts. No transition probability is generated. No outcome prediction is generated. No treatment recommendation is generated. Two unrelated report fixtures do not produce identical tumor-behavior transitions unless their evidence truly supports the same structure.

Tutorial 12 — Add artifact-specific provenance everywhere
Gap being fixed

Current provenance exists but is too generic. It does not fully prove which model, schema, prompt, source chunks, and source artifacts produced each artifact.

What the code should do

Each artifact should receive artifact-specific provenance at creation time. Provenance should include artifact ID, artifact type, schema name, model name, prompt hash, schema hash, source file ID, source chunk IDs, source artifact IDs, created timestamp, validation status, and generation status.

Intended runtime behavior

When a reviewer sees a claim, matrix row, Sankey link, tumor-behavior state, or narrative sentence, the system can trace it to source chunks, graph evidence, tool outputs, Medea reasoning, model generation, and human validation.

Business outcome

This creates reusable institutional memory and makes future Markov/state modeling possible because every reasoning unit is traceable.

Acceptance criteria

Every artifact has specific provenance. Generic values like “translume_mvp” or “deterministic_compiler_or_external_provider” are removed from production artifacts. Provenance is persisted to Postgres and indexed in OpenSearch. Export includes provenance for every artifact. Missing provenance fails production validation.

Tutorial 13 — Enforce narrative fact containment
Gap being fixed

Narrative containment exists but is not enforced before returning or persisting the final narrative.

What the code should do

After generating the final narrative, the workflow should validate that all genes, alterations, biomarkers, mechanisms, therapy-context terms, and major claims appear in the structured artifacts or retrieved evidence. Unsupported content should either fail the narrative or be transformed into explicit missing-evidence claim cards requiring review.

Intended runtime behavior

The final narrative becomes a readable rendering of the review packet, not a freeform chatbot answer. It cannot introduce new clinical facts without structured support.

Business outcome

This preserves trust and prevents the most dangerous failure mode: a polished explanation containing unsupported claims.

Acceptance criteria

Narrative containment is called in the production path. Unsupported entities are flagged. Unsupported claims are rejected or marked missing evidence. The final narrative cannot be returned if it introduces unsupported treatment claims. Containment results are recorded in provenance or ledger events.

Tutorial 14 — Decide and enforce the vector retrieval scope
Gap being fixed

OpenSearch mappings include an embedding field, but embeddings are not generated and indexed in the production path. That means vector/HNSW retrieval should not be claimed as real yet.

What the code should do

Either implement real local embedding generation and vector indexing, or explicitly scope the MVP to lexical OpenSearch retrieval until embeddings are added. Under PRIME_DIRECTIVES, the code and docs must not claim vector retrieval unless embeddings are actually generated and used.

Intended runtime behavior

If vector retrieval is enabled, every indexed chunk has an embedding with the configured dimension. If vector retrieval is disabled, retrieval uses lexical and metadata filters only, and the UI/docs say so honestly.

Business outcome

This avoids overclaiming. It keeps the demo honest while preserving a clear upgrade path.

Acceptance criteria

If vector retrieval is enabled, embedding generation is real and tested. If vector retrieval is disabled, no HNSW/vector claims appear in README, UI, or validation reports. OpenSearch queries report their retrieval method. Missing embeddings cannot silently pretend vector search is active.

Tutorial 15 — Replace JSON-centric UI with clinical artifact panels
Gap being fixed

The UI currently appears too JSON-centric. It is functional but not yet a persuasive clinical review surface.

What the code should do

Add real renderers for extracted findings, normalized entities, graph/evidence context, molecular phenotype, molecular-fit matrix, mechanism Sankey, confirmatory tests, tumor-behavior states and transitions, claim validation cards, narrative, and ledger export. These renderers must display actual API-returned artifacts, not local demo content.

Intended runtime behavior

A clinician should see the review packet in the same order they think: what was found, what it maps to, what evidence supports it, what mechanisms are plausible, what should be validated, how the tumor may behave, and what claims need review.

Business outcome

This makes the demo valuable. Translume’s buyer needs a fast clinical review surface, not a raw JSON explorer.

Acceptance criteria

The UI renders artifact tables and visualizations from live API data. No renderer uses hardcoded example rows. Validation actions call real API endpoints. Export button returns the persisted packet. UI shows missing service/evidence errors clearly.

Tutorial 16 — Run live VM validation and repair the first failure
Gap being fixed

Unit tests prove local code behavior but not full runtime behavior. The MVP must be proven on a real VM with Docker, GPU, vLLM, Docling, OpenSearch, Postgres, and MIMS services.

What the code should do

The live VM validation command should start the full stack, run health checks, upload a real oncology PDF, verify all required artifacts, validate OpenSearch/Postgres persistence, validate MIMS execution, validate local vLLM structured outputs, test claim validation, and export the final review packet. It should produce JSON and Markdown diagnostics.

Intended runtime behavior

The operator runs one command and receives a clear pass/fail report. If anything fails, the report identifies the exact failed service, stage, command, or artifact.

Business outcome

This is the final proof step before calling the MVP demo-ready.

Acceptance criteria

The validator runs against real Docker containers. It checks GPU/vLLM availability. It checks Docling, OpenSearch, Postgres, OptimusKG, ToolUniverse, Medea, FastAPI, and Gradio. It uploads a real PDF. It verifies all required artifacts exist. It applies a validation decision. It exports the review packet. It does not pass if any required service is missing or fake.

Final corrected build order

The implementation order should be:

First, fix the Gradio Docker launch so the UI can actually start. Second, replace zip-extracted MIMS directories with real git clones and add a vendor-status gate. Third, add the PRIME_DIRECTIVES production config gate so fake product paths cannot start. Fourth, persist session and upload metadata before any processing begins. Fifth, move OpenSearch chunk indexing before artifact generation. Sixth, convert all clinical artifacts to local vLLM structured outputs. Seventh, enforce narrative containment in the production path. Eighth, replace OptimusKG generic edge-file loading with true OptimusKG data/client usage. Ninth, configure the required ToolUniverse workflows. Tenth, prove Medea local runtime and remote-provider blocking. Eleventh, generate tumor-behavior states and transitions dynamically from evidence. Twelfth, add artifact-specific provenance everywhere. Thirteenth, decide and enforce vector retrieval scope. Fourteenth, render real clinical artifacts in the UI. Fifteenth, run live VM validation and repair the first runtime failure until the full path passes.

What success means

Success means a real user can upload an oncology report and receive a review packet generated from real source text, real document extraction, real OpenSearch retrieval, real local vLLM structured outputs, real MIMS evidence services, real clinical artifacts, real validation controls, and real Postgres/OpenSearch persistence.