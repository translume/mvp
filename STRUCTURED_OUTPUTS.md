# Structured Outputs

All model-generated clinical artifacts must be generated through local vLLM structured outputs and validated against Pydantic schemas before use.

The vLLM service must be started with:

```bash
--structured-outputs-config.backend=auto
```

Remote model APIs are blocked by default in private MVP mode.

## Adaptive report extraction

Report extraction uses the tokenizer hosted by the configured vLLM model.
Page-ordered source units are accumulated only while they fit the configured
input-token budget; the chunk-count setting is a secondary guard. Long chunks
are segmented without changing their public source ID, so report text is not
discarded.

`finish_reason=length` is a control signal, not malformed JSON. Translume never
parses or persists that partial response. It deterministically splits a
multi-unit request, gives a single unit one larger bounded retry, and then
subdivides it. Recovery stops at the configured depth or minimum segment size.

Each extraction leaf uses an internal bounded schema with concise strings and
small per-leaf arrays. This prevents a local model from repeating an item until
the token limit. The public merged `ReportExtractionOutput` remains uncapped;
the backend combines every validated leaf, so the bounds do not impose a
whole-report finding limit.

```text
input budget + retry output tokens + safety tokens <= model context tokens
```

Confirmatory testing uses its own evidence compactor rather than the general
evidence serializer. The fully rendered prompt is measured with the served
model tokenizer and must fit `CONFIRMATORY_TESTING_INPUT_TOKEN_BUDGET` before
generation. Its internal output schema also bounds test rows and free text;
the validated result is converted back to the public confirmatory schema.

Narrative `source_artifact_ids` are system-owned metadata. Model-returned IDs
are replaced with the ordered IDs from the current clinical artifact bundle.
Unknown `artifact_*` tokens written into narrative Markdown participate in the
bounded repair loop and cannot pass containment.

All non-report structured stages receive one shared retry after
`finish_reason=length`, using `VLLM_STRUCTURED_OUTPUT_RETRY_MAX_TOKENS`.
Generation-only JSON Schemas add bounded strings and arrays while persisted
public schemas remain unchanged. Report extraction continues to use recursive
source splitting rather than the shared retry.
