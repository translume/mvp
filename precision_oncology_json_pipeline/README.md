# Precision Oncology JSON Pipeline

This service takes the persisted Translume review packet, retrieves current
external evidence through OpenAI hosted web search, and compiles the existing
structured precision-oncology report. Every model request goes to the official
OpenAI Responses API. The container performs ordinary CPU data processing and
filesystem I/O; it does not load model weights.

## Run through the application

1. Follow the repository-root `README.md` to install Docker, create `.env`, and
   start the stack.
2. Set `OPENAI_API_KEY` in the root `.env` to your actual OpenAI project key.
   The same key is used by all model services. Do not create a separate
   downstream key or put a key in source code.
3. Open the Translume UI, enter the diagnosis, upload the real report, and
   generate the persisted review packet. The API invokes this runner and then
   the dynamic pathway analyzer automatically.
4. Review the output in the UI. Generated files remain under
   `data/artifacts/<session_id>/precision_oncology_outputs/<run_id>/`.

From the repository root, inspect this service with:

```bash
docker compose logs --tail=200 precision-oncology-pipeline
```

Display the standalone command's supported arguments inside Docker:

```bash
docker compose exec --user pipeline precision-oncology-pipeline \
  python /app/precision_oncology_pipeline.py --help
```

## OpenAI configuration

The defaults are `OPENAI_REASONING_MODEL=gpt-6-astra`,
`OPENAI_REASONING_MODE=pro`, and `OPENAI_REASONING_EFFORT=xhigh`. The CLI accepts
`--model`, `--reasoning-mode`, and `--reasoning-effort`; the runner forwards the
same values from the environment. Pro mode is required. The official endpoint
is `https://api.openai.com/v1`; local and third-party inference URLs are rejected.

The existing prompts retain their deliberate per-stage effort choices:
source extraction uses low effort, clinical generation uses medium effort,
and validator stages use high effort. All of these run in Pro mode. Each call
records its actual effort. On output-token exhaustion the gateway permits one
larger output allowance at low effort. A report-compiler timeout permits one
compacted low-effort request. Neither response can be cached as if it were the
original request.

`PRECISION_ONCOLOGY_REQUEST_TIMEOUT_SECONDS` controls the runner's request
limit (900 seconds by default). The report compiler retains a 900-second
stage limit. `PRECISION_ONCOLOGY_RUN_TIMEOUT_SECONDS` limits the complete
subprocess (10,800 seconds by default). An exceeded limit fails the run and
persists a diagnostic; it does not create a successful report.

## Report, cache, and provenance

The pipeline preserves canonical findings, hypotheses, research jobs, real
consulted URLs, source extractions, evidence-fit assessments, trial prescreens,
report sections, validations, and final renderer-independent JSON. The dynamic
analyzer consumes `state_after_trial_prescreens.json` from the completed run.
The final precision JSON is `precision_oncology_packet.json`.

`calls/` contains a request summary and a separate receipt for every actual
attempt, including failures. Receipts contain provider/model, mode, effective
effort, wire-schema and request hashes, actual request/response IDs, completion
state, and usage when OpenAI returned it. Input text and credentials are excluded
from these receipts. The optional `--store-prompt-payloads` flag separately
persists complete inputs and should be used only when intended.

Cache identities include provider, model, mode, effective effort, prompt content,
wire schema, output allowance, input payload, and web-search settings. Earlier
standard-mode caches cannot satisfy Pro requests. Cache hits are explicitly
marked and do not count as new API attempts.

Public web-search requests receive an explicit biomedical subset of the case.
Raw source quotations, specimen details, dates, location, and patient history
remain out of the search payload. Full case context remains available to the
non-web evidence-fit, prescreen, and final report stages. This field minimization
is not a de-identification guarantee for free-text medical concepts.

## Failures and validation

Only transient network, rate-limit, and server failures are retried. Invalid
credentials, exhausted quota, permissions, malformed requests, refusals,
content filtering, and failed domain validation stop explicitly. Responses are
checked for completed status before any JSON is accepted. Partial JSON is never
used as a report.

The production path has no simulated response mode. `--dry-run` only writes
parsed canonical input and deliberately stops before model generation. Tests
use isolated test fixtures and HTTP transports; those fixtures are never loaded
by the product workflow. Live acceptance still requires a configured OpenAI
account and a real source report.

The outputs support qualified human review; clinical uncertainty, evidence
boundaries, source provenance, and the existing clinician-review requirements
remain part of the report.
