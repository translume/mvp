# Local Reactome GraphDB ToolUniverse Override

Translume keeps the governed ToolUniverse name `ReactomeContent_search` but
executes that exact step against a release-pinned Reactome Neo4j graph on the
private Compose network. `PathwayCommons_search` and `kegg_search_pathway`
continue through the vendored ToolUniverse engine. No Reactome HTTP fallback is
available.

## Runtime flow

```text
pathway_context
  -> ToolUniverseRuntime.run_workflow_step
  -> ReactomeContent_search exact-name override
  -> Neo4jReactomeSearchBackend
  -> bolt://reactome-graphdb:7687
  -> ToolUniverse-compatible data and metadata
```

The local adapter supports Homo sapiens pathways, pathway name/stable-ID
search, and normalized gene entities. Alteration prose is never treated as a
gene identifier. Results are deterministic, bounded to 30 public entries, and
carry `remote_api_used: false` provenance.

## Readiness and failure behavior

`tooluniverse-service` owns one runtime and Neo4j driver pool per Uvicorn
worker. Its `/health` endpoint returns HTTP 503 until the vendor tools,
workflow catalog, GraphDB connection, positive pathway count, and configured
Reactome release are all valid. GraphDB failures fail loudly and never fall
back to Reactome ContentService or download hosts.

Neo4j ports 7474 and 7687 are exposed only inside Compose. Passwords are not
included in configuration representations, health payloads, or search logs.

## Release validation and rollback

For every `Release<N>` upgrade, set matching image and release values, pull the
image, verify credentials/database/release/schema, compare bounded traversal
with a diagnostic query, measure warmed latency, and run `make reactome-smoke`.
Rollback restores the prior matching image/release values and force-recreates
`reactome-graphdb` and `tooluniverse-service`. V1 deliberately has no GraphDB
data volume, preventing an older database from masking a new image tag.
