# Dynamic Pathway Analyzer

This CPU service continues the existing downstream report workflow. It reads the
precision pipeline's trial-prescreen state, normalizes the case, researches
pathways, creates the pathway report, and synthesizes the tumor-board summary.
All five model stages use the official OpenAI Responses API with Astra Pro:
normalization, authoritative search, open-web research, report compilation, and
no-web tumor-board synthesis.

## Run with the complete application

1. Follow the repository-root `README.md` to install Docker and start the stack.
2. Put your actual OpenAI project key in the root `.env` as `OPENAI_API_KEY`.
3. Enter the diagnosis and upload the real report in the UI. The main API invokes
   the precision runner, this analyzer, and the tumor-board synthesizer.
4. Review the **Pathway analysis** tab and download the generated report.

The service writes the following under `data/artifacts/<session_id>/`:

- `pathway_output_comprehensive/<run_id>/`: pathway JSON, Markdown, normalized
  case, research memo, consulted sources, and an OpenAI manifest.
- `tumor_board_output/<run_id>/`: `onco_board_summary.md`, its manifest, and
  per-attempt OpenAI receipts.

Both output directories retain `openai_calls/` receipts for successful and
failed attempts, with actual request/response IDs and usage where available.
No credentials or model input text are written into those receipts.

Inspect the service from the repository root:

```bash
docker compose logs --tail=200 dynamic-pathway-analyzer
```

Display the two command interfaces inside Docker:

```bash
docker compose exec --user analyzer dynamic-pathway-analyzer \
  python /app/dynamic_pathway_analyzer.py --help

docker compose exec --user analyzer dynamic-pathway-analyzer \
  python /app/tumor_board_causal_synthesis.py --help
```

## Model settings

Defaults:

```dotenv
OPENAI_REASONING_MODEL=gpt-6-astra
OPENAI_NORMALIZER_MODEL=gpt-6-astra
OPENAI_REASONING_MODE=pro
OPENAI_REASONING_EFFORT=xhigh
OPENAI_REQUEST_TIMEOUT_SECONDS=900
DYNAMIC_PATHWAY_RUN_TIMEOUT_SECONDS=7200
```

The CLI supports `--model`, `--reasoning-mode`, `--reasoning-effort`,
`--request-timeout`, `--max-attempts`, and `--max-output-tokens`.
The analyzer additionally supports `--normalizer-model`. The internal runner
passes the same environment values to both commands. A nonofficial inference
endpoint or standard mode fails validation before a model call.

Every request sends `store=False` and an explicit output-token allowance.
The wrapper is the only retry owner; SDK automatic retries are disabled.
A token-limit response can receive one larger bounded allowance. Credential,
permission, quota, refusal, filtering, and domain-validation failures are
terminal. Partial output is never returned as a finished report.

## Source handling

The public-search payload includes disease/histology, relevant molecular
concepts, and pathway identifiers. It excludes dates, location, specimen details,
patient history, source quotations, patient-specific narrative, and generated
free-form queries. The finalizer still receives the full normalized case.
Field minimization does not guarantee that user-supplied free text contains no
identifying information.

The two research calls request actual hosted web searches and retain consulted
source metadata. The tumor-board stage has no search tool: it receives only the
completed pathway analysis and research memo. Missing inputs, absent model
output, and unsuccessful searches fail explicitly instead of creating evidence.
The original domain models, source URLs, evidence tiers, uncertainty, and
human-review requirements are retained.

## Runtime modules

- `dynamic_pathway_analyzer.py`: evidence discovery, normalization, research,
  structured report validation, and deterministic Markdown rendering.
- `tumor_board_causal_synthesis.py`: bounded synthesis using the two completed
  Markdown documents.
- `openai_runtime.py`: official endpoint validation, strict wire schemas,
  completion/refusal handling, bounded retries, receipts, and atomic writes.
- `dynamic_pathway_runner.py`: session-scoped HTTP orchestration with finite
  subprocess deadlines and redacted diagnostics.

No module loads or executes a local language, embedding, vision, or reranking
model. The source includes isolated unit tests; the runtime does not use their
fixtures or simulate remote completions.
