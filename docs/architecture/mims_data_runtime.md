# Harvard MIMS data runtime

Translume uses two different Harvard MIMS data access patterns. Medea expects a
separately provisioned `MedeaDB` directory, while OptimusKG uses its Python
client to resolve and cache graph Parquet files from Harvard Dataverse. The
repository now provisions both patterns explicitly and mounts the resulting
host directories into the matching service containers.

## Provisioning commands

```bash
# Clone/update the upstream Git repositories and download both datasets.
make mims-data

# Download one dataset only.
make medea-data
make optimuskg-data

# Validate local files and OptimusKG Parquet schemas without downloading.
make mims-data-status
```

`make integration-full-stack-up` depends on `prepare-full-stack`, which depends
on `mims-data`. Downloads are therefore performed before Docker preflight and
container startup. Both upstream download mechanisms are cache-aware, so a
subsequent invocation reuses complete local files unless a force flag is set.

The complete MedeaDB snapshot is large. Ensure the data volume has enough free
space before running the target.

## Paths used by host code and containers

| Resource | Default host path | Container path | Runtime setting |
| --- | --- | --- | --- |
| MedeaDB root | `data/medea_cache/MedeaDB` | `/app/data/medea_cache/MedeaDB` | `MEDEADB_PATH` |
| OptimusKG client cache | `data/optimuskg_cache` | `/app/data/optimuskg_cache` | `OPTIMUSKG_CACHE_DIR` |

`docker-compose.yml` bind-mounts the exact host paths from `MEDEADB_PATH` and
`OPTIMUSKG_CACHE_DIR`. Medea's mount is read-only because the service only parses
the downloaded snapshot. OptimusKG's mount is writable so the upstream client
can refresh a missing file when explicitly allowed.

Override the host locations without changing the fixed paths seen inside the
containers:

```bash
make mims-data \
  MEDEADB_PATH=/data/translume/medea/MedeaDB \
  OPTIMUSKG_CACHE_DIR=/data/translume/optimuskg
```

`MEDEA_DATA_HOST_DIR` and `OPTIMUSKG_DATA_HOST_DIR` remain convenience variables
for deriving the Make defaults. The exact `MEDEADB_PATH` and
`OPTIMUSKG_CACHE_DIR` values take precedence and are also the Compose bind-mount
sources.

## Where OptimusKG data is parsed

The production graph path is:

1. `services/optimuskg-service/src/optimuskg_service/main.py` builds an
   `OptimusKGGraphConfig` from `OPTIMUSKG_CACHE_DIR`, `OPTIMUSKG_USE_LCC`, and
   related settings.
2. `packages/translume-adapters/src/translume_adapters/graph_providers/optimuskg_runtime.py`
   imports the real upstream client from
   `third_party/upstream/OptimusKG/packages/optimuskg/src`.
3. The adapter calls `optimuskg.set_cache_dir(...)`, followed by
   `optimuskg.get_file(...)` for one of these exact pairs:
   - largest connected component (default):
     `largest_connected_component_nodes.parquet` and
     `largest_connected_component_edges.parquet`
   - full graph: `nodes.parquet` and `edges.parquet`
4. Polars scans the node and edge Parquet tables. Translume requires node
   columns `id`, `label`, and `properties`, and edge columns `from`, `to`, and
   `label`.
5. Report entities are matched against node IDs, labels, names, symbols, and
   aliases. Only adjacent edges, bounded by `OPTIMUSKG_MAX_EDGES`, are returned
   as graph evidence.

The upstream OptimusKG client already downloads a missing file lazily. The
original deployment did not persist or pre-populate its default user cache,
though, so container recreation could lose downloaded files. The
`optimuskg-data` target now calls that same client before startup and stores the
result in the bind-mounted cache. It also validates the exact schema consumed
by the adapter.

Use the full graph instead of the default largest-connected-component pair with:

```bash
make optimuskg-data OPTIMUSKG_USE_LCC=false
```

Force a client refresh with `OPTIMUSKG_FORCE_DOWNLOAD=true`.

## Where Medea literature reasoning runs

`services/medea-service/src/medea_service/main.py` preserves the existing
literature path. For each `/reason` request it constructs Medea's three bounded
literature actions:

- `LiteratureSearch`
- `PaperJudge`
- `OpenScholarReasoning`

It then calls the upstream `medea.literature_reasoning(...)` entry point. The
Translume-owned local runtime patches Medea's model call sites so they use the
configured local vLLM endpoint rather than a remote model provider.

Literature search is a runtime operation, not a static dataset download. The
`medea-data` target does not replace or disable this path.

## Where MedeaDB is parsed and used

Medea's upstream tools resolve database files relative to `MEDEADB_PATH`.
`scripts/download_mims_data.py` downloads the official
`mims-harvard/MedeaDB` Hugging Face dataset directly into the directory mounted
at that exact root and checks the resource families used by the upstream tools:

- DepMap 24Q2 correlation matrices
- PINNACLE embeddings
- TranscriptFormer embedding store
- COMPASS checkpoints

The service's database adapter lives in
`services/medea-service/src/medea_service/database_runtime.py`. It imports the
real upstream `medea.tool_space.depmap.GeneCorrelationLookup`, memory-maps the
DepMap matrices, and exposes two interaction paths:

- `POST /database/depmap-correlation` performs a direct pairwise gene lookup.
- `POST /reason` extracts report genes, performs a bounded set of DepMap
  pairwise or single-gene-neighbor lookups, and adds those raw observations to
  the query passed through Medea literature reasoning. The returned artifact
  contains both the database observations and the literature synthesis.

`GET /database/status` reports the exact mounted resources, and
`GET /runtime-contract` opens the upstream parser to confirm that the database
is actually parseable rather than merely present.

The complete snapshot is provisioned so PINNACLE, TranscriptFormer, and COMPASS
resources remain at the paths expected by upstream Medea. The automatic
`/reason` enrichment currently uses DepMap because the incoming report context
contains gene symbols and maps directly to that parser; it does not
unconditionally execute every model or embedding resource in MedeaDB.

By default `MEDEA_REQUIRE_DATABASE=true`. A missing or incomplete database makes
Medea requests fail with an actionable message instead of silently falling back
to literature-only output. For an intentional literature-only development run:

```bash
MEDEA_REQUIRE_DATABASE=false docker compose up medea-service
```

## Validation and refresh controls

```text
MEDEADB_PATH                  host destination for the snapshot target
MEDEADB_REVISION              optional Hugging Face revision pin
MEDEADB_MAX_WORKERS           concurrent snapshot downloads (default 8)
MEDEADB_FORCE_DOWNLOAD        force Hugging Face file refresh
OPTIMUSKG_CACHE_DIR           host cache destination for the Make target
OPTIMUSKG_USE_LCC             select LCC (true) or full graph (false)
OPTIMUSKG_FORCE_DOWNLOAD      force Dataverse file refresh
OPTIMUSKG_DOI                 optional upstream Dataverse dataset override
```

`make mims-data-status` and full-stack preflight reject missing Medea resources,
missing OptimusKG files, and OptimusKG Parquet files whose columns do not match
the adapter parser.
