# Phase 7 Performance Controls

Phase 7 adds execution controls around the existing decision-brief pipeline without changing clinical semantics.

## What changed

- Independent post-tumor-behavior model stages now run concurrently when their inputs are ready.
- Graph, ToolUniverse, and Medea provider lookups use an async in-memory cache with request coalescing.
- Async workflow stages can enforce configurable latency budgets.
- Decision-brief prompt stages can enforce per-stage latency budgets.

## Runtime knobs

- `TRANSLUME_ENABLE_PROVIDER_CACHE=true|false`
- `TRANSLUME_GRAPH_CACHE_TTL_SECONDS=3600`
- `TRANSLUME_TOOL_CACHE_TTL_SECONDS=1800`
- `TRANSLUME_MEDEA_CACHE_TTL_SECONDS=1800`
- `TRANSLUME_ASYNC_STAGE_LATENCY_BUDGET_SECONDS=<seconds or empty>`
- `TRANSLUME_DECISION_BRIEF_STAGE_LATENCY_BUDGET_SECONDS=<seconds or empty>`
- `TRANSLUME_STAGE_LATENCY_BUDGETS_SECONDS=stage=seconds,decision_brief.current_tumor_state=seconds`

Empty latency values disable enforcement. Cache TTL values of zero or less disable storage for that cache path.

## Safety behavior

Performance caching is used only for deterministic provider inputs. Cache misses still call the real provider. Provider failures are not cached. Latency-budget failures are recorded as workflow failures and do not produce placeholder clinical artifacts.
