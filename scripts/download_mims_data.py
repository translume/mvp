#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MEDEA_DATA_DIR = ROOT / "data" / "medea_cache" / "MedeaDB"
DEFAULT_OPTIMUSKG_CACHE_DIR = ROOT / "data" / "optimuskg_cache"
DEFAULT_OPTIMUSKG_REPO = ROOT / "third_party" / "upstream" / "OptimusKG"
MEDEADB_REPO_ID = "mims-harvard/MedeaDB"
MEDEADB_MARKER = ".translume_medeadb_complete.json"
OPTIMUSKG_MARKER = ".translume_optimuskg_download.json"

MEDEADB_REQUIRED_FILES = {
    "depmap_24q2": (
        "depmap_24q2/corr_matrix.npy",
        "depmap_24q2/p_val_matrix.npy",
        "depmap_24q2/p_adj_matrix.npy",
        "depmap_24q2/gene_idx_array.npy",
        "depmap_24q2/gene_names.txt",
    ),
    "pinnacle_embeds": (
        "pinnacle_embeds/pinnacle_protein_embed.pth",
        "pinnacle_embeds/pinnacle_mg_embed.pth",
        "pinnacle_embeds/ppi_embed_dict.pth",
        "pinnacle_embeds/pinnacle_labels_dict.txt",
    ),
    "compass_checkpoints": (
        "compass/checkpoint/pretrainer.pt",
        "compass/checkpoint/pft_leave_IMVigor210.pt",
    ),
}

OPTIMUSKG_LCC_FILES = (
    "largest_connected_component_nodes.parquet",
    "largest_connected_component_edges.parquet",
)
OPTIMUSKG_FULL_FILES = ("nodes.parquet", "edges.parquet")


class MimsDataError(RuntimeError):
    """Raised when Harvard MIMS data cannot be downloaded or validated."""


@dataclass(frozen=True)
class MedeaDBInspection:
    """Validation result for a local MedeaDB snapshot."""

    path: str
    available: bool
    resources: dict[str, bool]
    missing: tuple[str, ...]


@dataclass(frozen=True)
class OptimusKGInspection:
    """Validation result for a local OptimusKG client cache."""

    cache_dir: str
    available: bool
    use_lcc: bool
    nodes_path: str | None
    edges_path: str | None
    missing: tuple[str, ...]


_GIT_LFS_POINTER_PREFIX = b"version https://git-lfs.github.com/spec/v1"


def _is_nonempty_file(path: Path) -> bool:
    """Reject missing, empty, and unmaterialized Git LFS pointer files."""
    if not path.is_file() or path.stat().st_size <= 0:
        return False
    try:
        with path.open("rb") as stream:
            return stream.read(len(_GIT_LFS_POINTER_PREFIX)) != _GIT_LFS_POINTER_PREFIX
    except OSError:
        return False


def inspect_medeadb(path: Path) -> MedeaDBInspection:
    """Inspect the MedeaDB resources consumed by upstream Medea tools.

    This checks the concrete resource paths used by Medea's DepMap, PINNACLE,
    TranscriptFormer, and COMPASS tool implementations. It does not load the
    large matrices or model checkpoints.
    """
    root = path.expanduser().resolve()
    resources: dict[str, bool] = {}
    missing: list[str] = []
    for resource, relative_paths in MEDEADB_REQUIRED_FILES.items():
        resource_missing = [
            relative
            for relative in relative_paths
            if not _is_nonempty_file(root / relative)
        ]
        resources[resource] = not resource_missing
        missing.extend(resource_missing)

    embedding_store = root / "transcriptformer_embedding" / "embedding_store"
    transcriptformer_files = (
        tuple(embedding_store.rglob("*.npy")) if embedding_store.is_dir() else ()
    )
    usable_transcriptformer_files = tuple(
        path for path in transcriptformer_files if _is_nonempty_file(path)
    )
    resources["transcriptformer_embeddings"] = bool(usable_transcriptformer_files)
    if not usable_transcriptformer_files:
        missing.append("transcriptformer_embedding/embedding_store/**/*.npy")

    transcriptformer_metadata = (
        tuple(embedding_store.rglob("metadata.json.gz"))
        if embedding_store.is_dir()
        else ()
    )
    usable_transcriptformer_metadata = tuple(
        path for path in transcriptformer_metadata if _is_nonempty_file(path)
    )
    resources["transcriptformer_metadata"] = bool(
        usable_transcriptformer_metadata
    )
    if not usable_transcriptformer_metadata:
        missing.append(
            "transcriptformer_embedding/embedding_store/**/metadata.json.gz"
        )

    return MedeaDBInspection(
        path=str(root),
        available=root.is_dir() and all(resources.values()),
        resources=resources,
        missing=tuple(sorted(missing)),
    )


def download_medeadb(
    destination: Path,
    *,
    force: bool = False,
    revision: str | None = None,
    max_workers: int = 8,
) -> MedeaDBInspection:
    """Download the complete official MedeaDB dataset snapshot."""
    try:
        from huggingface_hub import snapshot_download
    except ImportError as error:
        raise MimsDataError(
            "huggingface-hub is required; run this command through `make medea-data`"
        ) from error

    destination = destination.expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    kwargs: dict[str, Any] = {
        "repo_id": MEDEADB_REPO_ID,
        "repo_type": "dataset",
        "local_dir": destination,
        "force_download": force,
        "max_workers": max_workers,
    }
    if revision:
        kwargs["revision"] = revision
    snapshot_download(**kwargs)

    inspection = inspect_medeadb(destination)
    if not inspection.available:
        raise MimsDataError(
            "MedeaDB download completed without all resources required by Medea: "
            + ", ".join(inspection.missing)
        )
    _write_json(
        destination / MEDEADB_MARKER,
        {
            "repository": MEDEADB_REPO_ID,
            "revision": revision or "latest",
            "validated_at": _utc_now(),
            "inspection": asdict(inspection),
        },
    )
    return inspection


def _optimuskg_file_names(use_lcc: bool) -> tuple[str, str]:
    return OPTIMUSKG_LCC_FILES if use_lcc else OPTIMUSKG_FULL_FILES


def _marker_paths(cache_dir: Path, use_lcc: bool) -> tuple[Path, Path] | None:
    marker = cache_dir / OPTIMUSKG_MARKER
    if not marker.is_file():
        return None
    try:
        payload = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if bool(payload.get("use_lcc")) != use_lcc:
        return None
    raw_paths = payload.get("files")
    if not isinstance(raw_paths, list) or len(raw_paths) != 2:
        return None
    paths = tuple(Path(str(item)).expanduser().resolve() for item in raw_paths)
    if all(_is_nonempty_file(path) for path in paths):
        return paths[0], paths[1]
    return None


def _find_cached_pair(
    cache_dir: Path,
    names: tuple[str, str],
) -> tuple[Path, Path] | None:
    """Find a node/edge pair from the same DOI/version cache directory."""
    pairs: list[tuple[Path, Path]] = []
    for nodes_path in cache_dir.rglob(names[0]):
        edges_path = nodes_path.parent / names[1]
        if _is_nonempty_file(nodes_path) and _is_nonempty_file(edges_path):
            pairs.append((nodes_path, edges_path))
    if not pairs:
        return None
    return max(
        pairs,
        key=lambda pair: max(
            pair[0].stat().st_mtime_ns,
            pair[1].stat().st_mtime_ns,
        ),
    )


def inspect_optimuskg_cache(
    cache_dir: Path,
    *,
    use_lcc: bool = True,
) -> OptimusKGInspection:
    """Locate the exact OptimusKG parquet pair consumed by Translume."""
    cache_dir = cache_dir.expanduser().resolve()
    names = _optimuskg_file_names(use_lcc)
    marked = _marker_paths(cache_dir, use_lcc)
    if marked is not None:
        nodes_path, edges_path = marked
    else:
        cached_pair = _find_cached_pair(cache_dir, names)
        nodes_path, edges_path = (
            cached_pair if cached_pair is not None else (None, None)
        )
    missing = tuple(
        name
        for name, path in zip(names, (nodes_path, edges_path), strict=True)
        if path is None
    )
    return OptimusKGInspection(
        cache_dir=str(cache_dir),
        available=not missing,
        use_lcc=use_lcc,
        nodes_path=str(nodes_path) if nodes_path else None,
        edges_path=str(edges_path) if edges_path else None,
        missing=missing,
    )


def _add_optimuskg_repo_paths(repo_path: Path) -> None:
    if not repo_path.is_dir() or not any(repo_path.iterdir()):
        raise MimsDataError(
            f"OptimusKG repository is missing or empty: {repo_path}. "
            "Run `make vendor-repos` first."
        )
    candidates = (
        repo_path,
        repo_path / "src",
        repo_path / "packages" / "optimuskg" / "src",
    )
    for candidate in candidates:
        if candidate.is_dir() and str(candidate) not in sys.path:
            sys.path.insert(0, str(candidate))


def validate_optimuskg_parquet(nodes_path: Path, edges_path: Path) -> None:
    """Validate the node/edge columns consumed by the Translume adapter."""
    try:
        import polars as pl
    except ImportError as error:
        raise MimsDataError(
            "polars is required; run this command through `make optimuskg-data`"
        ) from error

    try:
        node_columns = set(pl.scan_parquet(nodes_path).collect_schema().names())
        edge_columns = set(pl.scan_parquet(edges_path).collect_schema().names())
    except Exception as error:
        raise MimsDataError(
            "OptimusKG parquet files could not be opened by Polars: "
            f"nodes={nodes_path}, edges={edges_path}: {error}"
        ) from error
    missing_nodes = sorted({"id", "label", "properties"} - node_columns)
    missing_edges = sorted({"from", "to", "label"} - edge_columns)
    if missing_nodes or missing_edges:
        details = []
        if missing_nodes:
            details.append("nodes=" + ",".join(missing_nodes))
        if missing_edges:
            details.append("edges=" + ",".join(missing_edges))
        raise MimsDataError(
            "OptimusKG parquet schema is incompatible with Translume: "
            + "; ".join(details)
        )


def download_optimuskg(
    repo_path: Path,
    cache_dir: Path,
    *,
    use_lcc: bool = True,
    force: bool = False,
) -> OptimusKGInspection:
    """Download OptimusKG through its official Python client cache API."""
    repo_path = repo_path.expanduser().resolve()
    cache_dir = cache_dir.expanduser().resolve()
    cache_dir.mkdir(parents=True, exist_ok=True)
    _add_optimuskg_repo_paths(repo_path)
    try:
        optimuskg = importlib.import_module("optimuskg")
    except ImportError as error:
        raise MimsDataError(
            f"could not import the OptimusKG client from {repo_path}: {error}"
        ) from error
    if not hasattr(optimuskg, "get_file") or not hasattr(optimuskg, "set_cache_dir"):
        raise MimsDataError(
            "the vendored OptimusKG client must expose get_file and set_cache_dir"
        )

    optimuskg.set_cache_dir(cache_dir)
    nodes_name, edges_name = _optimuskg_file_names(use_lcc)
    try:
        nodes_path = Path(optimuskg.get_file(nodes_name, force=force)).resolve()
        edges_path = Path(optimuskg.get_file(edges_name, force=force)).resolve()
    except Exception as error:
        raise MimsDataError(
            "OptimusKG client download failed for "
            f"{nodes_name} and {edges_name}: {error}"
        ) from error
    if not _is_nonempty_file(nodes_path) or not _is_nonempty_file(edges_path):
        raise MimsDataError(
            "OptimusKG client returned missing or empty parquet files: "
            f"{nodes_path}, {edges_path}"
        )
    validate_optimuskg_parquet(nodes_path, edges_path)
    _write_json(
        cache_dir / OPTIMUSKG_MARKER,
        {
            "downloaded_at": _utc_now(),
            "use_lcc": use_lcc,
            "doi": os.getenv("OPTIMUSKG_DOI", "upstream-default"),
            "files": [str(nodes_path), str(edges_path)],
        },
    )
    return inspect_optimuskg_cache(cache_dir, use_lcc=use_lcc)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _json_result(kind: str, inspection: object) -> str:
    return json.dumps(
        {"status": "ok", "dataset": kind, "inspection": asdict(inspection)},
        indent=2,
        sort_keys=True,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Download and validate Harvard MIMS datasets used by Translume."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    medea = subparsers.add_parser(
        "medea", help="download the complete MedeaDB snapshot"
    )
    medea.add_argument("--destination", type=Path, default=DEFAULT_MEDEA_DATA_DIR)
    medea.add_argument("--revision")
    medea.add_argument("--max-workers", type=int, default=8)
    medea.add_argument("--force", action="store_true")

    optimus = subparsers.add_parser(
        "optimuskg", help="download the graph parquet pair through the OptimusKG client"
    )
    optimus.add_argument("--repo", type=Path, default=DEFAULT_OPTIMUSKG_REPO)
    optimus.add_argument("--cache-dir", type=Path, default=DEFAULT_OPTIMUSKG_CACHE_DIR)
    optimus.add_argument(
        "--use-lcc",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="download the largest-connected-component pair (default: true)",
    )
    optimus.add_argument("--force", action="store_true")

    status = subparsers.add_parser(
        "status", help="inspect local MIMS data without downloading"
    )
    status.add_argument("--medeadb", type=Path, default=DEFAULT_MEDEA_DATA_DIR)
    status.add_argument(
        "--optimuskg-cache", type=Path, default=DEFAULT_OPTIMUSKG_CACHE_DIR
    )
    status.add_argument(
        "--use-lcc",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    try:
        if args.command == "medea":
            if args.max_workers <= 0:
                raise MimsDataError("--max-workers must be positive")
            inspection = download_medeadb(
                args.destination,
                force=args.force,
                revision=args.revision,
                max_workers=args.max_workers,
            )
            print(_json_result("medea", inspection))
            return 0
        if args.command == "optimuskg":
            inspection = download_optimuskg(
                args.repo,
                args.cache_dir,
                use_lcc=args.use_lcc,
                force=args.force,
            )
            print(_json_result("optimuskg", inspection))
            return 0
        medea = inspect_medeadb(args.medeadb)
        optimus = inspect_optimuskg_cache(
            args.optimuskg_cache,
            use_lcc=args.use_lcc,
        )
        if optimus.available and optimus.nodes_path and optimus.edges_path:
            validate_optimuskg_parquet(
                Path(optimus.nodes_path),
                Path(optimus.edges_path),
            )
        payload = {
            "status": "ok" if medea.available and optimus.available else "incomplete",
            "medea": asdict(medea),
            "optimuskg": asdict(optimus),
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0 if payload["status"] == "ok" else 1
    except (MimsDataError, OSError, ValueError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
