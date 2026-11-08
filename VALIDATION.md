# Validation record for the OpenAI/CPU migration

## Executed checks

The code was tested in a fresh isolated Python 3.12.14 environment installed from `docker/test-requirements.txt` with dependency hash enforcement. The environment did not inherit system Python packages.

| Check | Observed result |
| --- | --- |
| Main application suite | 424 passed, 1 live-integration test skipped |
| Precision-oncology suite | 38 passed |
| Dynamic pathway and tumor-board suite | 21 passed |
| Total passing tests across the three suites | 483 |
| Final API upload and integration-contract check | 14 passed, 1 live test skipped |
| Application/service imports in the clean environment | 9 entry points imported successfully |
| Installed local ML packages | None from the prohibited package set |
| Workspace dependency lock | `uv lock --check` passed; 111 resolved packages |
| Bundled vendor archives and installed sources | All three archive/source snapshots verified |
| Boundary and changed-code lint | New OpenAI/document/Medea/downstream/orchestration boundary checks passed; changed root imports and undefined-name checks passed |

The full test log is included at `validation/unit-tests.txt`. Unit tests use controlled response fixtures and explicit test doubles. They check serialization, error handling, actual source-code integration, schema constraints, source IDs, audit metadata, cancellation, and orchestration. No controlled response is used by a production entry point, and these tests are not described as live OpenAI runs.

The opt-in integration test now invokes the actual `run_full_stack_integration` workflow when explicitly enabled. It does not pass merely because an environment flag is present. The documented `verify` container performs the same real integration directly.

## Actual public-source checks

- Europe PMC returned real results for the non-patient query `MTAP sarcoma`: 692 hits and 8 parsed abstracts. Semantic Scholar returned HTTP 429 and was recorded as unavailable.
- HTTP Range requests to the official MedeaDB files confirmed the gene index is a Unicode array with 18,443 entries. The three DepMap matrices have shape 18,443 by 18,443 and float32 storage; each is 1,360,577,124 bytes. The upstream parser supports their native memory mapping. Only headers were fetched here; the complete multi-gigabyte dataset was not downloaded.
- The actual bundled ToolUniverse source instantiated all ten configured external biomedical tools without loading local ML libraries. The local Reactome graph-backed tool requires its database container and was not exercised live.
- The actual unchanged Medea `GeneCorrelationLookup` and `OpenScholar` modules loaded through the narrow import boundary. Tests exercised their actual behavior with small local source-data fixtures and controlled OpenAI responses.
- Harvard Dataverse metadata for the official OptimusKG DOI `doi:10.7910/DVN/IYNGEV` returned HTTP 403 with an HTML Forbidden response from this environment. The public dataset page also presented automated-access verification during web retrieval. The canonical DOI and client URL were confirmed; no alternate or fabricated dataset was substituted.

## Not executed here

This environment has no Docker CLI/daemon and no supplied OpenAI API credential. Therefore the following remain **unverified**, not passed:

- Building or starting the actual Docker images and Compose stack.
- A live paid Astra Pro Responses request, remote token-count request, or embeddings request.
- Complete reference-data provisioning, including the blocked Dataverse transfer.
- A real oncology PDF processed through all live services into a final report.
- Laptop RAM/latency benchmarks and Apple Silicon emulation of the amd64 Reactome image.
- Clinical/research equivalence of embedding cosine reranking to the previous local cross-encoder.

The Docker images use Python 3.12.13-slim; the executed Python environment was 3.12.14. The hash-pinned Python dependency set installed successfully, but this is not a claim that an image build was executed.

## Real acceptance command

Follow `README.md` to start the services with your actual API key. Place your real PDF at `data/input/report.pdf`, set its report type and actual diagnosis in `.env`, then run:

```sh
docker compose --profile verification run --rm verify
```

The verifier makes actual Astra Pro and embedding calls, processes the actual PDF, checks service and persistence behavior, validates remote-call receipts, preserves a `needs_review` review status, and requires all three downstream reports. A zero exit code with `"status": "ok"` is the acceptance result. Authentication, quota, data download, schema, provider, or report failures exit nonzero and retain actionable diagnostics.

If Dataverse access is blocked on the target laptop, restore access to the official dataset before expecting setup to complete. The application does not mark missing scientific data as ready.
