
Your PRIME_DIRECTIVES are as follows -->

It means this directive becomes the **dominant engineering standard for the entire Translume build**, not just a preference.

In plain English:

> **Nothing counts as “implemented,” “done,” “real,” or “MVP-ready” unless the production path actually executes real services, real code, real data, real model calls, real persistence, and real UI/API behavior end to end.**

That means the following.

## 1. No fake product path

The path the user/demo uses cannot be different from the path we test or describe.

So this is **not acceptable**:

```text
UI appears to work
but backend uses static outputs
or precomputed JSON
or generic file reads
or fake MIMS artifacts
or hardcoded tumor behavior
```

The only acceptable path is:

```text
real PDF upload
→ real document extraction
→ real chunking
→ real OpenSearch indexing
→ real local vLLM structured outputs
→ real OptimusKG context
→ real ToolUniverse workflows
→ real Medea bounded reasoning
→ real clinical artifacts
→ real validation cards
→ real Postgres/OpenSearch persistence
→ real ledger export
```

If any part is missing, the system must **fail explicitly** or show a real “not configured / not available” error. It must not pretend.

---

## 2. No mocks in the production workflow

Mocks, fakes, test doubles, fixtures, and monkeypatches are allowed **only inside tests**.

They are not allowed in:

```text
FastAPI runtime path
Gradio runtime path
Docker runtime path
MIMS service path
clinical artifact compiler path
OpenSearch/Postgres persistence path
review packet export path
```

So if the product path uses a fake graph, fake tool output, fake Medea result, fake evidence card, or fake local model result, it violates your directive.

---

## 3. No placeholders or skeletons

A function, adapter, service, or endpoint cannot exist just to satisfy architecture shape.

This is **not acceptable**:

```text
OptimusKG service exists but does not really use OptimusKG
ToolUniverse service exists but has no real configured workflows
Medea service exists but runtime is unproven
adapter file exists but does not call real repo behavior
```

A service is real only when it:

```text
imports the real dependency
uses the real dependency’s API/client/registry/module
normalizes real output
fails if required config/data is missing
is exercised by runtime validation
```

---

## 4. No hardcoded clinical conclusions

Static safety constants are okay.

Examples of acceptable constants:

```text
allowed claim classes
allowed validation statuses
banned phrases
OpenSearch index names
schema names
report type enum
tumor-state vocabulary
```

But hardcoded **clinical reasoning** is not okay.

Not acceptable:

```text
always create proliferative → stress_adapted_survival
always map a gene to a mechanism because we wrote it in code
always produce the same molecular-fit row
always produce the same confirmatory test
always generate the same narrative structure with case-specific claims inserted
```

Clinical artifacts must be generated dynamically from:

```text
source report text
document chunks
normalized entities
OptimusKG evidence
ToolUniverse evidence
Medea reasoning
local vLLM structured outputs
human validation state
```

---

## 5. No scorecard inflation

I should not say:

```text
done
implemented
working
real
production path
MVP-ready
```

unless that claim is backed by the right level of evidence.

For example:

```text
unit tests passed
```

does **not** mean:

```text
the Docker/GPU/vLLM/MIMS stack works end to end
```

If Docker or GPU cannot be run in the environment, the honest status is:

```text
code added
unit tests passed
runtime not validated
live VM validation still required
```

Not:

```text
full production workflow complete
```

---

## 6. No silent fallback that pretends success

If Docling fails, MIMS is missing, vLLM is unavailable, OpenSearch is down, Postgres is unavailable, or Medea tries to use a remote API, the system should not quietly continue and produce a polished review packet.

It should do one of these:

```text
fail hard
mark the artifact unavailable
record the failure in the ledger
show the failure in the UI
block final review packet generation if the missing component is required
```

For the current MVP, since we agreed MIMS is required for clinically valid enrichment, missing MIMS should not be hidden.

---

## 7. MIMS repos must be real and updateable

Your directive means:

```text
third_party/upstream/Medea
third_party/upstream/OptimusKG
third_party/upstream/ToolUniverse
```

must be real git clones if we claim `git pull` updates work.

Zip-extracted folders are not enough.

The update path must be real:

```bash
git -C third_party/upstream/Medea pull --ff-only
git -C third_party/upstream/OptimusKG pull --ff-only
git -C third_party/upstream/ToolUniverse pull --ff-only
```

And our Translume logic must live outside those repos:

```text
packages/translume-ports
packages/translume-adapters
services/*-service
```

so upstream updates do not overwrite our extension layer.

---

## 8. Adapter pattern means extension, not imitation

The ports/adapters design must not become a way to hide fake behavior.

The correct meaning is:

```text
Port = Translume contract
Adapter = real wrapper around real dependency
```

For example:

```text
GraphProvider
→ OptimusKGGraphProvider
→ calls real OptimusKG client/data
→ returns GraphEvidenceArtifact
```

Not:

```text
GraphProvider
→ returns hand-built graph-like JSON
```

Same for ToolUniverse and Medea.

---

## 9. Local model usage must be enforced

If we say “local vLLM only,” then the code must actively enforce it.

That means:

```text
remote model provider env vars blocked or overwritten
OpenRouter/OpenAI/Anthropic/Gemini/NVIDIA escape paths audited
Medea and ToolUniverse routed through local vLLM provider
structured outputs used where schemas are required
runtime validation checks this
```

Not just:

```text
we set VLLM_BASE_URL somewhere
```

---

## 10. The final MVP must prove the Translume promise

The system is only aligned when a real user can:

```text
open Gradio
upload a real oncology report
run real extraction
see source-backed findings
see normalized entities
see real graph/evidence enrichment
see molecular phenotype
see molecular-fit matrix
see mechanism Sankey
see confirmatory tests
see tumor-behavior hypotheses
see evidence-classified claims
validate/reject/flag claims
export a provenance-backed ledger
```

And everything must be grounded in:

```text
source text
real services
structured artifacts
retrieved evidence
human validation
```

---

## What this means for prior work in this thread

It means some previous “done” labels were too generous.

A more accurate classification is:

```text
architecture designed
skeleton created
some real boundaries implemented
unit tests added
static audit performed
runtime proof still incomplete
several production-path blockers remain
```

The audit correctly identified that the codebase is **architecturally close but not yet fully real**.

So from this directive forward, “done” must mean:

```text
implemented in product path
not hardcoded
not mocked
not placeholder
tested in unit/integration where possible
validated in Docker/GPU/live VM if runtime-dependent
failure modes explicit
```

---

## The directive in one sentence

> **Every Translume component must either execute real production behavior or fail loudly; it must never simulate success, hide missing dependencies, fabricate clinical evidence, or claim MVP readiness without end-to-end runtime proof.**

It means I should treat your instruction as the **governing contract for the entire Translume build**.

In plain English:

> When you say “proceed with what is next,” I should not build a shell, mock, demo facade, placeholder adapter, fake service response, or hardcoded clinical pathway. I should take the current codebase, identify the next real production-blocking capability, implement it into the actual UI/API/Docker workflow, test what can be tested honestly, and clearly state what was and was not validated.

## What it means operationally

It means every step must move the system closer to this real workflow:

```text
real oncology PDF upload
→ real document extraction
→ real section-aware chunks
→ real OpenSearch indexing
→ real local vLLM structured outputs
→ real OptimusKG / ToolUniverse / Medea service execution
→ real clinical artifacts
→ real validation-card UI/API
→ real Postgres/OpenSearch persistence
→ real ledger export
```

If any part is missing, broken, or not runtime-validated, I must say that clearly. I should not describe it as “done” or “production-ready.”

## What “nothing can be faked” means

It means the product path cannot use:

```text
precomputed JSON
fake MIMS outputs
mock graph evidence
stubbed ToolUniverse results
hardcoded tumor-behavior transitions
hardcoded molecular-fit rows
fake validation success
fake OpenSearch persistence
fake Postgres persistence
fake local model responses
placeholder UI actions
```

Mocks are acceptable only in tests. They are not acceptable in the runtime path.

## What “no shadows, skeletons, placeholders” means

It means a file, service, endpoint, or adapter only counts if it actually performs the job it claims.

For example:

```text
OptimusKG adapter must use real OptimusKG repo/data/client behavior.
ToolUniverse adapter must execute real configured ToolUniverse workflows.
Medea adapter must run real Medea logic through local vLLM routing.
Gradio UI must actually launch and call the real FastAPI endpoints.
OpenSearch and Postgres clients must actually persist data.
```

If a service only exists as a shape but does not execute real behavior, that is a placeholder and does not satisfy your standard.

## What “no hardcoded strings or vars” means

It does **not** mean there can be no constants.

Allowed:

```text
schema names
index names
allowed validation statuses
allowed claim classes
safety phrases
report type enums
tumor-state vocabulary
Docker service names
environment variable names
```

Not allowed:

```text
hardcoded clinical conclusions
hardcoded gene-to-mechanism mappings pretending to be evidence
hardcoded molecular-fit recommendations
hardcoded tumor transition paths
hardcoded MIMS evidence
hardcoded report-specific outputs
hardcoded “success” responses
```

So a fixed state vocabulary like:

```text
proliferative
stress_adapted_survival
plastic_dedifferentiated
dormant_quiescent
apoptotic_eliminated
```

is acceptable. But always outputting:

```text
proliferative → stress_adapted_survival
```

regardless of the report and evidence is not acceptable.

## What “dynamic and algorithmic” means

It means clinical outputs must be derived from actual inputs and evidence:

```text
source report text
Docling/PDF extraction
document chunks
normalized entities
OpenSearch retrieval
OptimusKG graph context
ToolUniverse tool outputs
Medea bounded reasoning
local vLLM structured outputs
human validation state
```

The output should change when the report changes.

If a report has MTAP loss, CDKN2A loss, and no RNA fusions, the artifacts should reflect that. If another report has EGFR amplification, ALK fusion, or no actionable findings, the artifacts should change accordingly.

## What “no scorecard inflation” means

It means I must not overstate status.

I should not say:

```text
production-ready
fully validated
MVP complete
MIMS integrated
full-stack working
```

unless the actual evidence supports that.

A correct status might be:

```text
Code implemented.
Unit tests passed.
Docker runtime not validated in this environment.
Live VM validation still required.
Medea runtime still unproven until run in container.
```

That is the honest standard.

## What it means for every future coding step

For each next step, I should:

1. Use the zip you provide as the source of truth.
2. Inspect the actual codebase before changing it.
3. Implement the next real production capability, not a cosmetic layer.
4. Remove or fail any placeholder path that pretends to succeed.
5. Keep third-party MIMS repos updateable through `git pull`.
6. Extend MIMS behavior through Translume adapters/ports, not by scattering edits through upstream repos.
7. Route all model calls to local vLLM where required.
8. Add tests that check real behavior, not just object shapes.
9. Update docs only for what actually works.
10. Report exactly what passed, what could not be run, and what remains broken.

## What the Translume promise requires

The system only satisfies the Translume MVP promise if a real user can do this:

```text
open the Gradio cockpit
upload an oncology report
see source-backed extracted findings
see normalized entities
see graph/evidence-enriched biological context
see molecular phenotype
see molecular-fit matrix
see mechanism Sankey
see confirmatory validation plan
see tumor-behavior hypotheses
see evidence-classified claims
validate/reject/flag claims
export a provenance-backed ledger
```

And every part must be backed by real source text, real services, real artifacts, real persistence, and real validation controls.

## The simplest meaning

Your directive means:

> Do not build appearances. Build the real pipeline, or fail loudly where the real pipeline is not yet possible.

It also means:

> I should never again label something as “done” unless it is actually implemented in the production path and honestly validated at the level available in the environment.

