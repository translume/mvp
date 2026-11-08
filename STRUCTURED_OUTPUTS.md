# OpenAI structured outputs

## Request contract

The application uses the official OpenAI Responses API. The default request model is `gpt-6-astra`, with `reasoning.mode=pro` and configured effort. Structured JSON uses `text.format` with `type=json_schema`, a schema name, `strict=true`, and the sanitized wire schema. Requests also set `store=false` and an explicit `max_output_tokens`.

The SDK is used by the downstream runners; the shared application boundary uses authenticated HTTPX requests to the same official endpoints. Neither boundary permits a local OpenAI-compatible endpoint.

## Schema conversion

The wire schema closes objects with `additionalProperties=false`, requires every wire property, expresses nullable fields explicitly, and preserves supported bounds and references. Application Pydantic models remain the semantic validation layer. Unsupported annotations are removed only from the wire schema; the internal domain schema is not weakened to accept an invalid clinical artifact.

The source code owns deterministic identifiers and source alignment. Generated outputs must refer to allowed source chunks, findings, graph/tool artifacts, and evidence. Invalid citations are errors, not silently invented source records.

## Context and output budgets

Before generation, the shared provider calls `/v1/responses/input_tokens` with the final request's prompt, instructions, wire schema, and reasoning configuration. Input count plus reserved output and safety margin must fit the configured operational context budget. This budget is intentionally conservative.

Report extraction measures complete candidate requests, batches source chunks, and recursively splits oversized or output-truncated batches within explicit depth limits. Leaf results are validated and merged deterministically. No source batch is dropped to make the count fit.

An incomplete response is never accepted as completed JSON. An output-token-limit failure may receive one larger bounded output attempt, or a source-preserving split where that stage supports splitting. Content filters, refusals, authentication failures, and quota failures do not enter a clinical repair loop. Existing stage-specific effort overrides in the downstream precision pipeline are retained and recorded as the effective request settings.

## Receipts and provenance

Each actual attempt has request/schema hashes, timing, status, configured model/mode/effort, observed model and response/request IDs when returned, and token usage. These receipts are attached to generated artifacts or their component provenance, and appended to the service audit journal. A failed request is recorded as failed; the requested model is not presented as an observed response model.

Task-local capture scopes isolate concurrent artifact generation. Document extraction retains its receipts even if the native-text candidate is selected after quality evaluation. Source-page identities are stable; the converter does not fabricate bounding boxes or confidence scores.

## Embeddings

The embedding adapter calls `/v1/embeddings` using `text-embedding-3-large` and configured dimensions. It rejects empty inputs, oversized inputs/batches, missing or duplicate indices, wrong vector lengths, non-finite values, and mismatched model responses. Its conservative input sizing uses UTF-8 byte bounds instead of loading a local tokenizer. CPU cosine comparison of returned vectors performs ranking without any local learned model.

## Relevant code

- `packages/translume-clients/src/translume_clients/openai_client.py`
- `packages/translume-adapters/src/translume_adapters/model_providers/openai_provider.py`
- `packages/translume-adapters/src/translume_adapters/embedding_providers/`
- `packages/translume-schemas/src/translume_schemas/model_calls.py`
- `packages/translume-core/src/translume_core/compiler/`
- `services/docling-service/src/docling_service/`
- `services/medea-service/src/medea_service/`
- `precision_oncology_json_pipeline/precision_oncology_pipeline.py`
- `dynamic_pathway_analyzer/openai_runtime.py`

## Official API references

- [Reasoning guide](https://platform.openai.com/docs/guides/reasoning)
- [Structured outputs](https://platform.openai.com/docs/guides/structured-outputs)
- [Responses API](https://platform.openai.com/docs/api-reference/responses)
- [Embeddings API](https://platform.openai.com/docs/api-reference/embeddings/create)

See `VALIDATION.md` for the distinction between executed request-contract tests and live API verification.
