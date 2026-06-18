from __future__ import annotations

import json
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from translume_schemas.entities import NormalizedEntitySet
from translume_schemas.graph import GraphEdge, GraphEvidenceArtifact, GraphNode


class OptimusKGRuntimeError(RuntimeError):
    """Raised when the real OptimusKG runtime cannot provide graph context."""


@dataclass(frozen=True)
class OptimusKGGraphConfig:
    """Runtime configuration for real OptimusKG graph retrieval.

    Attributes:
        repo_path: Real git checkout containing the OptimusKG Python package.
        cache_dir: Optional OptimusKG cache directory used by the upstream client.
        use_lcc: Whether to use OptimusKG largest-connected-component parquet files.
        force_download: Whether to force the upstream client to refresh parquet files.
        max_edges: Maximum graph edges returned for one report request.
    """

    repo_path: Path
    cache_dir: Path | None = None
    use_lcc: bool = True
    force_download: bool = False
    max_edges: int = 500


def retrieve_optimuskg_graph_context(
    entities: NormalizedEntitySet,
    config: OptimusKGGraphConfig,
) -> GraphEvidenceArtifact:
    """Retrieve graph evidence through OptimusKG's real parquet client path.

    Acceptance criteria:
        1. Imports the real OptimusKG Python package from a real vendor repo.
        2. Uses OptimusKG get_file/load-graph parquet paths, not generic edge files.
        3. Loads nodes and edges with Polars from OptimusKG parquet tables.
        4. Returns nodes/edges only when they derive from those parquet tables.
        5. Fails loudly when OptimusKG, Polars, or parquet graph data is missing.
        6. Records missing entity context without converting absence into claims.
    """
    if config.max_edges <= 0:
        raise OptimusKGRuntimeError("OPTIMUSKG_MAX_EDGES must be positive")
    optimuskg = _import_optimuskg(config.repo_path)
    _configure_cache(optimuskg, config.cache_dir)
    nodes_path, edges_path = _optimuskg_parquet_paths(
        optimuskg=optimuskg,
        use_lcc=config.use_lcc,
        force_download=config.force_download,
    )
    return _graph_artifact_from_parquet(
        entities=entities,
        nodes_path=nodes_path,
        edges_path=edges_path,
        config=config,
    )


def _import_optimuskg(repo_path: Path) -> Any:
    """Import the real OptimusKG package from an upstream checkout.

    The current OptimusKG client package lives under
    ``packages/optimuskg/src`` in the repository. Older or installed layouts may
    expose either the repository root or ``src``. All supported paths are added
    explicitly and no synthetic module is created.
    """
    if not repo_path.exists() or not repo_path.is_dir():
        raise OptimusKGRuntimeError(f"OptimusKG repository is missing: {repo_path}")
    if not any(repo_path.iterdir()):
        raise OptimusKGRuntimeError(f"OptimusKG repository is empty: {repo_path}")
    candidate_paths = (
        repo_path,
        repo_path / "src",
        repo_path / "packages" / "optimuskg" / "src",
    )
    for candidate in candidate_paths:
        if candidate.exists():
            value = str(candidate)
            if value not in sys.path:
                sys.path.insert(0, value)
    try:
        import optimuskg  # type: ignore[import-not-found]
    except ImportError as error:
        raise OptimusKGRuntimeError(
            "could not import real OptimusKG package from "
            f"{repo_path}; expected package path packages/optimuskg/src"
        ) from error
    required = ("get_file",)
    missing = [name for name in required if not hasattr(optimuskg, name)]
    if missing:
        raise OptimusKGRuntimeError(
            "imported OptimusKG package is missing required client API: "
            + ", ".join(missing)
        )
    return optimuskg


def _configure_cache(optimuskg: Any, cache_dir: Path | None) -> None:
    """Configure upstream OptimusKG cache if the client supports it."""
    if cache_dir is None:
        return
    cache_dir.mkdir(parents=True, exist_ok=True)
    if hasattr(optimuskg, "set_cache_dir"):
        optimuskg.set_cache_dir(cache_dir)


def _optimuskg_parquet_paths(
    *,
    optimuskg: Any,
    use_lcc: bool,
    force_download: bool,
) -> tuple[Path, Path]:
    """Return OptimusKG node and edge parquet paths through its client API."""
    nodes_rel, edges_rel = (
        ("largest_connected_component_nodes.parquet", "largest_connected_component_edges.parquet")
        if use_lcc
        else ("nodes.parquet", "edges.parquet")
    )
    try:
        nodes_path = Path(optimuskg.get_file(nodes_rel, force=force_download))
        edges_path = Path(optimuskg.get_file(edges_rel, force=force_download))
    except Exception as error:  # upstream client may raise dataverse/cache errors
        raise OptimusKGRuntimeError(
            "OptimusKG parquet files are unavailable through the real client API: "
            f"nodes={nodes_rel}, edges={edges_rel}. Configure OPTIMUSKG_CACHE_DIR "
            "with cached files or allow the client to download them."
        ) from error
    missing = [str(path) for path in (nodes_path, edges_path) if not path.exists()]
    if missing:
        raise OptimusKGRuntimeError(
            "OptimusKG client returned missing parquet paths: " + ", ".join(missing)
        )
    return nodes_path, edges_path


def _graph_artifact_from_parquet(
    *,
    entities: NormalizedEntitySet,
    nodes_path: Path,
    edges_path: Path,
    config: OptimusKGGraphConfig,
) -> GraphEvidenceArtifact:
    """Build graph evidence from OptimusKG node/edge parquet tables."""
    pl = _require_polars()
    nodes_df = pl.scan_parquet(nodes_path).collect()
    _require_columns(nodes_df.columns, {"id", "label", "properties"}, "nodes parquet")
    labels = _entity_lookup_labels(entities)
    matched_node_ids = _matched_node_ids(nodes_df, labels)
    if not matched_node_ids:
        return GraphEvidenceArtifact(
            artifact_id=_artifact_id(entities.artifact_id),
            source_entity_ids=[entity.entity_id for entity in entities.entities],
            nodes=[],
            edges=[],
            missing_entities=[entity.entity_id for entity in entities.entities],
            warnings=["no_optimuskg_nodes_matched_normalized_entities"],
        )
    edges_df = _collect_matching_edges(
        edges_path=edges_path,
        matched_node_ids=matched_node_ids,
        max_edges=config.max_edges,
    )
    if edges_df.height == 0:
        return GraphEvidenceArtifact(
            artifact_id=_artifact_id(entities.artifact_id),
            source_entity_ids=[entity.entity_id for entity in entities.entities],
            nodes=_graph_nodes_from_node_ids(
                nodes_df,
                matched_node_ids,
                nodes_path,
                edges_path,
                config,
            ),
            edges=[],
            missing_entities=_missing_entity_ids(entities, nodes_df, matched_node_ids),
            warnings=["no_optimuskg_edges_matched_normalized_entities"],
        )
    endpoint_ids = _edge_endpoint_ids(edges_df)
    nodes = _graph_nodes_from_node_ids(
        nodes_df,
        endpoint_ids | matched_node_ids,
        nodes_path,
        edges_path,
        config,
    )
    node_ids = {node.node_id for node in nodes}
    edges = _graph_edges_from_df(edges_df, node_ids, nodes_path, edges_path, config)
    return GraphEvidenceArtifact(
        artifact_id=_artifact_id(entities.artifact_id),
        source_entity_ids=[entity.entity_id for entity in entities.entities],
        nodes=nodes,
        edges=edges,
        missing_entities=_missing_entity_ids(entities, nodes_df, matched_node_ids),
        warnings=[] if edges else ["no_optimuskg_edges_after_node_matching"],
    )


def _require_polars() -> Any:
    try:
        import polars as pl  # type: ignore[import-not-found]
    except ImportError as error:
        raise OptimusKGRuntimeError(
            "Polars is required for real OptimusKG parquet graph loading"
        ) from error
    return pl


def _require_columns(columns: Sequence[str], required: set[str], label: str) -> None:
    missing = sorted(required - set(columns))
    if missing:
        raise OptimusKGRuntimeError(
            f"{label} is missing required OptimusKG columns: {', '.join(missing)}"
        )


def _entity_lookup_labels(entities: NormalizedEntitySet) -> set[str]:
    labels: set[str] = set()
    for entity in entities.entities:
        for value in (entity.normalized_label, entity.original_text):
            cleaned = _casefold(value)
            if cleaned:
                labels.add(cleaned)
    return labels


def _matched_node_ids(nodes_df: Any, labels: set[str]) -> set[str]:
    matched: set[str] = set()
    for row in nodes_df.iter_rows(named=True):
        aliases = _node_aliases(row)
        if aliases & labels:
            matched.add(str(row["id"]))
    return matched


def _node_aliases(row: dict[str, Any]) -> set[str]:
    aliases = {_casefold(row.get("id")), _casefold(row.get("label"))}
    properties = _parse_properties(row.get("properties"))
    for key in ("name", "symbol", "identifier", "description"):
        value = properties.get(key)
        if isinstance(value, str):
            aliases.add(_casefold(value))
    for key in ("synonyms", "aliases", "xrefs", "equivalent_identifiers"):
        value = properties.get(key)
        aliases |= _casefold_many(value)
    return {alias for alias in aliases if alias}


def _parse_properties(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _casefold(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().casefold()


def _casefold_many(value: Any) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, str):
        return {_casefold(value)}
    if isinstance(value, Iterable):
        return {_casefold(item) for item in value if _casefold(item)}
    return {_casefold(value)}


def _collect_matching_edges(edges_path: Path, matched_node_ids: set[str], max_edges: int) -> Any:
    pl = _require_polars()
    edge_scan = pl.scan_parquet(edges_path)
    columns = edge_scan.collect_schema().names()
    _require_columns(columns, {"from", "to", "label"}, "edges parquet")
    return (
        edge_scan.filter(
            pl.col("from").is_in(list(matched_node_ids))
            | pl.col("to").is_in(list(matched_node_ids))
        )
        .limit(max_edges)
        .collect()
    )


def _edge_endpoint_ids(edges_df: Any) -> set[str]:
    endpoint_ids: set[str] = set()
    for row in edges_df.iter_rows(named=True):
        endpoint_ids.add(str(row["from"]))
        endpoint_ids.add(str(row["to"]))
    return endpoint_ids


def _graph_nodes_from_node_ids(
    nodes_df: Any,
    node_ids: set[str],
    nodes_path: Path,
    edges_path: Path,
    config: OptimusKGGraphConfig,
) -> list[GraphNode]:
    rows = [row for row in nodes_df.iter_rows(named=True) if str(row["id"]) in node_ids]
    nodes: list[GraphNode] = []
    for row in sorted(rows, key=lambda item: str(item["id"])):
        raw_id = str(row["id"])
        properties = _parse_properties(row.get("properties"))
        label = _display_label(raw_id, properties)
        nodes.append(
            GraphNode(
                node_id=_node_id(raw_id),
                label=label,
                kind=str(row.get("label") or "entity"),
                source="optimuskg_parquet",
                provenance=_provenance(nodes_path, edges_path, config),
            )
        )
    return nodes


def _display_label(raw_id: str, properties: dict[str, Any]) -> str:
    name = properties.get("name")
    if isinstance(name, str) and name.strip():
        return name.strip()
    symbol = properties.get("symbol")
    if isinstance(symbol, str) and symbol.strip():
        return symbol.strip()
    return raw_id


def _graph_edges_from_df(
    edges_df: Any,
    node_ids: set[str],
    nodes_path: Path,
    edges_path: Path,
    config: OptimusKGGraphConfig,
) -> list[GraphEdge]:
    edges: list[GraphEdge] = []
    for row in edges_df.iter_rows(named=True):
        source_id = _node_id(str(row["from"]))
        target_id = _node_id(str(row["to"]))
        if source_id not in node_ids or target_id not in node_ids:
            continue
        relation_type = str(row.get("label") or row.get("relation") or "related_to")
        seed = f"{row['from']}:{relation_type}:{row['to']}:{row.get('relation', '')}"
        edges.append(
            GraphEdge(
                edge_id=f"edge_{uuid5(NAMESPACE_URL, seed).hex[:16]}",
                source_node_id=source_id,
                target_node_id=target_id,
                relation_type=relation_type,
                source="optimuskg_parquet",
                provenance=_provenance(nodes_path, edges_path, config),
            )
        )
    return edges


def _missing_entity_ids(
    entities: NormalizedEntitySet,
    nodes_df: Any,
    matched_node_ids: set[str],
) -> list[str]:
    matched_labels: set[str] = set()
    for row in nodes_df.iter_rows(named=True):
        if str(row["id"]) in matched_node_ids:
            matched_labels |= _node_aliases(row)
    missing: list[str] = []
    for entity in entities.entities:
        entity_aliases = {_casefold(entity.normalized_label), _casefold(entity.original_text)}
        if not (entity_aliases & matched_labels):
            missing.append(entity.entity_id)
    return missing


def _node_id(raw_id: str) -> str:
    return f"node_{uuid5(NAMESPACE_URL, raw_id).hex[:16]}"


def _artifact_id(entity_artifact_id: str) -> str:
    return f"artifact_{uuid5(NAMESPACE_URL, entity_artifact_id + ':optimuskg_parquet').hex[:16]}"


def _provenance(
    nodes_path: Path,
    edges_path: Path,
    config: OptimusKGGraphConfig,
) -> dict[str, str]:
    return {
        "provider": "optimuskg",
        "runtime": "optimuskg_python_client_get_file_polars_parquet",
        "vendor_repo": str(config.repo_path),
        "nodes_file": str(nodes_path),
        "edges_file": str(edges_path),
        "use_lcc": str(config.use_lcc).lower(),
    }
