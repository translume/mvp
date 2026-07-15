# Engineering Tutorial: Local Reactome GraphDB Override for Translume's Existing ToolUniverse Runtime

**Ticket:** `TL-REACTOME-LOCAL-001`  
**Status:** codebase-aligned implementation tutorial  
**Repository reviewed:** uploaded `mvp-mvp-testing` workspace  
**Supersedes:** `reactome_local_tooluniverse_adapter_plan_ecr_only(1).md`  
**Implementation state:** this document does not modify repository source files

---

## 1. Executive decision

Implement the governed ToolUniverse name `ReactomeContent_search` as a **local execution override inside the existing `ToolUniverseRuntime`**. Back it with the official Reactome Neo4j GraphDB image pulled from AWS Public ECR.

Keep these contracts unchanged:

- workflow: `pathway_context`;
- configured tool name: `ReactomeContent_search`;
- `ToolProvider.run_workflows(...)` port;
- `ToolUniverseServiceClient` request and response shape;
- `POST /workflows` body and response;
- `POST /api/v1/reports/process` orchestration;
- the ToolUniverse Reactome search result structure consumed by `result_to_evidence_items()`.

Do **not**:

- modify Harvard MIMS ToolUniverse source;
- add a second public tool registry;
- rename the workflow step to `ReactomeLocal_search`;
- call Reactome ContentService, AnalysisService, or `download.reactome.org` during report processing;
- automate the Cloudflare browser challenge;
- silently fall back to the blocked remote implementation.

### Why this is the real extension seam

The reviewed repository does not contain the hypothetical API from the earlier plan:

```python
adapter_registry.register(..., override=True)
```

The actual path is:

```text
Translume API
  -> ToolUniverseServiceClient
  -> POST tooluniverse-service:8092/workflows
  -> tooluniverse_service.main._runtime()
  -> ToolUniverseRuntime.run_workflows()
  -> run_workflow()
  -> run_workflow_step()
  -> engine.run_one_function(...)
```

`run_workflow_step()` is already the single governed dispatch point. Add exact-name local dispatch there, immediately before `engine.run_one_function()`. This replaces only the blocked Reactome step while preserving every surrounding boundary.

---

## 2. Root cause and desired path

### Current failure

```text
pathway_context[0] ReactomeContent_search
  -> requests.get(reactome.org/ContentService/search/query)
  -> Reactome Cloudflare challenges the AWS public egress IP
  -> 403 challenge page; ContentService is never reached
  -> ToolUniverse returns {status: error}
  -> ToolUniverseWorkflowError
  -> /workflows returns 422
  -> /api/v1/reports/process reports MIMS failure
```

### Target behavior

```text
public.ecr.aws/reactome/graphdb:Release97
  -> reactome-graphdb container
  -> Bolt on the private Compose network
  -> Neo4jReactomeSearchBackend
  -> ReactomeContentSearchOverride
  -> ToolUniverseRuntime exact-name local dispatch
  -> existing pathway_context workflow
  -> existing ToolRunArtifact flattening
  -> report processing continues
```

The later pathway steps remain vendor ToolUniverse calls:

```text
pathway_context[1] PathwayCommons_search
pathway_context[2] kegg_search_pathway
```

When local mode is enabled, the vendor engine must neither load nor execute the built-in `ReactomeContent_search`.

---

## 3. What the repository actually does

### 3.1 Stable domain port

`packages/translume-ports/src/translume_ports/tool_provider.py` defines:

```python
class ToolProvider(Protocol):
    async def run_workflows(
        self,
        *,
        workflows: list[str],
        entities: NormalizedEntitySet,
        graph: GraphEvidenceArtifact,
    ) -> list[ToolRunArtifact]: ...
```

Do not change this port. Local Reactome is an internal adapter detail.

### 3.2 Production client

`packages/translume-clients/src/translume_clients/mims.py` posts normalized entities and graph evidence to `/workflows`. It must remain unaware of Neo4j.

### 3.3 ToolUniverse provider

`packages/translume-adapters/src/translume_adapters/tool_providers/tooluniverse_provider.py` supports:

- HTTP service mode in production;
- direct `ToolUniverseRuntime` mode in tests and isolated execution.

Only direct mode needs an optional override mapping. HTTP mode continues to call the service.

### 3.4 Governed runtime

`packages/translume-adapters/src/translume_adapters/tool_providers/tooluniverse_runtime.py` currently:

1. validates `configs/local/tooluniverse_workflows.json`;
2. extracts configured tool names;
3. asks ToolUniverse to load every name;
4. renders step arguments from `template_context()`;
5. calls `engine.run_one_function()`;
6. rejects error-shaped results;
7. flattens each result into `ToolRunArtifact.evidence_items`.

This is the correct place for a local override.

### 3.5 Service lifecycle

`services/tooluniverse-service/src/tooluniverse_service/main.py` currently creates a new runtime every time `_runtime()` is called. That is acceptable for a stateless wrapper but wrong for a Neo4j driver, which owns a reusable connection pool. The service must cache one runtime per Uvicorn worker and close it on lifespan shutdown.

### 3.6 Existing workflow is already the right public contract

`configs/local/tooluniverse_workflows.json` contains:

```json
{
  "tool_name": "ReactomeContent_search",
  "required_context": ["pathway_query"],
  "use_cache": true,
  "arguments": {
    "query": "$pathway_query",
    "species": "Homo sapiens",
    "types": "Pathway"
  }
}
```

Do not change the JSON to select the local implementation.

### 3.7 Existing Translume extension patterns

The repository already shows two relevant patterns.

**OptimusKG** isolates vendor import and data I/O in `optimuskg_runtime.py`, then exposes it through `OptimusKGGraphProvider`. Reactome should similarly isolate Neo4j I/O in a small backend and keep orchestration pure/testable.

**Medea** validates local-only configuration in `medea_service/local_runtime.py` and applies the vendor adaptation at the service composition boundary. ToolUniverse has an even cleaner central dispatch than Medea, so use exact-name routing rather than monkeypatching ToolUniverse internals.

The resulting design follows the repository's style:

- frozen dataclasses for configuration and records;
- pure normalization/ranking helpers;
- one narrow I/O class;
- explicit provider errors;
- fail-loudly startup/readiness checks;
- acceptance criteria close to implementation and tests.

### 3.8 Important entity-normalization detail

`normalize_report_entities()` creates a true `gene` entity whenever `finding.gene` exists, then creates a separate alteration entity using `finding.alteration_type` and `finding.alteration`.

Therefore:

- `pathway_genes` must contain **only** normalized `gene` entities;
- `copy_number_loss` and `copy_number_gain` labels are alteration text, not guaranteed gene symbols;
- do not feed alteration labels into the Neo4j gene traversal;
- those labels may remain in the existing free-text `pathway_query` for PathwayCommons/KEGG compatibility;
- if a copy-number finding lacks `finding.gene`, fix extraction/normalization in a separate ticket rather than guessing a gene from alteration prose.

### 3.9 Actual upstream ToolUniverse result contract

The vendored `third_party/zips/ToolUniverse.zip` returns:

```json
{
  "status": "success",
  "data": {
    "query": "TP53",
    "species": "Homo sapiens",
    "types_searched": "Pathway",
    "total_results": 1,
    "results": [
      {
        "type": "Pathway",
        "stId": "R-HSA-000000",
        "name": "Example pathway",
        "species": ["Homo sapiens"],
        "compartments": [],
        "is_disease": false
      }
    ]
  },
  "metadata": {
    "source": "Reactome Content Service - Search",
    "query": "TP53"
  }
}
```

Compatibility requirements:

- results stay under `data.results`;
- each result's `species` stays a list;
- the count key remains `total_results`;
- public results remain capped at 30;
- `result_to_evidence_items()` continues to serialize `data` and `metadata` as JSON strings;
- local provenance is added only through backward-compatible metadata fields.

---

## 4. Architecture and scope

### Architecture

```text
reactome-graphdb (official ECR image)
       |
       | Bolt, private Compose network
       v
tooluniverse-service
  local_tool_overrides.py       deployment composition
       |
       v
ReactomeContentSearchOverride   ToolUniverse-compatible adapter
       |
       v
Neo4jReactomeSearchBackend      only Neo4j I/O boundary
       |
       v
ToolUniverseRuntime.run_workflow_step()
       |
       +--> exact Reactome name: local override
       +--> every other name: real ToolUniverse engine
```

### V1 scope

Implement only the contract used by `pathway_context`:

- operation: search;
- species: `Homo sapiens`;
- type: `Pathway`;
- search strategies: pathway stable ID/display name and structured report genes;
- deterministic, bounded results;
- no live Reactome HTTP request.

Out of scope:

- a complete ContentService clone;
- AnalysisService enrichment statistics;
- replacing other Reactome tools in ToolUniverse;
- all species and all search types;
- APOC or custom indexes in v1;
- remote fallback;
- Cloudflare challenge automation;
- changing the outer `/workflows` or report API schemas.

---

## 5. File-by-file change map

### New files

| File | Purpose |
|---|---|
| `packages/translume-adapters/src/translume_adapters/tool_providers/reactome_graphdb.py` | Local config, request normalization, Neo4j backend, ranking, ToolUniverse-compatible response, and override handler |
| `services/tooluniverse-service/src/tooluniverse_service/local_tool_overrides.py` | Parse service environment and build the immutable override mapping |
| `tests/unit/test_reactome_graphdb_adapter.py` | Pure/unit tests for configuration, normalization, ranking, contract mapping, and fake backend |
| `tests/fixtures/tooluniverse/reactome_content_search_success.json` | Frozen fixture matching vendored ToolUniverse output |
| `scripts/smoke_local_reactome_workflow.py` | Smoke test through the real `/workflows` service boundary |

### Modified files

| File | Change |
|---|---|
| `packages/translume-adapters/.../tooluniverse_runtime.py` | Add generic local override protocol/mapping, structured pathway context, vendor-name filtering, local dispatch, health aggregation, cleanup |
| `packages/translume-adapters/.../tooluniverse_provider.py` | Allow override injection in direct runtime mode only |
| `services/tooluniverse-service/.../main.py` | Build overrides, cache runtime, lifespan cleanup, readiness-aware health |
| `packages/translume-adapters/pyproject.toml` | Add Neo4j driver |
| `docker/tooluniverse-service.Dockerfile` | Install Neo4j driver in the image's current explicit dependency layer |
| `uv.lock` | Lock the selected driver |
| `docker-compose.yml` | Add internal GraphDB service and startup dependency |
| `.env.example` | Document pinned ECR image and local GraphDB settings |
| `Makefile` | Pass the same env file to Compose interpolation; add image pull/smoke targets |
| `packages/translume-core/.../prime_directives/gate.py` | Enforce local-only pinned Reactome configuration in production/demo |
| `configs/integration/full_stack_requirements.json` | Require GraphDB/local-override readiness fields |
| Existing ToolUniverse/MIMS test modules | Add dispatch, service, health, and end-to-end regression coverage |
| Operator/architecture docs | Add release validation, deployment, rollback, and provenance behavior |

### Files that should remain unchanged

```text
configs/local/tooluniverse_workflows.json
packages/translume-ports/src/translume_ports/tool_provider.py
packages/translume-clients/src/translume_clients/mims.py
third_party/upstream/ToolUniverse/**
third_party/zips/ToolUniverse.zip
```

---
## 6. Implementation tutorial

## Step 0 — Freeze the current ToolUniverse contract

Create `tests/fixtures/tooluniverse/reactome_content_search_success.json` from the vendored implementation before writing local code.

Add a contract test:

```python
payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

assert payload["status"] == "success"
assert set(payload["data"]) == {
    "query",
    "species",
    "types_searched",
    "total_results",
    "results",
}
assert set(payload["data"]["results"][0]) == {
    "type",
    "stId",
    "name",
    "species",
    "compartments",
    "is_disease",
}
```

Also freeze the repository's evidence flattening:

```python
items = result_to_evidence_items(
    "pathway_context",
    0,
    {"tool_name": "ReactomeContent_search"},
    payload,
)

assert items[0]["tool_name"] == "ReactomeContent_search"
assert json.loads(items[0]["data"])["results"]
assert json.loads(items[0]["metadata"])["query"] == "TP53"
```

**Why:** this protects the exact boundary consumed by report generation. A locally useful but structurally different response would otherwise silently degrade downstream evidence.

### Step 0 acceptance criteria

- The fixture is static and matches the vendored implementation.
- Tests parse flattened `data` and `metadata` JSON strings.
- No local GraphDB code is needed to run this test.

---

## Step 1 — Add the official Reactome GraphDB image

Add before `tooluniverse-service` in `docker-compose.yml`:

```yaml
  reactome-graphdb:
    image: ${REACTOME_GRAPHDB_IMAGE:-public.ecr.aws/reactome/graphdb:Release97}
    restart: unless-stopped
    expose:
      - "7474"
      - "7687"
    environment:
      NEO4J_dbms_memory_heap_maxSize: ${REACTOME_NEO4J_HEAP_MAX_SIZE:-8g}
```

Modify `tooluniverse-service`:

```yaml
  tooluniverse-service:
    build:
      context: .
      dockerfile: docker/tooluniverse-service.Dockerfile
    env_file: ${TRANSLUME_ENV_FILE:-.env}
    depends_on:
      reactome-graphdb:
        condition: service_started
    ports:
      - "8092:8092"
    healthcheck:
      test:
        [
          "CMD",
          "python",
          "-c",
          "import urllib.request; urllib.request.urlopen('http://localhost:8092/health', timeout=5).read()",
        ]
      interval: 15s
      timeout: 10s
      retries: 40
      start_period: 300s
```

Keep the existing API dependency unchanged:

```yaml
      tooluniverse-service:
        condition: service_healthy
```

### Network and storage rules

- Do not publish `7474` or `7687` on the VM by default.
- Use the existing default Compose network; `bolt://reactome-graphdb:7687` resolves internally.
- For one-time schema inspection, use a local-only override binding `127.0.0.1`.
- Do not mount a persistent `/data` volume in v1. The image tag is the immutable dataset release; a long-lived volume can retain an old database after an image update. Revisit only with a tested migration procedure.
- Do not rely on a superficial open-port healthcheck. The ToolUniverse `/health` endpoint will execute a Bolt readiness query and gate the API through the existing dependency chain.

### Compose interpolation warning

`env_file:` injects variables into the container, but it does **not** supply variables used while Compose renders `image: ${REACTOME_GRAPHDB_IMAGE...}`. The same deployment env file must be passed to Compose with `--env-file` or its values must be exported in the shell. Step 9 changes the Makefile accordingly.

Verify the tag before merge/deploy:

```bash
export TRANSLUME_ENV_FILE=.env

docker compose --env-file "$TRANSLUME_ENV_FILE" config \
  | grep -A2 'reactome-graphdb:'

docker compose --env-file "$TRANSLUME_ENV_FILE" pull reactome-graphdb
```

If `Release97` is not available, pin the highest verified `Release<N>` tag and set `REACTOME_RELEASE=N`. Never replace a missing tag with `latest`.

### Step 1 acceptance criteria

- `docker compose --env-file "$TRANSLUME_ENV_FILE" config` renders the intended pinned image.
- The ECR image pull succeeds.
- Neo4j is not publicly exposed.
- ToolUniverse can start while GraphDB initializes, but remains unhealthy until Bolt/data checks pass.
- Translume API still waits for ToolUniverse health.
- Recreating with a new image tag cannot silently retain an old mounted database.

---

## Step 2 — Add explicit local-only configuration

Add beside the current ToolUniverse settings in `.env.example`:

```dotenv
# Official Reactome GraphDB snapshot from AWS Public ECR.
REACTOME_LOCAL_ENABLED=true
REACTOME_GRAPHDB_IMAGE=public.ecr.aws/reactome/graphdb:Release97
REACTOME_RELEASE=97

# Private Compose-network connection.
REACTOME_NEO4J_URI=bolt://reactome-graphdb:7687
REACTOME_NEO4J_DATABASE=graph.db
REACTOME_NEO4J_AUTH_MODE=basic
REACTOME_NEO4J_USER=neo4j
# Verify against the pinned image before promotion. Reactome-owned tooling
# currently uses this default for its ECR GraphDB workflow.
REACTOME_NEO4J_PASSWORD=test

REACTOME_NEO4J_HEAP_MAX_SIZE=8g
REACTOME_QUERY_TIMEOUT_SECONDS=30
REACTOME_MAX_RESULTS=30
REACTOME_MAX_QUERY_TERMS=8
REACTOME_REMOTE_FALLBACK=false
```

Support only `basic` and `none` internally. Require `basic` for production/demo. Do not guess credentials, try multiple passwords, or silently downgrade to unauthenticated mode.

Do not set `NEO4J_AUTH` on the preloaded image unless the pinned image is explicitly proven to support changing its baked authentication store. The runtime should use one configured credential and fail clearly if it is wrong.

Configuration must reject:

- local mode disabled in production/demo;
- remote fallback enabled;
- empty, `latest`, non-ECR, or release-mismatched image tags;
- HTTP Reactome URIs or any URI containing `reactome.org`;
- unsupported auth mode;
- missing basic credentials;
- timeout <= 0;
- max results outside 1..30;
- max query terms outside a small bound such as 1..32.

### Step 2 acceptance criteria

- Environment parsing is a pure function over `Mapping[str, str]`.
- Configuration errors identify the exact variable.
- Password fields use `repr=False` and never appear in health/log output.
- Production/demo configuration has no remote Reactome route.

---

## Step 3 — Install the Neo4j driver in both real dependency paths

Update `packages/translume-adapters/pyproject.toml`:

```toml
[project]
dependencies = [
    "polars>=1.0.0",
    "httpx",
    "pydantic",
    "neo4j>=6.2,<7",
]
```

Update the explicit install in `docker/tooluniverse-service.Dockerfile`:

```dockerfile
RUN pip install --no-cache-dir uv \
    && uv pip install --system \
        pydantic \
        fastapi \
        uvicorn \
        httpx \
        gradio \
        pytest \
        "neo4j>=6.2,<7" \
    && for repo in /app/third_party/upstream/*; do \
        if [ -f "$repo/pyproject.toml" ] || [ -f "$repo/setup.py" ]; then \
          uv pip install --system -e "$repo"; \
        fi; \
      done
```

Then run:

```bash
uv lock
```

Both edits are necessary because this Dockerfile does not install the workspace adapter package from its metadata; it installs a manual dependency list and uses `PYTHONPATH`.

Before merge, run the selected driver against the pinned ECR image. If the actual image's Neo4j server cannot negotiate with driver 6.x, pin the newest compatible 5.x release in **both** places and record the compatibility result. Do not leave divergent constraints.

### Step 3 acceptance criteria

- Local unit tests import `neo4j` through locked dependencies.
- The ToolUniverse container imports the same driver major version.
- `driver.verify_connectivity()` succeeds against the pinned image.
- The configured `graph.db` query executes with the selected driver.

---

## Step 4 — Implement the local GraphDB adapter

Create:

```text
packages/translume-adapters/src/translume_adapters/tool_providers/reactome_graphdb.py
```

### 4.1 Define immutable records and a narrow internal protocol

```python
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any, Protocol

from neo4j import GraphDatabase, Query, RoutingControl
from neo4j.exceptions import DriverError, Neo4jError

from translume_adapters.errors import ProviderUnavailableError


class ReactomeGraphDBError(ProviderUnavailableError):
    """Raised when the local Reactome data source cannot be used."""


@dataclass(frozen=True)
class ReactomeGraphDBConfig:
    uri: str
    database: str
    auth_mode: str
    username: str | None
    password: str | None = field(repr=False)
    release: str
    query_timeout_seconds: float = 30.0
    max_results: int = 30
    max_query_terms: int = 8


@dataclass(frozen=True)
class ReactomeSearchRequest:
    query: str
    species: str
    types: tuple[str, ...]
    cluster: bool
    genes: tuple[str, ...]
    pathway_terms: tuple[str, ...]
    max_results: int


@dataclass(frozen=True)
class ReactomePathwayMatch:
    stable_id: str
    name: str
    species: str
    is_disease: bool
    matched_terms: tuple[str, ...] = ()
    matched_genes: tuple[str, ...] = ()
    score: int = 0


class ReactomeSearchBackend(Protocol):
    def search_text(
        self,
        *,
        terms: tuple[str, ...],
        species: str,
        candidate_limit: int,
    ) -> tuple[ReactomePathwayMatch, ...]: ...

    def search_genes(
        self,
        *,
        genes: tuple[str, ...],
        species: str,
        candidate_limit: int,
    ) -> tuple[ReactomePathwayMatch, ...]: ...

    def health_report(self) -> Mapping[str, object]: ...
    def close(self) -> None: ...
```

Keep this protocol inside the adapter package. It is not a domain port.

### 4.2 Add pure configuration and request normalization

```python
def validate_reactome_graphdb_config(
    config: ReactomeGraphDBConfig,
) -> None:
    if not config.uri.startswith(("bolt://", "neo4j://")):
        raise ValueError("Reactome URI must use bolt:// or neo4j://")
    if "reactome.org" in config.uri.casefold():
        raise ValueError("Reactome URI must point to local GraphDB")
    if not config.database.strip():
        raise ValueError("Reactome Neo4j database is required")
    normalize_reactome_release(config.release)
    if config.auth_mode not in {"basic", "none"}:
        raise ValueError("Reactome auth mode must be basic or none")
    if config.auth_mode == "basic" and not (
        config.username and config.password
    ):
        raise ValueError("Reactome basic auth requires user and password")
    if config.query_timeout_seconds <= 0:
        raise ValueError("Reactome query timeout must be positive")
    if not 1 <= config.max_results <= 30:
        raise ValueError("Reactome max results must be between 1 and 30")
    if not 1 <= config.max_query_terms <= 32:
        raise ValueError("Reactome max query terms must be between 1 and 32")


def normalize_strings(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        values = (value,)
    elif isinstance(value, Sequence) and not isinstance(
        value, (bytes, bytearray)
    ):
        values = tuple(str(item) for item in value)
    else:
        values = ()

    seen: set[str] = set()
    output: list[str] = []
    for item in values:
        text = item.strip()
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            output.append(text)
    return tuple(output)


def normalize_types(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return normalize_strings(value.split(","))
    if isinstance(value, Sequence):
        return normalize_strings(value)
    raise TypeError("Reactome types must be a string or sequence")


def normalize_boolean(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    raise ValueError("Reactome cluster must be a boolean")


def normalize_reactome_release(value: object) -> str:
    text = str(value or "").strip().casefold()
    for prefix in ("release", "version", "v"):
        if text.startswith(prefix):
            text = text.removeprefix(prefix).strip()
            break
    if not text.isdigit() or int(text) <= 0:
        raise ValueError(f"Invalid Reactome release: {value!r}")
    return str(int(text))


def species_tax_id(species: str) -> str:
    if species.strip().casefold() != "homo sapiens":
        raise ValueError("Local Reactome v1 supports only Homo sapiens")
    return "9606"


def normalize_reactome_search_request(
    *,
    arguments: Mapping[str, Any],
    context: Mapping[str, Any],
    config: ReactomeGraphDBConfig,
) -> ReactomeSearchRequest:
    query = str(arguments.get("query", "")).strip()
    if not query:
        raise ValueError("Reactome search query is required")

    species = str(arguments.get("species", "Homo sapiens")).strip()
    species_tax_id(species)

    types = normalize_types(arguments.get("types", "Pathway"))
    if tuple(item.casefold() for item in types) != ("pathway",):
        raise ValueError("Local Reactome v1 supports only types='Pathway'")

    genes = normalize_strings(
        context.get("pathway_genes", context.get("genes", ()))
    )[: config.max_query_terms]

    pathway_terms = normalize_strings(context.get("pathway_terms", ()))
    if not pathway_terms:
        # Direct/manual callers may not yet have structured context. Preserve
        # the complete phrase and bounded tokens; production workflow calls
        # use the explicit structured list added in Step 5.
        pathway_terms = normalize_strings((query, *query.split()))
    pathway_terms = pathway_terms[: config.max_query_terms]

    return ReactomeSearchRequest(
        query=query,
        species="Homo sapiens",
        types=("Pathway",),
        cluster=normalize_boolean(arguments.get("cluster", True)),
        genes=genes,
        pathway_terms=pathway_terms,
        max_results=config.max_results,
    )
```

Important: `pathway_genes` comes from real normalized gene entities only. Do not parse `copy_number_loss` or `copy_number_gain` prose as identifiers.

### 4.3 Build one long-lived Neo4j boundary

```python
def build_neo4j_auth(
    config: ReactomeGraphDBConfig,
) -> tuple[str, str] | None:
    if config.auth_mode == "none":
        return None
    if config.auth_mode == "basic":
        if not config.username or not config.password:
            raise ValueError("Reactome basic auth requires credentials")
        return (config.username, config.password)
    raise ValueError(f"Unsupported Reactome auth mode: {config.auth_mode}")


class Neo4jReactomeSearchBackend:
    def __init__(self, config: ReactomeGraphDBConfig) -> None:
        self._config = config
        self._driver = GraphDatabase.driver(
            config.uri,
            auth=build_neo4j_auth(config),
        )
        self._closed = False

    def search_text(
        self,
        *,
        terms: tuple[str, ...],
        species: str,
        candidate_limit: int,
    ) -> tuple[ReactomePathwayMatch, ...]:
        if not terms:
            return ()
        rows = self._read(
            TEXT_PATHWAY_SEARCH,
            {
                "terms": [term.casefold() for term in terms],
                "tax_id": species_tax_id(species),
                "candidate_limit": candidate_limit,
            },
        )
        return tuple(text_row_to_match(row) for row in rows)

    def search_genes(
        self,
        *,
        genes: tuple[str, ...],
        species: str,
        candidate_limit: int,
    ) -> tuple[ReactomePathwayMatch, ...]:
        if not genes:
            return ()
        rows = self._read(
            GENE_PATHWAY_SEARCH,
            {
                "genes": [gene.casefold() for gene in genes],
                "tax_id": species_tax_id(species),
                "candidate_limit": candidate_limit,
            },
        )
        return tuple(gene_row_to_match(row) for row in rows)

    def health_report(self) -> Mapping[str, object]:
        try:
            self._driver.verify_connectivity()
            rows = self._read(GRAPH_INFO_QUERY, {})
            row = rows[0] if rows else {}
            pathway_count = int(row.get("pathway_count", 0))
            actual_release = normalize_reactome_release(
                row.get("graph_version")
            )
            configured_release = normalize_reactome_release(
                self._config.release
            )
            release_matches = actual_release == configured_release
            healthy = pathway_count > 0 and release_matches
            error = None
            if pathway_count <= 0:
                error = "no Pathway nodes found"
            elif not release_matches:
                error = (
                    "Reactome graph release mismatch: "
                    f"configured={configured_release}, actual={actual_release}"
                )
            return {
                "status": "healthy" if healthy else "unhealthy",
                "reactome_graphdb_available": healthy,
                "reactome_graphdb_database": self._config.database,
                "reactome_graphdb_configured_release": configured_release,
                "reactome_graphdb_actual_release": actual_release,
                "reactome_graphdb_release_matches": release_matches,
                "reactome_pathway_count": pathway_count,
                "error": error,
            }
        except (ReactomeGraphDBError, TypeError, ValueError) as error:
            return {
                "status": "unhealthy",
                "reactome_graphdb_available": False,
                "reactome_graphdb_database": self._config.database,
                "reactome_graphdb_configured_release": self._config.release,
                "reactome_graphdb_actual_release": None,
                "reactome_graphdb_release_matches": False,
                "reactome_pathway_count": 0,
                "error": str(error)[:500],
            }

    def close(self) -> None:
        if self._closed:
            return
        self._driver.close()
        self._closed = True

    def _read(
        self,
        cypher: str,
        parameters: Mapping[str, object],
    ) -> tuple[Mapping[str, object], ...]:
        try:
            records, _, _ = self._driver.execute_query(
                Query(
                    cypher,
                    timeout=self._config.query_timeout_seconds,
                ),
                parameters_=dict(parameters),
                database_=self._config.database,
                routing_=RoutingControl.READ,
            )
        except (DriverError, Neo4jError, OSError) as error:
            raise ReactomeGraphDBError(
                "Local Reactome GraphDB query failed: "
                f"{type(error).__name__}: {error}"
            ) from error
        return tuple(record.data() for record in records)
```

One backend owns one driver pool. Sessions/transactions are created by the driver per query. No request creates a new driver.

### 4.4 Add bounded Cypher

Text and stable-ID search:

```python
TEXT_PATHWAY_SEARCH = """
UNWIND $terms AS term
MATCH
  (species:Species {taxId: $tax_id})
  <-[:species]-
  (pathway:Pathway)
WHERE
  toLower(coalesce(pathway.stId, '')) = term
  OR toLower(coalesce(pathway.displayName, '')) CONTAINS term
WITH
  pathway,
  species,
  collect(DISTINCT term) AS matched_terms,
  max(
    CASE WHEN toLower(coalesce(pathway.stId, '')) = term
         THEN 1 ELSE 0 END
  ) AS exact_stable_id,
  max(
    CASE WHEN toLower(coalesce(pathway.displayName, '')) = term
         THEN 1 ELSE 0 END
  ) AS exact_name
RETURN
  pathway.stId AS stable_id,
  pathway.displayName AS name,
  species.displayName AS species,
  coalesce(pathway.isInDisease, false) AS is_disease,
  matched_terms,
  [] AS matched_genes
ORDER BY
  exact_stable_id DESC,
  exact_name DESC,
  size(matched_terms) DESC,
  pathway.displayName,
  pathway.stId
LIMIT $candidate_limit
"""
```

Structured gene-to-pathway search, based on Reactome's documented relationship families:

```python
GENE_PATHWAY_SEARCH = """
UNWIND $genes AS gene
MATCH (reference)-[:referenceDatabase]->(database:ReferenceDatabase)
WHERE toLower(coalesce(database.displayName, '')) = 'uniprot'
  AND (
    toLower(coalesce(reference.identifier, '')) = gene
    OR toLower(coalesce(reference.variantIdentifier, '')) = gene
    OR any(
      symbol IN coalesce(reference.geneName, [])
      WHERE toLower(symbol) = gene
    )
    OR any(
      alias IN coalesce(reference.name, [])
      WHERE toLower(alias) = gene
    )
  )
WITH DISTINCT gene, reference
MATCH
  (physical:PhysicalEntity)
  -[:referenceEntity|referenceSequence|crossReference|referenceGene*1..4]->
  (reference)
WITH DISTINCT gene, physical
MATCH
  (reaction:ReactionLikeEvent)
  -[:input|output|catalystActivity|physicalEntity|entityFunctionalStatus|
    diseaseEntity|regulatedBy|regulator|hasComponent|hasMember|
    hasCandidate|repeatedUnit*1..8]->
  (physical)
WITH DISTINCT gene, reaction
MATCH
  (species:Species {taxId: $tax_id})
  <-[:species]-
  (pathway:Pathway)
  -[:hasEvent*1..12]->
  (reaction)
WITH pathway, species, collect(DISTINCT gene) AS matched_genes
RETURN
  pathway.stId AS stable_id,
  pathway.displayName AS name,
  species.displayName AS species,
  coalesce(pathway.isInDisease, false) AS is_disease,
  [] AS matched_terms,
  matched_genes
ORDER BY
  size(matched_genes) DESC,
  pathway.displayName,
  pathway.stId
LIMIT $candidate_limit
"""
```

Release/readiness query:

```python
GRAPH_INFO_QUERY = """
OPTIONAL MATCH (db_info:DBInfo)
WITH head(collect(db_info.version)) AS graph_version
MATCH (pathway:Pathway)
RETURN graph_version, count(pathway) AS pathway_count
"""
```

The variable-length caps are implementation defaults, not biological facts. Step 11 must compare them against Reactome's unbounded diagnostic query on the pinned release. Do not ship unbounded traversal in production.

### 4.5 Convert records, rank, and serialize

Keep record-shape knowledge at the I/O boundary:

```python
def require_row_text(row: Mapping[str, object], key: str) -> str:
    value = str(row.get(key, "")).strip()
    if not value:
        raise ReactomeGraphDBError(
            f"Local Reactome row missing required field: {key}"
        )
    return value


def text_row_to_match(
    row: Mapping[str, object],
) -> ReactomePathwayMatch:
    return ReactomePathwayMatch(
        stable_id=require_row_text(row, "stable_id"),
        name=require_row_text(row, "name"),
        species=str(row.get("species") or "Homo sapiens").strip(),
        is_disease=bool(row.get("is_disease", False)),
        matched_terms=normalize_strings(row.get("matched_terms")),
    )


def gene_row_to_match(
    row: Mapping[str, object],
) -> ReactomePathwayMatch:
    return ReactomePathwayMatch(
        stable_id=require_row_text(row, "stable_id"),
        name=require_row_text(row, "name"),
        species=str(row.get("species") or "Homo sapiens").strip(),
        is_disease=bool(row.get("is_disease", False)),
        matched_genes=normalize_strings(row.get("matched_genes")),
    )
```

Pure merge/ranking:

```python
def pathway_score(
    request: ReactomeSearchRequest,
    match: ReactomePathwayMatch,
) -> int:
    keys = {
        request.query.casefold(),
        *(term.casefold() for term in request.pathway_terms),
    }
    return (
        (10_000 if match.stable_id.casefold() in keys else 0)
        + (5_000 if match.name.casefold() in keys else 0)
        + 100 * len(match.matched_genes)
        + 10 * len(match.matched_terms)
    )


def combine_matches(
    request: ReactomeSearchRequest,
    left: ReactomePathwayMatch | None,
    right: ReactomePathwayMatch,
) -> ReactomePathwayMatch:
    if left is None:
        merged = right
    else:
        if left.stable_id != right.stable_id:
            raise ValueError("Reactome stable IDs differ during merge")
        merged = ReactomePathwayMatch(
            stable_id=left.stable_id,
            name=left.name,
            species=left.species or right.species,
            is_disease=left.is_disease or right.is_disease,
            matched_terms=normalize_strings(
                (*left.matched_terms, *right.matched_terms)
            ),
            matched_genes=normalize_strings(
                (*left.matched_genes, *right.matched_genes)
            ),
        )
    return replace(merged, score=pathway_score(request, merged))


def merge_and_rank_matches(
    *,
    request: ReactomeSearchRequest,
    text_matches: Sequence[ReactomePathwayMatch],
    gene_matches: Sequence[ReactomePathwayMatch],
) -> tuple[ReactomePathwayMatch, ...]:
    by_id: dict[str, ReactomePathwayMatch] = {}
    for candidate in (*text_matches, *gene_matches):
        by_id[candidate.stable_id] = combine_matches(
            request,
            by_id.get(candidate.stable_id),
            candidate,
        )
    return tuple(
        sorted(
            by_id.values(),
            key=lambda item: (
                -item.score,
                item.name.casefold(),
                item.stable_id,
            ),
        )
    )
```

Exact ToolUniverse-compatible serialization:

```python
def to_tooluniverse_reactome_result(
    *,
    request: ReactomeSearchRequest,
    matches: Sequence[ReactomePathwayMatch],
    config: ReactomeGraphDBConfig,
) -> dict[str, object]:
    public_matches = matches[: request.max_results]
    return {
        "status": "success",
        "data": {
            "query": request.query,
            "species": request.species,
            "types_searched": "Pathway",
            "total_results": len(matches),
            "results": [
                {
                    "type": "Pathway",
                    "stId": match.stable_id,
                    "name": match.name,
                    "species": [match.species],
                    "compartments": [],
                    "is_disease": match.is_disease,
                }
                for match in public_matches
            ],
        },
        "metadata": {
            "source": "Reactome GraphDB - Local Search",
            "query": request.query,
            "backend": "neo4j",
            "database": config.database,
            "configured_release": normalize_reactome_release(
                config.release
            ),
            "remote_api_used": False,
            "match_strategies": [
                "pathway_text",
                "structured_gene",
            ],
            "cluster_compatibility_value": request.cluster,
        },
    }
```

`cluster` is accepted for compatibility but is a documented no-op in v1. Do not claim to reproduce ContentService clustering.

### 4.6 Implement the exact-name override handler

```python
class ReactomeContentSearchOverride:
    tool_name = "ReactomeContent_search"

    def __init__(
        self,
        *,
        config: ReactomeGraphDBConfig,
        backend: ReactomeSearchBackend,
    ) -> None:
        self._config = config
        self._backend = backend

    def run(
        self,
        *,
        arguments: Mapping[str, Any],
        context: Mapping[str, Any],
        use_cache: bool,
        validate: bool,
    ) -> dict[str, object]:
        # Interface compatibility only. This local v1 deliberately has no
        # independent cache; the graph is local and release-pinned.
        del use_cache, validate

        request = normalize_reactome_search_request(
            arguments=arguments,
            context=context,
            config=self._config,
        )
        candidate_limit = min(request.max_results * 4, 120)
        text_matches = self._backend.search_text(
            terms=request.pathway_terms,
            species=request.species,
            candidate_limit=candidate_limit,
        )
        gene_matches = self._backend.search_genes(
            genes=request.genes,
            species=request.species,
            candidate_limit=candidate_limit,
        )
        matches = merge_and_rank_matches(
            request=request,
            text_matches=text_matches,
            gene_matches=gene_matches,
        )
        return to_tooluniverse_reactome_result(
            request=request,
            matches=matches,
            config=self._config,
        )

    def health_report(self) -> Mapping[str, object]:
        return self._backend.health_report()

    def close(self) -> None:
        self._backend.close()
```

### Step 4 acceptance criteria

- Only `Neo4jReactomeSearchBackend` performs I/O.
- All report values are Cypher parameters.
- Structured genes are true normalized gene entities only.
- Terms and candidates are bounded before expensive traversal/result mapping.
- One driver is reused and closed idempotently.
- Zero matches return `status: success` with an empty list.
- Output passes the frozen ToolUniverse contract tests.
- Metadata proves local GraphDB provenance and `remote_api_used: false`.
- This module imports no HTTP client and makes no remote request.

---
## Step 5 — Extend the existing `ToolUniverseRuntime`

Modify:

```text
packages/translume-adapters/src/translume_adapters/tool_providers/tooluniverse_runtime.py
```

### 5.1 Add a generic local-override protocol

Add `Mapping`, `Protocol`, and `MappingProxyType`, then define:

```python
class LocalToolOverride(Protocol):
    tool_name: str

    def run(
        self,
        *,
        arguments: Mapping[str, Any],
        context: Mapping[str, Any],
        use_cache: bool,
        validate: bool,
    ) -> Any: ...

    def health_report(self) -> Mapping[str, object]: ...
    def close(self) -> None: ...
```

This protocol stays generic. Do not put Neo4j-specific methods in the governed runtime.

### 5.2 Store an immutable mapping

Change the constructor:

```python
class ToolUniverseRuntime:
    def __init__(
        self,
        *,
        repo_path: Path,
        workflow_config_path: Path,
        module_names: tuple[str, ...] = ("tooluniverse",),
        local_tool_overrides: Mapping[str, LocalToolOverride] | None = None,
    ) -> None:
        self._repo_path = repo_path
        self._workflow_config_path = workflow_config_path
        self._module_names = module_names
        self._local_tool_overrides = MappingProxyType(
            dict(local_tool_overrides or {})
        )
        validate_local_tool_overrides(self._local_tool_overrides)
```

Add pure validation:

```python
def validate_local_tool_overrides(
    overrides: Mapping[str, LocalToolOverride],
) -> None:
    for name, handler in overrides.items():
        if not name or name != name.strip():
            raise ToolUniverseWorkflowError(
                f"invalid local override name: {name!r}"
            )
        if getattr(handler, "tool_name", None) != name:
            raise ToolUniverseWorkflowError(
                "local override key does not match handler.tool_name: "
                f"{name!r}"
            )


def validate_override_names_in_catalog(
    *,
    catalog: ToolUniverseWorkflowCatalog,
    overrides: Mapping[str, LocalToolOverride],
) -> None:
    configured = set(
        workflow_tool_names(catalog, tuple(catalog.workflows))
    )
    unknown = sorted(set(overrides) - configured)
    if unknown:
        raise ToolUniverseWorkflowError(
            "local override names are not present in governed workflows: "
            + ", ".join(unknown)
        )
```

The second check prevents a typo from leaving the intended Reactome tool on the vendor route.

### 5.3 Add structured context without changing `pathway_query`

In `template_context()`, keep the existing `gene_terms` and `pathway_query` behavior because the PathwayCommons and KEGG steps use it.

Add these return values:

```python
"pathway_genes": list(genes[:MAX_TOOL_QUERY_TERMS]),
"pathway_terms": bounded_query_terms(
    priority_terms=[*genes, *diseases],
    secondary_terms=graph_nodes,
),
```

Do **not** use `gene_terms` for `pathway_genes`. `gene_terms` currently mixes true genes with copy-number alteration labels. The local Neo4j identifier traversal must receive only `genes`.

This is backward compatible:

- the workflow still renders `$pathway_query` exactly as before;
- the local override receives the full context and reads the two new keys;
- other vendor tools see no request-schema change.

### 5.4 Exclude local names from vendor loading

Add:

```python
def vendor_tool_names(
    configured_names: tuple[str, ...],
    override_names: frozenset[str],
) -> tuple[str, ...]:
    return tuple(
        name for name in configured_names if name not in override_names
    )
```

Use it in `run_workflows()`:

```python
catalog = load_workflow_catalog(self._workflow_config_path)
validate_override_names_in_catalog(
    catalog=catalog,
    overrides=self._local_tool_overrides,
)
requested = tuple(workflows)
validate_requested_workflows(requested, catalog)
configured_names = workflow_tool_names(catalog, requested)
vendor_names = vendor_tool_names(
    configured_names,
    frozenset(self._local_tool_overrides),
)
engine = load_tooluniverse_engine(
    repo_path=self._repo_path,
    module_names=self._module_names,
    tool_names=vendor_names,
)
```

Also make an empty vendor set safe. Some registries treat an empty include list as “load everything”:

```python
engine = engine_cls()
if not tool_names:
    return engine
# Existing load_tools/loaded-name verification follows.
```

For `pathway_context`, the expected loaded routes become:

```text
local:  ReactomeContent_search
vendor: PathwayCommons_search, kegg_search_pathway
```

### 5.5 Thread the mapping through workflow execution

Add `local_tool_overrides` to `run_workflow()` and `run_workflow_step()` parameters. Pass `self._local_tool_overrides` from the list comprehension in `run_workflows()`.

Then replace the direct runner block in `run_workflow_step()`:

```python
def run_workflow_step(
    *,
    workflow: str,
    step_index: int,
    step: dict[str, Any],
    engine: Any,
    context: dict[str, Any],
    local_tool_overrides: Mapping[str, LocalToolOverride],
) -> Any:
    validate_required_context(workflow, step_index, step, context)
    tool_name = str(step["tool_name"]).strip()
    arguments = render_arguments(step.get("arguments", {}), context)
    if bool(step.get("omit_empty", False)):
        arguments = omit_empty_arguments(arguments)

    override = local_tool_overrides.get(tool_name)
    if override is not None:
        try:
            result = override.run(
                arguments=arguments,
                context=context,
                use_cache=bool(step.get("use_cache", False)),
                validate=bool(step.get("validate", True)),
            )
        except (ValueError, ProviderUnavailableError) as error:
            raise ToolUniverseWorkflowError(
                "Local ToolUniverse override failed: "
                f"{workflow}[{step_index}] {tool_name}: {error}"
            ) from error
    else:
        runner = getattr(engine, "run_one_function", None)
        if runner is None:
            raise ToolUniverseWorkflowError(
                "ToolUniverse.run_one_function is unavailable"
            )
        try:
            result = runner(
                {"name": tool_name, "arguments": arguments},
                use_cache=bool(step.get("use_cache", False)),
                validate=bool(step.get("validate", True)),
            )
        except Exception as error:
            # Retain the current broad vendor boundary: upstream tools expose
            # heterogeneous exception types.
            raise ToolUniverseWorkflowError(
                "ToolUniverse tool failed: "
                f"{workflow}[{step_index}] {tool_name}: {error}"
            ) from error

    reject_tool_error_result(
        workflow,
        step_index,
        tool_name,
        result,
    )
    return result
```

Arguments are rendered once and both routes pass through the existing error-result rejection and evidence normalization.

### 5.6 Make runtime health cover vendor and local routes

Health should validate the required workflow set, not make every optional configured workflow a readiness dependency.

Recommended flow:

```python
catalog = load_workflow_catalog(self._workflow_config_path)
validate_override_names_in_catalog(
    catalog=catalog,
    overrides=self._local_tool_overrides,
)
required_names = workflow_tool_names(
    catalog,
    catalog.required_workflows,
)
vendor_names = vendor_tool_names(
    required_names,
    frozenset(self._local_tool_overrides),
)
engine = load_tooluniverse_engine(..., tool_names=vendor_names)
vendor_loaded = loaded_tool_names(engine)

local_health = {
    name: handler.health_report()
    for name, handler in self._local_tool_overrides.items()
    if name in set(required_names)
}
```

Aggregate without removing existing keys:

```python
local_loaded = {
    name
    for name, report in local_health.items()
    if report.get("status") == "healthy"
}
loaded_union = vendor_loaded | local_loaded
missing_tools = sorted(set(required_names) - loaded_union)
unhealthy_local = sorted(
    name
    for name, report in local_health.items()
    if report.get("status") != "healthy"
)
runtime_ready = not missing_tools and not unhealthy_local
```

Add fields such as:

```json
{
  "runtime_ready": true,
  "vendor_loaded_tools": ["..."],
  "local_tool_overrides": ["ReactomeContent_search"],
  "local_tool_health": {
    "ReactomeContent_search": {
      "status": "healthy",
      "reactome_graphdb_available": true,
      "reactome_graphdb_database": "graph.db",
      "reactome_graphdb_configured_release": "97",
      "reactome_graphdb_actual_release": "97",
      "reactome_graphdb_release_matches": true,
      "reactome_pathway_count": 1
    }
  },
  "loaded_tools": ["ReactomeContent_search", "..."],
  "missing_configured_tools": []
}
```

Do not hard-code pathway count. Require it to be positive.

### 5.7 Close long-lived resources

Add:

```python
def close(self) -> None:
    seen: set[int] = set()
    for handler in self._local_tool_overrides.values():
        identity = id(handler)
        if identity in seen:
            continue
        seen.add(identity)
        handler.close()
```

Deduplicating by object identity makes cleanup safe if a future handler is intentionally exposed under more than one governed name.

### Step 5 acceptance criteria

- `ReactomeContent_search` is not passed to `ToolUniverse.load_tools()` in local mode.
- PathwayCommons and KEGG still load and execute through real ToolUniverse.
- The workflow JSON and public tool name are unchanged.
- `pathway_genes` contains true genes only; alteration labels are excluded.
- Local and vendor paths share argument rendering, error rejection, and evidence flattening.
- Health requires all required routes, including local GraphDB.
- Cleanup closes the driver exactly once.

---

## Step 6 — Compose the override in `tooluniverse-service`

Create:

```text
services/tooluniverse-service/src/tooluniverse_service/local_tool_overrides.py
```

### 6.1 Pure environment parsing

```python
from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from translume_adapters.tool_providers.reactome_graphdb import (
    Neo4jReactomeSearchBackend,
    ReactomeContentSearchOverride,
    ReactomeGraphDBConfig,
    validate_reactome_graphdb_config,
)
from translume_adapters.tool_providers.tooluniverse_runtime import (
    LocalToolOverride,
)


def truthy(value: str | None) -> bool:
    return str(value or "").strip().casefold() in {
        "1", "true", "yes", "on"
    }


def positive_float(
    environment: Mapping[str, str],
    name: str,
    default: str,
) -> float:
    try:
        value = float(environment.get(name, default).strip())
    except ValueError as error:
        raise ValueError(f"{name} must be a number") from error
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def bounded_int(
    environment: Mapping[str, str],
    name: str,
    default: str,
    *,
    minimum: int,
    maximum: int,
) -> int:
    try:
        value = int(environment.get(name, default).strip())
    except ValueError as error:
        raise ValueError(f"{name} must be an integer") from error
    if not minimum <= value <= maximum:
        raise ValueError(
            f"{name} must be between {minimum} and {maximum}"
        )
    return value
```

### 6.2 Construct one immutable mapping

```python
def build_local_tool_overrides(
    environment: Mapping[str, str],
) -> Mapping[str, LocalToolOverride]:
    if not truthy(environment.get("REACTOME_LOCAL_ENABLED")):
        return MappingProxyType({})

    if truthy(environment.get("REACTOME_REMOTE_FALLBACK")):
        raise ValueError(
            "REACTOME_REMOTE_FALLBACK must remain false"
        )

    config = ReactomeGraphDBConfig(
        uri=environment.get(
            "REACTOME_NEO4J_URI",
            "bolt://reactome-graphdb:7687",
        ).strip(),
        database=environment.get(
            "REACTOME_NEO4J_DATABASE",
            "graph.db",
        ).strip(),
        auth_mode=environment.get(
            "REACTOME_NEO4J_AUTH_MODE",
            "basic",
        ).strip().casefold(),
        username=(
            environment.get("REACTOME_NEO4J_USER", "neo4j").strip()
            or None
        ),
        password=(
            environment.get("REACTOME_NEO4J_PASSWORD", "")
            or None
        ),
        release=environment.get("REACTOME_RELEASE", "").strip(),
        query_timeout_seconds=positive_float(
            environment,
            "REACTOME_QUERY_TIMEOUT_SECONDS",
            "30",
        ),
        max_results=bounded_int(
            environment,
            "REACTOME_MAX_RESULTS",
            "30",
            minimum=1,
            maximum=30,
        ),
        max_query_terms=bounded_int(
            environment,
            "REACTOME_MAX_QUERY_TERMS",
            "8",
            minimum=1,
            maximum=32,
        ),
    )
    validate_reactome_graphdb_config(config)

    backend = Neo4jReactomeSearchBackend(config)
    override = ReactomeContentSearchOverride(
        config=config,
        backend=backend,
    )
    return MappingProxyType({override.tool_name: override})
```

Default the Python flag to off so isolated vendor-only tests do not unexpectedly require Neo4j. Compose, `.env.example`, and production validation turn it on explicitly.

### 6.3 Cache one runtime per service worker

Modify `services/tooluniverse-service/src/tooluniverse_service/main.py`.

```python
from contextlib import asynccontextmanager
from functools import lru_cache

from fastapi.responses import JSONResponse

from translume_adapters.errors import ProviderUnavailableError
from tooluniverse_service.local_tool_overrides import (
    build_local_tool_overrides,
    truthy,
)


@lru_cache(maxsize=1)
def _runtime() -> ToolUniverseRuntime:
    return ToolUniverseRuntime(
        repo_path=_repo_path(),
        workflow_config_path=_workflow_config_path(),
        module_names=_module_names(),
        local_tool_overrides=build_local_tool_overrides(os.environ),
    )


def reset_runtime_cache() -> None:
    if _runtime.cache_info().currsize:
        _runtime().close()
    _runtime.cache_clear()


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        yield
    finally:
        reset_runtime_cache()


app = FastAPI(
    title="tooluniverse_service",
    lifespan=lifespan,
)
```

Remove the old `app = FastAPI(...)` declaration. Tests that monkeypatch environment must reset the cache before and after:

```python
@pytest.fixture(autouse=True)
def isolated_tooluniverse_runtime():
    reset_runtime_cache()
    yield
    reset_runtime_cache()
```

### 6.4 Make `/health` readiness-aware

The current endpoint returns HTTP 200 even when the report contains failures. It should return 503 until vendor tools, workflow config, and local Reactome are all ready.

Implementation shape:

```python
@app.get("/health")
def health() -> JSONResponse:
    try:
        report = _runtime().health_report()
    except (
        ValueError,
        ProviderUnavailableError,
        ToolUniverseWorkflowError,
    ) as error:
        return JSONResponse(
            status_code=503,
            content={
                "status": "degraded",
                "service": "tooluniverse_service",
                "runtime_ready": False,
                "required_workflows_configured": False,
                "reactome_local_enabled": truthy(
                    os.getenv("REACTOME_LOCAL_ENABLED")
                ),
                "reactome_graphdb_available": False,
                "remote_reactome_enabled": False,
                "error": f"{type(error).__name__}: {str(error)[:500]}",
            },
        )

    local_health = report.get("local_tool_health", {})
    reactome = (
        local_health.get("ReactomeContent_search", {})
        if isinstance(local_health, dict)
        else {}
    )
    ready = bool(report.get("runtime_ready"))
    payload = {
        "status": "ok" if ready else "degraded",
        "service": "tooluniverse_service",
        "vendor_path": str(_repo_path()),
        "workflow_config": str(_workflow_config_path()),
        "required_workflows_configured": not bool(
            report.get("missing_required_workflows")
        ),
        "reactome_local_enabled": (
            "ReactomeContent_search"
            in report.get("local_tool_overrides", [])
        ),
        "reactome_graphdb_available": bool(
            reactome.get("reactome_graphdb_available")
        ),
        "reactome_graphdb_database": reactome.get(
            "reactome_graphdb_database"
        ),
        "reactome_graphdb_configured_release": reactome.get(
            "reactome_graphdb_configured_release"
        ),
        "reactome_graphdb_actual_release": reactome.get(
            "reactome_graphdb_actual_release"
        ),
        "reactome_graphdb_release_matches": bool(
            reactome.get("reactome_graphdb_release_matches")
        ),
        "reactome_pathway_count": reactome.get(
            "reactome_pathway_count"
        ),
        "remote_reactome_enabled": False,
        **report,
    }
    return JSONResponse(
        status_code=200 if ready else 503,
        content=payload,
    )
```

Keep `/workflows` request and response unchanged. A local connectivity failure remains an explicit `ToolUniverseWorkflowError` through the current 422 mapping. A later API-semantics ticket may map provider outages to 502; that is not required to eliminate the Cloudflare path.

### Step 6 acceptance criteria

- One runtime and Neo4j driver exist per Uvicorn worker.
- Lifespan shutdown closes and clears them.
- Environment-mutating tests are isolated with cache reset.
- `/health` returns 503 while GraphDB starts, is empty, has wrong release, or is unreachable.
- `/health` returns 200 only when the complete required runtime is ready.
- No credentials appear in health output.
- `/workflows` schema remains unchanged.

---

## Step 7 — Preserve direct-runtime provider parity

Modify `tooluniverse_provider.py` to accept an optional final parameter:

```python
from collections.abc import Mapping

class ToolUniverseProvider:
    def __init__(
        self,
        config: ToolUniverseProviderConfig | str | Path,
        workflow_config_path: Path | None = None,
        module_names: tuple[str, ...] = ("tooluniverse",),
        local_tool_overrides: Mapping[str, LocalToolOverride] | None = None,
    ) -> None:
        self._runtime: ToolUniverseRuntime | None = None
        if workflow_config_path is not None:
            self._config = None
            self._runtime = ToolUniverseRuntime(
                repo_path=Path(config),
                workflow_config_path=workflow_config_path,
                module_names=module_names,
                local_tool_overrides=local_tool_overrides,
            )
            return

        if local_tool_overrides:
            raise ProviderUnavailableError(
                "local overrides are valid only in direct runtime mode; "
                "HTTP-mode overrides belong in tooluniverse-service"
            )
        # Existing HTTP-mode configuration remains unchanged.

    def close(self) -> None:
        if self._runtime is not None:
            self._runtime.close()
```

### Step 7 acceptance criteria

- Existing HTTP constructor calls remain valid.
- Direct tests can inject a fake local Reactome handler.
- HTTP mode rejects, rather than ignores, a local mapping.
- `run_workflows()` remains unchanged.

---
## Step 8 — Enforce the deployment contract with PRIME_DIRECTIVES

Modify:

```text
packages/translume-core/src/translume_core/prime_directives/gate.py
```

Add `REACTOME_LOCAL_ENABLED` to `REQUIRED_TRUE_FLAGS` and add these to `REQUIRED_NONEMPTY_ENV`:

```python
"REACTOME_GRAPHDB_IMAGE",
"REACTOME_RELEASE",
"REACTOME_NEO4J_URI",
"REACTOME_NEO4J_DATABASE",
"REACTOME_NEO4J_AUTH_MODE",
"REACTOME_NEO4J_USER",
"REACTOME_NEO4J_PASSWORD",
```

Add a semantic validator rather than relying only on non-empty strings:

```python
from urllib.parse import urlparse


def validate_local_reactome_runtime(
    environment: Mapping[str, str],
) -> tuple[PrimeDirectiveFinding, ...]:
    findings: list[PrimeDirectiveFinding] = []
    image = env_value("REACTOME_GRAPHDB_IMAGE", environment)
    release = env_value("REACTOME_RELEASE", environment)
    uri = env_value("REACTOME_NEO4J_URI", environment)
    database = env_value("REACTOME_NEO4J_DATABASE", environment)
    auth_mode = env_value(
        "REACTOME_NEO4J_AUTH_MODE",
        environment,
    ).casefold()

    expected_prefix = "public.ecr.aws/reactome/graphdb:"
    expected_tag = f"Release{release}" if release else ""

    if not image.startswith(expected_prefix):
        findings.append(
            PrimeDirectiveFinding(
                rule_id="reactome:image_public_ecr",
                severity="error",
                message=(
                    "REACTOME_GRAPHDB_IMAGE must use the official "
                    "Reactome AWS Public ECR repository."
                ),
                next_actions=(
                    "Use public.ecr.aws/reactome/graphdb:Release<N>.",
                ),
            )
        )
    elif (
        image.endswith(":latest")
        or not expected_tag
        or not image.endswith(f":{expected_tag}")
    ):
        findings.append(
            PrimeDirectiveFinding(
                rule_id="reactome:image_release_pinned",
                severity="error",
                message=(
                    "Reactome image tag must be pinned and match "
                    "REACTOME_RELEASE."
                ),
                next_actions=(
                    "Use matching values such as Release97 and 97.",
                    "Verify with docker compose pull reactome-graphdb.",
                ),
            )
        )

    parsed = urlparse(uri)
    if parsed.scheme not in {"bolt", "neo4j"}:
        findings.append(
            PrimeDirectiveFinding(
                rule_id="reactome:bolt_uri",
                severity="error",
                message=(
                    "REACTOME_NEO4J_URI must use bolt:// or neo4j://."
                ),
                next_actions=(
                    "Use bolt://reactome-graphdb:7687.",
                ),
            )
        )
    if "reactome.org" in uri.casefold():
        findings.append(
            PrimeDirectiveFinding(
                rule_id="reactome:no_remote_host",
                severity="error",
                message=(
                    "Reactome runtime must use the local GraphDB container."
                ),
                next_actions=(
                    "Use the Compose hostname reactome-graphdb.",
                ),
            )
        )
    if not database:
        findings.append(
            PrimeDirectiveFinding(
                rule_id="reactome:database_required",
                severity="error",
                message="REACTOME_NEO4J_DATABASE is required.",
                next_actions=(
                    "Set the database verified for the pinned image.",
                ),
            )
        )
    if auth_mode != "basic":
        findings.append(
            PrimeDirectiveFinding(
                rule_id="reactome:auth_mode",
                severity="error",
                message=(
                    "Production/demo Reactome must use explicit basic auth."
                ),
                next_actions=(
                    "Set REACTOME_NEO4J_AUTH_MODE=basic.",
                ),
            )
        )
    if truthy(env_value("REACTOME_REMOTE_FALLBACK", environment)):
        findings.append(
            PrimeDirectiveFinding(
                rule_id="reactome:remote_fallback_disabled",
                severity="error",
                message="Remote Reactome fallback is prohibited.",
                next_actions=(
                    "Set REACTOME_REMOTE_FALLBACK=false.",
                ),
            )
        )
    return tuple(findings)
```

Call it from `validate_prime_directives()` after the existing required-environment checks:

```python
findings.extend(validate_local_reactome_runtime(environment))
```

Also validate the integer/timeout ranges with small pure functions. Do not import the service package into core.

### Full-stack requirement update

Update the ToolUniverse entry in `configs/integration/full_stack_requirements.json` with stable readiness fields:

```json
{
  "status": "ok",
  "vendor_available": true,
  "workflow_config_valid": true,
  "runtime_ready": true,
  "required_workflows_configured": true,
  "missing_required_workflows": [],
  "reactome_local_enabled": true,
  "reactome_graphdb_available": true,
  "reactome_graphdb_database": "graph.db",
  "reactome_graphdb_configured_release": "97",
  "reactome_graphdb_actual_release": "97",
  "reactome_graphdb_release_matches": true,
  "remote_reactome_enabled": false,
  "local_tool_overrides": ["ReactomeContent_search"]
}
```

Do not require an exact pathway count in JSON. Integration code should assert a positive integer so release updates do not require brittle count changes.

### Step 8 acceptance criteria

- Production/demo validation rejects local mode off, remote fallback on, `latest`, tag/release mismatch, non-ECR images, HTTP/remote URIs, and invalid auth.
- Local developer mode remains inactive unless the existing PRIME_DIRECTIVES switch is enabled.
- Full-stack health proves the exact Reactome name is local and the graph release matches.

---

## Step 9 — Align Compose, Makefile, and operator commands

### 9.1 Make Compose use the same env file for interpolation

At the top of `Makefile`, replace the current Compose declaration with:

```make
TRANSLUME_ENV_FILE ?= .env
COMPOSE ?= docker compose --env-file $(TRANSLUME_ENV_FILE)
export TRANSLUME_ENV_FILE
```

This is required because `env_file:` is applied to containers after Compose has already interpolated the image tag.

### 9.2 Add image and smoke targets

Add to `.PHONY`:

```make
reactome-image reactome-status reactome-smoke
```

Targets:

```make
reactome-image:
	$(COMPOSE) pull reactome-graphdb

reactome-status:
	$(COMPOSE) ps reactome-graphdb tooluniverse-service
	curl -fsS "$${TOOLUNIVERSE_PUBLIC_URL:-http://localhost:8092}/health" | python -m json.tool

reactome-smoke:
	$(PYTHON) scripts/smoke_local_reactome_workflow.py \
		--base-url "$${TOOLUNIVERSE_PUBLIC_URL:-http://localhost:8092}" \
		--expected-release "$${REACTOME_RELEASE:?set REACTOME_RELEASE}"
```

Make image preparation part of the existing full-stack path:

```make
prepare-full-stack: check-local-data-ignore mims-data reactome-image
```

### 9.3 Validate rendered configuration

Before startup:

```bash
make docker-config

grep -A4 'reactome-graphdb:' /tmp/translume-compose.yaml
```

The rendered image tag and `REACTOME_RELEASE` must correspond. A custom `TRANSLUME_ENV_FILE` must work without exporting every individual variable.

### Step 9 acceptance criteria

- `make docker-config TRANSLUME_ENV_FILE=.env.production` renders the production image tag from that file.
- `make reactome-image` pulls only from `public.ecr.aws`.
- `make reactome-smoke` exercises `/workflows`, not direct Neo4j only.
- Existing full-stack commands still work.

---

## Step 10 — Add tests at every real boundary

Follow the repository's existing test locations and fake-package patterns. Do not create a disconnected testing hierarchy.

### 10.1 Pure adapter tests

Create `tests/unit/test_reactome_graphdb_adapter.py` and cover:

```text
test_config_rejects_http_or_reactome_org_uri
test_config_rejects_missing_basic_credentials
test_config_password_is_not_in_repr
test_normalize_request_accepts_string_types
test_normalize_request_accepts_list_types
test_normalize_request_uses_structured_genes_and_terms
test_normalize_request_caps_genes_and_terms
test_normalize_request_falls_back_for_direct_query_only_call
test_copy_number_alteration_labels_are_not_gene_identifiers
test_merge_deduplicates_by_stable_id
test_exact_stable_id_ranks_first
test_tooluniverse_response_matches_contract_fixture
test_zero_matches_are_success
test_backend_error_is_explicit
test_close_is_idempotent
```

Use an immutable fake backend:

```python
@dataclass(frozen=True)
class FakeReactomeBackend:
    text: tuple[ReactomePathwayMatch, ...] = ()
    genes: tuple[ReactomePathwayMatch, ...] = ()

    def search_text(self, **_: object):
        return self.text

    def search_genes(self, **_: object):
        return self.genes

    def health_report(self):
        return {
            "status": "healthy",
            "reactome_graphdb_available": True,
            "reactome_graphdb_database": "graph.db",
            "reactome_graphdb_configured_release": "97",
            "reactome_graphdb_actual_release": "97",
            "reactome_graphdb_release_matches": True,
            "reactome_pathway_count": 1,
            "error": None,
        }

    def close(self):
        return None
```

### 10.2 Context tests

Extend `tests/unit/test_tooluniverse_workflow_config.py`:

```python
context = template_context(entities, graph)

assert context["pathway_genes"] == ["EGFR"]
assert len(context["pathway_genes"]) <= MAX_TOOL_QUERY_TERMS
assert len(context["pathway_terms"]) <= MAX_TOOL_QUERY_TERMS
assert "lung cancer" in context["pathway_terms"]
assert "participates_in" not in context["pathway_terms"]
assert context["pathway_query"]  # existing free-text behavior remains
```

Add a copy-number fixture in which the report has both a true `gene` entity and a `copy_number_loss` alteration entity. Assert only the gene symbol appears in `pathway_genes`.

### 10.3 Runtime dispatch tests

Test the central seam directly:

- local exact-name handler is called;
- vendor runner is not called for `ReactomeContent_search`;
- `ReactomeContent_search` is excluded from `load_tools(include_tools=...)`;
- vendor runner is still called for PathwayCommons and KEGG;
- local output passes through `reject_tool_error_result()`;
- unknown override names fail catalog validation;
- empty vendor name tuples do not load every vendor tool;
- runtime cleanup closes the override.

A strong regression assertion:

```python
assert "ReactomeContent_search" not in fake_engine.loaded_names
assert fake_override.calls == 1
assert "PathwayCommons_search" in fake_engine.loaded_names
assert "kegg_search_pathway" in fake_engine.loaded_names
```

### 10.4 Service tests

Extend `tests/unit/test_real_mims_service_execution.py` using the existing fake ToolUniverse package approach.

Add:

- cached `_runtime()` returns the same object until reset;
- cache reset closes the local handler;
- `/health` is 503 when fake GraphDB is unhealthy;
- `/health` is 200 when local and vendor routes are healthy;
- `/workflows` completes all three `pathway_context` steps;
- Reactome evidence has local metadata;
- later vendor steps still produce evidence.

When invoking endpoint functions directly, reset the cache around environment mutations.

### 10.5 HTTP client contract tests

`tests/unit/test_mims_clients.py` should prove `ToolUniverseServiceClient` sends the same payload and validates the same `artifacts` list. No Neo4j fields should leak into the client API.

### 10.6 PRIME_DIRECTIVES and full-stack contract tests

Extend:

```text
tests/unit/test_prime_directives_gate.py
tests/integration/test_full_stack_integration_contract.py
```

Cover valid pinned config and each rejection rule independently. Assert positive pathway count in integration logic rather than exact equality.

### 10.7 Prove there is no remote Reactome call

In unit tests, fail any attempted HTTP request to Reactome:

```python
def fail_remote(*args, **kwargs):
    raise AssertionError("remote Reactome HTTP call attempted")

monkeypatch.setattr("requests.get", fail_remote)
```

Then run `pathway_context`. Because the vendor Reactome implementation is not loaded, the monkeypatch should never fire.

Also assert the vendor loader's include list excludes `ReactomeContent_search`; this is stronger than relying only on an HTTP monkeypatch.

### 10.8 Live ECR integration test

Add an opt-in marker, for example `live_reactome_graphdb`, that posts to `/workflows` rather than connecting directly to Neo4j. Assert:

- HTTP 200;
- one `pathway_context` artifact;
- one evidence item with `tool_name == "ReactomeContent_search"`;
- decoded `data.results` is non-empty for a representative gene;
- returned stable IDs begin with `R-HSA-`;
- decoded metadata says local GraphDB, expected release, and `remote_api_used == false`;
- PathwayCommons and KEGG evidence items also exist.

Do not assert one exact pathway name for a broad gene query unless tied to the pinned release fixture.

### 10.9 End-to-end report regression

Run an existing de-identified report fixture through:

```text
POST /api/v1/reports/process
```

Assert:

- the prior Cloudflare/MIMS 422 string is absent;
- a `pathway_context` ToolRunArtifact exists;
- its Reactome evidence decodes to local GraphDB provenance;
- report processing continues through later workflows and review-packet construction;
- no connection is observed to `reactome.org` or `download.reactome.org` during processing.

### Step 10 acceptance criteria

- Unit tests need no Docker/network.
- A live opt-in test exercises the official ECR image end to end.
- Tests prove both local interception and continued vendor execution.
- Tests prove copy-number alteration prose is not sent to gene traversal.
- The exact production failure path has a report-level regression test.

---

## Step 11 — Validate the pinned ECR image before approving Cypher

The ECR image's actual schema and auth behavior are the source of truth. Complete this gate for every release.

### 11.1 Pull and start only GraphDB

```bash
export TRANSLUME_ENV_FILE=.env

docker compose --env-file "$TRANSLUME_ENV_FILE" pull reactome-graphdb
docker compose --env-file "$TRANSLUME_ENV_FILE" up -d reactome-graphdb
```

### 11.2 Verify one configured credential and discover the database

Use the same user/password the service will use. Do not print the password, guess alternatives, or add runtime probing.

```bash
docker compose --env-file "$TRANSLUME_ENV_FILE" run --rm --no-deps \
  tooluniverse-service python - <<'PY'
from __future__ import annotations

import os
from neo4j import GraphDatabase

uri = os.environ["REACTOME_NEO4J_URI"]
auth = (
    os.environ["REACTOME_NEO4J_USER"],
    os.environ["REACTOME_NEO4J_PASSWORD"],
)

with GraphDatabase.driver(uri, auth=auth) as driver:
    driver.verify_connectivity()
    print({"connectivity": "ok", "user": auth[0]})

    # Deployment discovery only. Runtime uses exactly one configured database.
    for database in ("graph.db", "neo4j", "reactome"):
        try:
            records, _, _ = driver.execute_query(
                """
                OPTIONAL MATCH (info:DBInfo)
                WITH head(collect(info.version)) AS graph_version
                MATCH (p:Pathway)
                RETURN graph_version, count(p) AS pathway_count
                """,
                database_=database,
            )
            print({"database": database, **records[0].data()})
        except Exception as error:
            print({
                "database": database,
                "error_type": type(error).__name__,
                "error": str(error)[:300],
            })
PY
```

Once identified, configure one database and remove all probing from normal runtime.

### 11.3 Inspect required schema

Run and save outputs:

```cypher
MATCH (info:DBInfo)
RETURN info.version AS graph_version
LIMIT 1;
```

```cypher
MATCH (p:Pathway)
OPTIONAL MATCH (species:Species)<-[:species]-(p)
RETURN labels(p), keys(p), p.stId, p.displayName,
       species.taxId, species.displayName, p.isInDisease
LIMIT 10;
```

```cypher
MATCH (reference)-[:referenceDatabase]->(rd:ReferenceDatabase)
WHERE toLower(rd.displayName) = 'uniprot'
RETURN labels(reference), keys(reference), reference.identifier,
       reference.variantIdentifier, reference.geneName, reference.name
LIMIT 20;
```

```cypher
MATCH (rle:ReactionLikeEvent)-[r]->(pe:PhysicalEntity)
RETURN type(r), labels(pe), count(*) AS occurrences
ORDER BY occurrences DESC
LIMIT 30;
```

```cypher
MATCH (p:Pathway)-[r]->(event)
RETURN type(r), labels(event), count(*) AS occurrences
ORDER BY occurrences DESC
LIMIT 30;
```

If labels/properties differ, change only the Cypher constants and record mappers in `reactome_graphdb.py`. Do not leak release-specific graph details into the workflow runtime.

### 11.4 Validate representative searches

At minimum test:

```text
TP53
EGFR
MTAP
R-HSA-199420
PI3K AKT signaling
```

Confirm report-normalized gene symbols match `geneName` or another property in the image. If they do not, add a local graph-based mapping strategy. Do not call an external identifier API at runtime.

### 11.5 Compare bounded traversal with Reactome's diagnostic traversal

For each representative gene:

1. resolve the same `ReferenceEntity`/UniProt record;
2. run Reactome's documented unbounded diagnostic query in the release-validation environment only;
3. run the proposed bounded production query;
4. compare the sets of returned `p.stId` values;
5. use `PROFILE` to measure expansion and latency;
6. increase only the smallest bound that omits expected pathways;
7. rerun the comparison and performance test.

Diagnostic shape:

```cypher
MATCH (n)-[:referenceDatabase]->(rd:ReferenceDatabase)
WHERE toLower(rd.displayName) = toLower('UniProt')
  AND (
    n.identifier = $identifier
    OR n.variantIdentifier = $identifier
    OR $identifier IN n.geneName
    OR $identifier IN n.name
  )
WITH DISTINCT n
MATCH (pe:PhysicalEntity)
  -[:referenceEntity|referenceSequence|crossReference|referenceGene*]->(n)
WITH DISTINCT pe
MATCH (rle:ReactionLikeEvent)
  -[:input|output|catalystActivity|physicalEntity|entityFunctionalStatus|
    diseaseEntity|regulatedBy|regulator|hasComponent|hasMember|
    hasCandidate|repeatedUnit*]->(pe)
WITH DISTINCT rle
MATCH (:Species {taxId:'9606'})<-[:species]-(p:Pathway)
  -[:hasEvent]->(rle)
RETURN DISTINCT p.stId AS stable_id
ORDER BY stable_id;
```

Never ship the unbounded query in request handling.

### 11.6 Record latency

Measure warmed p50/p95 for:

- health/release count;
- one pathway name;
- one stable ID;
- one gene;
- eight genes/terms.

Initial engineering target:

```text
single local Reactome override p95 <= 5 seconds
```

If slower, first inspect `EXPLAIN`/`PROFILE`, shipped indexes, candidate limits, and traversal caps. Do not mutate the official release image or add APOC until measurements justify it.

### Step 11 acceptance criteria

- Image tag, basic credential, driver, and database are verified together.
- Graph release equals `REACTOME_RELEASE` after normalization.
- Pathway count is positive.
- Required labels/properties/relationships exist.
- Representative gene and text searches return plausible human pathways.
- Bounded traversal does not lose expected pathways relative to the diagnostic set.
- Query latency is measured and recorded.
- Runtime contains no database/password/auth guessing.

---

## Step 12 — Deployment, operations, and rollback

### Deployment order

1. Merge unit-tested adapter/runtime/service changes.
2. Build ToolUniverse service with the Neo4j driver.
3. Pull the pinned ECR GraphDB image.
4. Run Step 11 against GraphDB alone.
5. Start ToolUniverse with local Reactome enabled.
6. Wait for `/health` HTTP 200 and `runtime_ready: true`.
7. Run the `/workflows` pathway smoke test.
8. Start/restart Translume API.
9. Run one de-identified `/api/v1/reports/process` regression.
10. Start the remaining stack/UI.

### Logging

Emit one bounded structured event per local search:

```json
{
  "event": "reactome_local_search",
  "tool": "ReactomeContent_search",
  "release": "97",
  "database": "graph.db",
  "query_term_count": 4,
  "gene_count": 2,
  "text_candidate_count": 10,
  "gene_candidate_count": 16,
  "result_count": 20,
  "duration_ms": 184,
  "remote_api_used": false
}
```

Never log passwords, full report text, patient identifiers, or unbounded entity lists.

Recommended metrics:

```text
reactome_local_search_requests_total
reactome_local_search_failures_total
reactome_local_search_duration_seconds
reactome_local_search_results
reactome_graphdb_ready
reactome_graphdb_pathway_count
```

### Failure behavior

If GraphDB becomes unavailable:

- the current request fails explicitly through `ToolUniverseWorkflowError`;
- `/health` becomes 503/degraded;
- Docker marks ToolUniverse unhealthy;
- no remote Reactome fallback runs;
- no partial result is mislabeled as live Reactome evidence.

Making pathway context optional can be a later resilience ticket. First preserve the repository's current fail-loudly rule for required MIMS services.

### Release upgrade

For release `N`:

1. set `REACTOME_GRAPHDB_IMAGE=public.ecr.aws/reactome/graphdb:ReleaseN`;
2. set `REACTOME_RELEASE=N`;
3. verify rendered Compose config;
4. pull in non-production;
5. repeat auth/database/schema/bounded-query validation;
6. run unit and live tests;
7. compare pathway count and representative search behavior;
8. deploy GraphDB and ToolUniverse together;
9. retain the previous tag for rollback.

Rollback is an image/config rollback, not a data download:

```bash
# Restore prior matching values in the deployment env file, then:
docker compose --env-file "$TRANSLUME_ENV_FILE" pull reactome-graphdb
docker compose --env-file "$TRANSLUME_ENV_FILE" up -d --force-recreate \
  reactome-graphdb tooluniverse-service
```

---

## 7. Consolidated acceptance criteria

### Architecture

- [ ] The governed name remains `ReactomeContent_search`.
- [ ] `ToolProvider`, MIMS client, `/workflows`, and report API contracts are unchanged.
- [ ] No Harvard MIMS ToolUniverse source is patched.
- [ ] The override is implemented at `run_workflow_step()`.
- [ ] Non-overridden pathway tools still use real ToolUniverse.

### Data source and networking

- [ ] Reactome data comes from a pinned official `public.ecr.aws/reactome/graphdb:Release<N>` image.
- [ ] Compose interpolation and container env use the same deployment env file.
- [ ] Neo4j ports are private by default.
- [ ] Report processing makes no request to Reactome HTTP/API/download hosts.
- [ ] Remote fallback is disabled and production validation enforces it.

### Correctness

- [ ] The local result matches the vendored ToolUniverse status/data/metadata contract.
- [ ] Result species remains a list and public results are capped at 30.
- [ ] `pathway_genes` contains only normalized gene entities.
- [ ] Copy-number alteration text is not used as a gene identifier.
- [ ] Text, stable-ID, and gene results are deterministic and deduplicated.
- [ ] Zero matches are a successful empty result.
- [ ] Release metadata and `remote_api_used: false` are present.

### Runtime and operations

- [ ] One Neo4j driver exists per service worker.
- [ ] Runtime shutdown closes it idempotently.
- [ ] Vendor loading excludes the local name.
- [ ] Health is 503 until GraphDB, release, workflow catalog, and vendor tools are ready.
- [ ] A release mismatch keeps the service unhealthy.
- [ ] Secrets never appear in repr, logs, or health output.

### Verification

- [ ] Pure/unit tests run without Docker/network.
- [ ] Runtime tests prove local interception and later vendor execution.
- [ ] PRIME_DIRECTIVES tests cover all rejection rules.
- [ ] The live ECR test runs through `/workflows`.
- [ ] A de-identified report no longer produces the Cloudflare/MIMS 422 failure.
- [ ] Bounded Cypher is compared against Reactome's diagnostic traversal.
- [ ] Query latency is recorded and within the approved threshold.

---

## 8. Recommended pull-request sequence

Keep review and rollback manageable:

1. **PR 1 — Contract and pure adapter core**  
   Fixture, immutable records, normalization, ranking, response mapping, fake-backend tests.

2. **PR 2 — Runtime dispatch**  
   Generic override protocol, structured context, vendor-name exclusion, local step dispatch, health aggregation, direct-provider parity.

3. **PR 3 — Service lifecycle and deployment**  
   Override builder, cached runtime, lifespan cleanup, health semantics, Neo4j dependency, Compose/ECR/env/Makefile.

4. **PR 4 — Governance and integration tests**  
   PRIME_DIRECTIVES, full-stack health contract, smoke script, live ECR test, report regression, docs.

Do not merge deployment enablement until the pinned image passes Step 11.

---

## 9. Troubleshooting decision tree

### ECR image does not pull

- Check rendered tag with `docker compose --env-file ... config`.
- Confirm `Release<N>` exists.
- Do not use `latest`.
- Align `REACTOME_RELEASE` with the verified tag.

### Bolt connection fails

- Confirm `reactome-graphdb` and `tooluniverse-service` share the default network.
- Confirm URI is `bolt://reactome-graphdb:7687` inside Compose.
- Verify one configured credential against the pinned image.
- Inspect GraphDB logs; do not add password guessing.

### Database unavailable

- Run the Step 11 discovery script.
- Set one explicit database name.
- Confirm the image fully initialized before expecting health 200.

### Release mismatch

- Compare rendered image tag, `REACTOME_RELEASE`, and `DBInfo.version`.
- Recreate the container after changing image tag.
- Confirm no old data volume is masking the image snapshot.

### Reactome still calls the internet

- Inspect ToolUniverse `load_tools(include_tools=...)` in tests/logs.
- Confirm `ReactomeContent_search` is absent.
- Confirm the exact workflow name matches the override key.
- Confirm `REACTOME_LOCAL_ENABLED=true` reached the service container.
- Confirm no remote fallback exists.

### Local search returns no gene pathways

- Verify `pathway_genes` contains real gene symbols.
- Inspect reference entity properties in the pinned graph.
- Compare bounded and diagnostic traversal.
- Adjust only observed schema relationships/bounds.
- Do not parse alteration prose or call external mapping APIs at runtime.

---

## 10. Repository files reviewed

The implementation decisions above were aligned against these concrete files:

```text
packages/translume-ports/src/translume_ports/tool_provider.py
packages/translume-clients/src/translume_clients/mims.py
packages/translume-adapters/src/translume_adapters/tool_providers/tooluniverse_provider.py
packages/translume-adapters/src/translume_adapters/tool_providers/tooluniverse_runtime.py
packages/translume-adapters/src/translume_adapters/graph_providers/optimuskg_runtime.py
packages/translume-adapters/src/translume_adapters/graph_providers/optimuskg_graph_provider.py
packages/translume-core/src/translume_core/compiler/entity_normalization.py
packages/translume-core/src/translume_core/prime_directives/gate.py
services/tooluniverse-service/src/tooluniverse_service/main.py
services/tooluniverse-service/src/tooluniverse_service/vendor_runtime.py
services/medea-service/src/medea_service/local_runtime.py
services/medea-service/src/medea_service/main.py
configs/local/tooluniverse_workflows.json
configs/integration/full_stack_requirements.json
docker-compose.yml
docker/tooluniverse-service.Dockerfile
Makefile
.env.example
tests/unit/test_real_mims_service_execution.py
tests/unit/test_tooluniverse_workflow_config.py
tests/unit/test_adapters.py
tests/unit/test_mims_clients.py
tests/unit/test_prime_directives_gate.py
tests/integration/test_full_stack_integration_contract.py
third_party/zips/ToolUniverse.zip
```

---

## 11. External implementation references

- Reactome Graph Database deployment documentation: `https://reactome.org/dev/graph-database`
- Reactome AWS Public ECR repository: `public.ecr.aws/reactome/graphdb`
- Reactome Graph Database FAQ/query examples: `https://reactome.org/dev/graph-database`
- ToolUniverse extension documentation: `https://zitniklab.hms.harvard.edu/ToolUniverse/expand_tooluniverse/index.html`
- Neo4j Python driver compatibility/install documentation: `https://neo4j.com/docs/python-manual/current/install/`

---

## 12. Final intended behavior

```text
existing pathway_context workflow
  -> ReactomeContent_search
  -> ToolUniverseRuntime exact-name override
  -> local Reactome Neo4j query
  -> ToolUniverse-compatible local result
  -> existing evidence flattening
  -> PathwayCommons and KEGG vendor steps
  -> ToolRunArtifact
  -> report processing and review packet
```

The workflow, client, and report pipeline do not need to know the data source changed. The operational difference is that pathway search is now deterministic, release-pinned, locally queryable, and independent of Reactome's Cloudflare treatment of the AWS egress IP.
