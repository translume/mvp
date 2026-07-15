"""Local Reactome GraphDB adapter for the governed ToolUniverse runtime."""

from __future__ import annotations

import logging
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any, Protocol

from neo4j import GraphDatabase, Query, RoutingControl
from neo4j.exceptions import DriverError, Neo4jError

from translume_adapters.errors import ProviderUnavailableError


TEXT_PATHWAY_SEARCH = """
UNWIND $terms AS term
MATCH (species:Species {taxId: $tax_id})<-[:species]-(pathway:Pathway)
WHERE toLower(coalesce(pathway.stId, '')) = term
   OR toLower(coalesce(pathway.displayName, '')) CONTAINS term
WITH pathway, species, collect(DISTINCT term) AS matched_terms,
     max(CASE WHEN toLower(coalesce(pathway.stId, '')) = term
              THEN 1 ELSE 0 END) AS exact_stable_id,
     max(CASE WHEN toLower(coalesce(pathway.displayName, '')) = term
              THEN 1 ELSE 0 END) AS exact_name
RETURN pathway.stId AS stable_id,
       pathway.displayName AS name,
       species.displayName AS species,
       coalesce(pathway.isInDisease, false) AS is_disease,
       matched_terms,
       [] AS matched_genes
ORDER BY exact_stable_id DESC, exact_name DESC,
         size(matched_terms) DESC, pathway.displayName, pathway.stId
LIMIT $candidate_limit
"""

GENE_PATHWAY_SEARCH = """
UNWIND $genes AS gene
MATCH (reference)-[:referenceDatabase]->(database:ReferenceDatabase)
WHERE toLower(coalesce(database.displayName, '')) = 'uniprot'
  AND (
    toLower(coalesce(reference.identifier, '')) = gene
    OR toLower(coalesce(reference.variantIdentifier, '')) = gene
    OR any(symbol IN coalesce(reference.geneName, [])
           WHERE toLower(symbol) = gene)
    OR any(alias IN coalesce(reference.name, [])
           WHERE toLower(alias) = gene)
  )
WITH DISTINCT gene, reference
MATCH (physical:PhysicalEntity)
  -[:referenceEntity|referenceSequence|crossReference|referenceGene*1..4]->
  (reference)
WITH DISTINCT gene, physical
MATCH (reaction:ReactionLikeEvent)
  -[:input|output|catalystActivity|physicalEntity|entityFunctionalStatus|
    diseaseEntity|regulatedBy|regulator|hasComponent|hasMember|
    hasCandidate|repeatedUnit*1..8]->
  (physical)
WITH DISTINCT gene, reaction
MATCH (species:Species {taxId: $tax_id})<-[:species]-(pathway:Pathway)
  -[:hasEvent*1..12]->(reaction)
WITH pathway, species, collect(DISTINCT gene) AS matched_genes
RETURN pathway.stId AS stable_id,
       pathway.displayName AS name,
       species.displayName AS species,
       coalesce(pathway.isInDisease, false) AS is_disease,
       [] AS matched_terms,
       matched_genes
ORDER BY size(matched_genes) DESC, pathway.displayName, pathway.stId
LIMIT $candidate_limit
"""

GRAPH_INFO_QUERY = """
OPTIONAL MATCH (db_info:DBInfo)
WITH head(
  collect(coalesce(db_info.version, db_info.releaseNumber))
) AS graph_version
MATCH (pathway:Pathway)
RETURN graph_version, count(pathway) AS pathway_count
"""


class ReactomeGraphDBError(ProviderUnavailableError):
    """Raised when the local Reactome graph cannot serve a request."""


@dataclass(frozen=True)
class ReactomeGraphDBConfig:
    """Immutable local Reactome GraphDB configuration."""

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
    """Normalized request supported by the local Reactome v1 adapter."""

    query: str
    species: str
    types: tuple[str, ...]
    cluster: bool
    genes: tuple[str, ...]
    pathway_terms: tuple[str, ...]
    max_results: int


@dataclass(frozen=True)
class ReactomePathwayMatch:
    """Immutable pathway match returned from one local search strategy."""

    stable_id: str
    name: str
    species: str
    is_disease: bool
    matched_terms: tuple[str, ...] = ()
    matched_genes: tuple[str, ...] = ()
    score: int = 0


class ReactomeSearchBackend(Protocol):
    """Narrow I/O protocol used by the ToolUniverse-compatible override."""

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


def validate_reactome_graphdb_config(config: ReactomeGraphDBConfig) -> None:
    """Validate local-only GraphDB configuration.

    Acceptance criteria:
        1. Only Bolt/Neo4j URIs are accepted.
        2. Remote Reactome hosts are rejected.
        3. Basic authentication requires both configured credentials.
        4. Release and numeric bounds are explicit and deterministic.
    """
    if not config.uri.startswith(("bolt://", "neo4j://")):
        raise ValueError("REACTOME_NEO4J_URI must use bolt:// or neo4j://")
    if "reactome.org" in config.uri.casefold():
        raise ValueError("REACTOME_NEO4J_URI must point to local GraphDB")
    if not config.database.strip():
        raise ValueError("REACTOME_NEO4J_DATABASE is required")
    normalize_reactome_release(config.release)
    if config.auth_mode not in {"basic", "none"}:
        raise ValueError("REACTOME_NEO4J_AUTH_MODE must be basic or none")
    if config.auth_mode == "basic" and not (
        config.username and config.password
    ):
        raise ValueError(
            "REACTOME_NEO4J_USER and REACTOME_NEO4J_PASSWORD are required"
        )
    if config.query_timeout_seconds <= 0:
        raise ValueError("REACTOME_QUERY_TIMEOUT_SECONDS must be positive")
    if not 1 <= config.max_results <= 30:
        raise ValueError("REACTOME_MAX_RESULTS must be between 1 and 30")
    if not 1 <= config.max_query_terms <= 32:
        raise ValueError("REACTOME_MAX_QUERY_TERMS must be between 1 and 32")


def normalize_strings(value: object) -> tuple[str, ...]:
    """Return unique non-empty strings in deterministic input order."""
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
    """Normalize ToolUniverse's string-or-sequence `types` argument."""
    if isinstance(value, str):
        return normalize_strings(value.split(","))
    if isinstance(value, Sequence):
        return normalize_strings(value)
    raise TypeError("Reactome types must be a string or sequence")


def normalize_boolean(value: object) -> bool:
    """Normalize a strict boolean-compatible value."""
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
    """Return the positive numeric portion of a Reactome release."""
    text = str(value or "").strip().casefold()
    for prefix in ("release", "version", "v"):
        if text.startswith(prefix):
            text = text.removeprefix(prefix).strip()
            break
    if not text.isdigit() or int(text) <= 0:
        raise ValueError(f"Invalid Reactome release: {value!r}")
    return str(int(text))


def species_tax_id(species: str) -> str:
    """Return the taxon identifier for the only supported v1 species."""
    if species.strip().casefold() != "homo sapiens":
        raise ValueError("Local Reactome v1 supports only Homo sapiens")
    return "9606"


def normalize_reactome_search_request(
    *,
    arguments: Mapping[str, Any],
    context: Mapping[str, Any],
    config: ReactomeGraphDBConfig,
) -> ReactomeSearchRequest:
    """Return one validated, bounded local search request."""
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


def build_neo4j_auth(
    config: ReactomeGraphDBConfig,
) -> tuple[str, str] | None:
    """Return the configured Neo4j authentication tuple or no auth."""
    if config.auth_mode == "none":
        return None
    if config.auth_mode == "basic" and config.username and config.password:
        return (config.username, config.password)
    raise ValueError("Reactome basic auth requires credentials")


class Neo4jReactomeSearchBackend:
    """Long-lived Neo4j connection pool and sole GraphDB I/O boundary."""

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
        """Return bounded pathway text/stable-ID matches."""
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
        """Return bounded structured-gene pathway matches."""
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
        """Return connectivity, content, and release readiness without secrets."""
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
        """Close the driver once; repeated calls have no effect."""
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
                Query(cypher, timeout=self._config.query_timeout_seconds),
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


def require_row_text(row: Mapping[str, object], key: str) -> str:
    """Return a required non-empty text value from one Neo4j record."""
    value = str(row.get(key, "")).strip()
    if not value:
        raise ReactomeGraphDBError(
            f"Local Reactome row missing required field: {key}"
        )
    return value


def text_row_to_match(row: Mapping[str, object]) -> ReactomePathwayMatch:
    """Convert one text-query record at the I/O boundary."""
    return ReactomePathwayMatch(
        stable_id=require_row_text(row, "stable_id"),
        name=require_row_text(row, "name"),
        species=str(row.get("species") or "Homo sapiens").strip(),
        is_disease=bool(row.get("is_disease", False)),
        matched_terms=normalize_strings(row.get("matched_terms")),
    )


def gene_row_to_match(row: Mapping[str, object]) -> ReactomePathwayMatch:
    """Convert one gene-query record at the I/O boundary."""
    return ReactomePathwayMatch(
        stable_id=require_row_text(row, "stable_id"),
        name=require_row_text(row, "name"),
        species=str(row.get("species") or "Homo sapiens").strip(),
        is_disease=bool(row.get("is_disease", False)),
        matched_genes=normalize_strings(row.get("matched_genes")),
    )


def pathway_score(
    request: ReactomeSearchRequest,
    match: ReactomePathwayMatch,
) -> int:
    """Return a deterministic score for one merged pathway match."""
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
    """Return one immutable merged match for a shared stable identifier."""
    if left is None:
        merged = right
    else:
        if left.stable_id.casefold() != right.stable_id.casefold():
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
    """Deduplicate and deterministically rank matches without mutation."""
    by_id: dict[str, ReactomePathwayMatch] = {}
    for candidate in (*text_matches, *gene_matches):
        key = candidate.stable_id.casefold()
        by_id[key] = combine_matches(request, by_id.get(key), candidate)
    return tuple(
        sorted(
            by_id.values(),
            key=lambda item: (-item.score, item.name.casefold(), item.stable_id),
        )
    )


def to_tooluniverse_reactome_result(
    *,
    request: ReactomeSearchRequest,
    matches: Sequence[ReactomePathwayMatch],
    config: ReactomeGraphDBConfig,
) -> dict[str, object]:
    """Serialize matches using the upstream ToolUniverse response contract."""
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
            "configured_release": normalize_reactome_release(config.release),
            "remote_api_used": False,
            "match_strategies": ["pathway_text", "structured_gene"],
            "cluster_compatibility_value": request.cluster,
        },
    }


class ReactomeContentSearchOverride:
    """Exact-name local implementation of `ReactomeContent_search`."""

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
        """Execute a bounded local search and return vendor-compatible data."""
        del use_cache, validate
        started = time.monotonic()
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
        logging.info(
            "reactome_local_search tool=%s release=%s database=%s "
            "query_term_count=%d gene_count=%d text_candidate_count=%d "
            "gene_candidate_count=%d result_count=%d duration_ms=%d "
            "remote_api_used=false",
            self.tool_name,
            normalize_reactome_release(self._config.release),
            self._config.database,
            len(request.pathway_terms),
            len(request.genes),
            len(text_matches),
            len(gene_matches),
            len(matches),
            round((time.monotonic() - started) * 1000),
        )
        return to_tooluniverse_reactome_result(
            request=request,
            matches=matches,
            config=self._config,
        )

    def health_report(self) -> Mapping[str, object]:
        """Return local GraphDB readiness."""
        return self._backend.health_report()

    def close(self) -> None:
        """Close the backend connection pool."""
        self._backend.close()
