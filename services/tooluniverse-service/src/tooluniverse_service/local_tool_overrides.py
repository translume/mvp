"""Local ToolUniverse override composition owned by the service boundary."""

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
    """Return whether an environment value explicitly enables a feature."""
    return str(value or "").strip().casefold() in {
        "1",
        "true",
        "yes",
        "on",
    }


def positive_float(
    environment: Mapping[str, str],
    name: str,
    default: str,
) -> float:
    """Parse a positive float and identify its environment variable on error."""
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
    """Parse an integer inside an explicit inclusive range."""
    try:
        value = int(environment.get(name, default).strip())
    except ValueError as error:
        raise ValueError(f"{name} must be an integer") from error
    if not minimum <= value <= maximum:
        raise ValueError(
            f"{name} must be between {minimum} and {maximum}"
        )
    return value


def build_local_tool_overrides(
    environment: Mapping[str, str],
) -> Mapping[str, LocalToolOverride]:
    """Build an immutable exact-name mapping from explicit environment.

    Acceptance criteria:
        1. Disabled local mode creates no Neo4j driver.
        2. Remote fallback is rejected rather than ignored.
        3. All configuration is parsed and validated before driver creation.
        4. The mapping exposes only `ReactomeContent_search`.
    """
    if not truthy(environment.get("REACTOME_LOCAL_ENABLED")):
        return MappingProxyType({})
    if truthy(environment.get("REACTOME_REMOTE_FALLBACK")):
        raise ValueError("REACTOME_REMOTE_FALLBACK must remain false")
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
            environment.get("REACTOME_NEO4J_PASSWORD", "") or None
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
