# Validation record

Validation date: 2026-11-08

## Checks executed

The precision-oncology suite was run against OpenAI SDK 2.54.0 and Pydantic
2.14.3:

```sh
python -m pytest tests/test_pipeline.py tests/test_runner.py tests/test_openai_remote_runtime.py -q -o addopts='' --tb=short
```

Result: **38 passed**. Ruff checks also passed for both runtime modules and
their tests. Schema generation using `--emit-schema-only` succeeded.

The companion dynamic-pathway and tumor-board suite passed **21 tests**, and
the repository's downstream container contract checks passed **3 tests**.

## What these checks establish

The tests use the actual OpenAI SDK with an HTTPX mock transport at the network
boundary. They verify the serialized request's official endpoint, API-key
header, Astra model, Pro reasoning mode, effective reasoning effort,
`store=False`, strict JSON schema, and finite output limit. They exercise
successful pipeline assembly, domain validation, per-attempt usage receipts,
cache identity, bounded transient retries, and terminal handling of
authentication errors, insufficient quota, refusals, and incomplete responses.

The runner tests cover model-setting propagation, process deadlines, persisted
precision-pipeline failure diagnostics, and safe health responses. The container
contract tests inspect the deployment files; they do not execute Docker.

Mock API responses are test fixtures only. The production pipeline has no fake
provider, sample-response substitution, or local-model fallback.

## Verification still required on the deployment machine

No live OpenAI request or Docker build was executed in this environment: it
contained neither an OpenAI API key nor a Docker CLI/daemon. These checks do not
establish account model access, billing availability, provider latency, image
build success, or scientific accuracy of a generated report.

Follow the root README to build the containers, configure a real API key, upload
a real report, and run the full-stack verification command. Preserve the emitted
response IDs, usage receipts, and verification output as the evidence for that
live run. Do not treat `--dry-run` or `--quick-test` as full workflow verification.
