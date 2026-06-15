from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from optimuskg_service.vendor_runtime import VendorRuntimeError, import_vendor_module
from translume_schemas.entities import NormalizedEntitySet
from translume_schemas.graph import GraphEdge, GraphEvidenceArtifact, GraphNode

app = FastAPI(title="optimuskg_service")


class ContextRequest(BaseModel):
    entities: dict[str, object]


@app.get("/health")
def health() -> dict[str, object]:
    """Return service health and vendored OptimusKG availability."""
    repo_path = _repo_path()
    try:
        import_vendor_module(repo_path, _module_names())
        vendor_available = True
        error = None
    except VendorRuntimeError as runtime_error:
        vendor_available = False
        error = str(runtime_error)
    return {
        "status": "ok",
        "service": "optimuskg_service",
        "vendor_path": str(repo_path),
        "vendor_available": vendor_available,
        "error": error,
    }


@app.post("/context")
async def context(request: ContextRequest) -> dict[str, object]:
    """Retrieve graph evidence from vendored OptimusKG-backed data.

    Acceptance criteria:
        1. Requires a real vendored OptimusKG repository import.
        2. Requires real graph edge data from configured or discovered files.
        3. Does not fabricate graph nodes, edges, or source relations.
        4. Missing graph data returns explicit HTTP errors.
        5. Missing entity matches are recorded as missing evidence, not claims.
    """
    try:
        entities = NormalizedEntitySet.model_validate(request.entities)
        import_vendor_module(_repo_path(), _module_names())
        rows = _load_edge_rows(_edge_table_path(), _search_roots())
        artifact = _graph_artifact_from_rows(entities, rows)
    except (ValueError, VendorRuntimeError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return artifact.model_dump(mode="json")


def _repo_path() -> Path:
    return Path(os.getenv("OPTIMUSKG_VENDOR_DIR", "/app/third_party/upstream/OptimusKG"))


def _module_names() -> tuple[str, ...]:
    raw = os.getenv("OPTIMUSKG_MODULE_NAMES", "optimuskg,OptimusKG")
    return tuple(item.strip() for item in raw.split(",") if item.strip())


def _edge_table_path() -> Path | None:
    raw = os.getenv("OPTIMUSKG_EDGE_TABLE_PATH", "").strip()
    return Path(raw) if raw else None


def _search_roots() -> list[Path]:
    roots = [_repo_path()]
    cache = os.getenv("OPTIMUSKG_CACHE_DIR", "").strip()
    if cache:
        roots.append(Path(cache))
    return roots


def _load_edge_rows(
    configured_path: Path | None,
    search_roots: list[Path],
) -> list[dict[str, str]]:
    """Load edge rows from real configured or discovered graph data.

    Acceptance criteria:
        1. Reads configured edge table when provided.
        2. Otherwise discovers supported edge-like files under search roots.
        3. Requires subject, relation, and object fields after alias mapping.
        4. Raises when no real edge table is available.
    """
    candidates = [configured_path] if configured_path is not None else _discover_edge_files(search_roots)
    attempted: list[str] = []
    for candidate in candidates:
        if candidate is None:
            continue
        attempted.append(str(candidate))
        if not candidate.exists():
            continue
        rows = _read_edge_file(candidate)
        if rows:
            return rows
    raise VendorRuntimeError(
        "no usable OptimusKG edge data found; attempted=" + ", ".join(attempted)
    )


def _discover_edge_files(search_roots: list[Path]) -> list[Path]:
    suffixes = {".csv", ".jsonl", ".json"}
    files: list[Path] = []
    for root in search_roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file() and path.suffix.lower() in suffixes and _looks_edge_like(path):
                files.append(path)
    return sorted(files, key=lambda item: (len(item.parts), str(item)))


def _looks_edge_like(path: Path) -> bool:
    name = path.name.casefold()
    return any(token in name for token in ("edge", "edges", "relation", "relations"))


def _read_edge_file(path: Path) -> list[dict[str, str]]:
    if path.suffix.lower() == ".csv":
        return _read_edge_csv(path)
    if path.suffix.lower() == ".jsonl":
        return [_normalize_edge_row(json.loads(line)) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if path.suffix.lower() == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows = payload.get("edges") if isinstance(payload, dict) else payload
        if not isinstance(rows, list):
            raise VendorRuntimeError(f"edge JSON must contain a list: {path}")
        return [_normalize_edge_row(row) for row in rows]
    raise VendorRuntimeError(f"unsupported OptimusKG edge file type: {path}")


def _read_edge_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return [_normalize_edge_row(row) for row in reader]


def _normalize_edge_row(row: Any) -> dict[str, str]:
    if not isinstance(row, dict):
        raise VendorRuntimeError("edge row must be an object")
    normalized = {str(key).strip().casefold(): "" if value is None else str(value) for key, value in row.items()}
    subject = _first_value(normalized, ("subject", "source", "source_label", "head", "node1", "from"))
    relation = _first_value(normalized, ("relation_type", "relation", "predicate", "edge_type", "type"))
    obj = _first_value(normalized, ("object", "target", "target_label", "tail", "node2", "to"))
    if not subject or not relation or not obj:
        raise VendorRuntimeError("edge row missing subject/relation/object fields")
    return {
        "subject": subject,
        "relation_type": relation,
        "object": obj,
        "subject_kind": _first_value(normalized, ("subject_kind", "source_kind", "source_type")) or "entity",
        "object_kind": _first_value(normalized, ("object_kind", "target_kind", "target_type")) or "entity",
        "source": _first_value(normalized, ("source", "provenance", "data_source")) or "optimuskg",
    }


def _first_value(row: dict[str, str], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = row.get(key, "").strip()
        if value:
            return value
    return ""


def _graph_artifact_from_rows(
    entities: NormalizedEntitySet,
    rows: list[dict[str, str]],
) -> GraphEvidenceArtifact:
    labels = {entity.normalized_label.casefold(): entity.entity_id for entity in entities.entities}
    nodes: dict[str, GraphNode] = {}
    edges: list[GraphEdge] = []
    matched_entities: set[str] = set()
    for row in rows:
        subject = row["subject"]
        obj = row["object"]
        if subject.casefold() not in labels and obj.casefold() not in labels:
            continue
        subject_id = _node_id(subject)
        object_id = _node_id(obj)
        nodes.setdefault(
            subject_id,
            GraphNode(
                node_id=subject_id,
                label=subject,
                kind=row["subject_kind"],
                source="optimuskg_vendor",
                provenance={"vendor_repo": str(_repo_path())},
            ),
        )
        nodes.setdefault(
            object_id,
            GraphNode(
                node_id=object_id,
                label=obj,
                kind=row["object_kind"],
                source="optimuskg_vendor",
                provenance={"vendor_repo": str(_repo_path())},
            ),
        )
        if subject.casefold() in labels:
            matched_entities.add(labels[subject.casefold()])
        if obj.casefold() in labels:
            matched_entities.add(labels[obj.casefold()])
        edge_seed = f"{subject}:{row['relation_type']}:{obj}:{row['source']}"
        edges.append(
            GraphEdge(
                edge_id=f"edge_{uuid5(NAMESPACE_URL, edge_seed).hex[:16]}",
                source_node_id=subject_id,
                target_node_id=object_id,
                relation_type=row["relation_type"],
                source=row["source"],
                provenance={"vendor_repo": str(_repo_path())},
            )
        )
    missing = [entity.entity_id for entity in entities.entities if entity.entity_id not in matched_entities]
    artifact_id = f"artifact_{uuid5(NAMESPACE_URL, entities.artifact_id + ':optimuskg_service').hex[:16]}"
    return GraphEvidenceArtifact(
        artifact_id=artifact_id,
        source_entity_ids=[entity.entity_id for entity in entities.entities],
        nodes=list(nodes.values()),
        edges=edges,
        missing_entities=missing,
        warnings=[] if edges else ["no_optimuskg_edges_matched_normalized_entities"],
    )


def _node_id(label: str) -> str:
    return f"node_{uuid5(NAMESPACE_URL, label.casefold()).hex[:16]}"
