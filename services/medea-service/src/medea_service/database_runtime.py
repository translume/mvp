from __future__ import annotations

import importlib
import os
from dataclasses import dataclass
from itertools import combinations, islice
from pathlib import Path
from typing import Any, Mapping

from translume_schemas.evidence import EvidenceContextBundle

DEFAULT_MEDEADB_PATH = Path("/app/data/medea_cache/MedeaDB")

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


class MedeaDatabaseError(RuntimeError):
    """Raised when MedeaDB is required but unavailable or unreadable."""


@dataclass(frozen=True)
class MedeaDBStatus:
    """Availability of the resource families in the full MedeaDB snapshot."""

    path: Path
    available: bool
    resources: dict[str, bool]
    missing: tuple[str, ...]

    @property
    def depmap_available(self) -> bool:
        return self.resources.get("depmap_24q2", False)

    def as_dict(self) -> dict[str, object]:
        return {
            "path": str(self.path),
            "available": self.available,
            "resources": dict(self.resources),
            "missing": list(self.missing),
        }


@dataclass(frozen=True)
class DepMapPairEvidence:
    """One report-gene pair parsed from MedeaDB DepMap matrices."""

    gene_a: str
    gene_b: str
    correlation: float
    p_value: float
    adjusted_p_value: float | None


@dataclass(frozen=True)
class DepMapNeighborEvidence:
    """One exploratory DepMap neighbor for a single report gene."""

    query_gene: str
    gene: str
    correlation: float
    p_value: float


@dataclass(frozen=True)
class MedeaDBEvidence:
    """Bounded MedeaDB evidence added to the literature-reasoning query."""

    queried_genes: tuple[str, ...]
    pairwise: tuple[DepMapPairEvidence, ...]
    neighbors: tuple[DepMapNeighborEvidence, ...]
    missing_genes: tuple[str, ...]

    @property
    def has_data(self) -> bool:
        return bool(self.pairwise or self.neighbors)


@dataclass(frozen=True)
class MedeaDBRuntimeValidation:
    """Result of opening Medea's real DepMap parser over local data."""

    gene_count: int
    storage_format: str


def medeadb_path(environment: Mapping[str, str] | None = None) -> Path:
    """Resolve the exact root passed to upstream Medea as ``MEDEADB_PATH``."""
    env = environment or os.environ
    raw = env.get("MEDEADB_PATH", "").strip()
    return Path(raw).expanduser().resolve() if raw else DEFAULT_MEDEADB_PATH


def database_required(environment: Mapping[str, str] | None = None) -> bool:
    """Return whether service requests must use a complete MedeaDB snapshot."""
    env = environment or os.environ
    return env.get("MEDEA_REQUIRE_DATABASE", "true").strip().casefold() in {
        "1",
        "true",
        "yes",
        "on",
    }


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


def inspect_medeadb(path: Path | None = None) -> MedeaDBStatus:
    """Inspect the concrete files consumed by Medea's database-backed tools."""
    root = (path or medeadb_path()).expanduser().resolve()
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
    embeddings = (
        tuple(embedding_store.rglob("*.npy")) if embedding_store.is_dir() else ()
    )
    usable_embeddings = tuple(path for path in embeddings if _is_nonempty_file(path))
    resources["transcriptformer_embeddings"] = bool(usable_embeddings)
    if not usable_embeddings:
        missing.append("transcriptformer_embedding/embedding_store/**/*.npy")

    metadata_files = (
        tuple(embedding_store.rglob("metadata.json.gz"))
        if embedding_store.is_dir()
        else ()
    )
    usable_metadata = tuple(
        path for path in metadata_files if _is_nonempty_file(path)
    )
    resources["transcriptformer_metadata"] = bool(usable_metadata)
    if not usable_metadata:
        missing.append(
            "transcriptformer_embedding/embedding_store/**/metadata.json.gz"
        )

    return MedeaDBStatus(
        path=root,
        available=root.is_dir() and all(resources.values()),
        resources=resources,
        missing=tuple(sorted(missing)),
    )


def require_medeadb(status: MedeaDBStatus) -> None:
    """Fail with an actionable message when the full snapshot is unavailable."""
    if status.available:
        return
    details = (
        ", ".join(status.missing) if status.missing else "database directory missing"
    )
    raise MedeaDatabaseError(
        f"MedeaDB is required at {status.path}, but it is incomplete: {details}. "
        "Run `make medea-data` on the host and restart medea-service."
    )


def _import_depmap_module(medea_module: Any) -> Any:
    package_name = str(getattr(medea_module, "__name__", "medea")).split(".", 1)[0]
    module_name = f"{package_name}.tool_space.depmap"
    try:
        module = importlib.import_module(module_name)
    except ImportError as error:
        raise MedeaDatabaseError(
            f"could not import Medea DepMap parser {module_name}: {error}"
        ) from error
    if not hasattr(module, "GeneCorrelationLookup"):
        raise MedeaDatabaseError(
            f"Medea DepMap parser {module_name} lacks GeneCorrelationLookup"
        )
    return module


def _open_depmap_lookup(medea_module: Any, status: MedeaDBStatus) -> Any:
    if not status.depmap_available:
        raise MedeaDatabaseError(
            f"MedeaDB DepMap files are unavailable under {status.path / 'depmap_24q2'}"
        )
    depmap_module = _import_depmap_module(medea_module)
    try:
        return depmap_module.GeneCorrelationLookup(str(status.path / "depmap_24q2"))
    except Exception as error:
        raise MedeaDatabaseError(
            f"Medea could not parse DepMap data under {status.path}: {error}"
        ) from error


def _close_lookup(lookup: Any) -> None:
    h5_file = getattr(lookup, "h5_file", None)
    if h5_file is not None and hasattr(h5_file, "close"):
        h5_file.close()


def validate_medeadb_runtime(
    medea_module: Any,
    status: MedeaDBStatus,
) -> MedeaDBRuntimeValidation:
    """Open the real upstream parser without loading matrices into RAM."""
    require_medeadb(status)
    lookup = _open_depmap_lookup(medea_module, status)
    try:
        gene_count = int(getattr(lookup, "num_genes", 0))
        storage_format = str(getattr(lookup, "format", "unknown"))
        if gene_count <= 0:
            raise MedeaDatabaseError("Medea DepMap parser reported zero genes")
        if storage_format not in {"dense", "sparse"}:
            raise MedeaDatabaseError(
                f"Medea DepMap parser reported unsupported format: {storage_format}"
            )
        return MedeaDBRuntimeValidation(
            gene_count=gene_count,
            storage_format=storage_format,
        )
    finally:
        _close_lookup(lookup)


def context_genes(context: EvidenceContextBundle) -> tuple[str, ...]:
    """Return unique report gene symbols in deterministic input order."""
    genes: list[str] = []
    seen: set[str] = set()
    for finding in context.extraction.molecular_findings:
        gene = (finding.gene or "").strip().upper()
        if gene and gene not in seen:
            seen.add(gene)
            genes.append(gene)
    return tuple(genes)


def collect_medeadb_evidence(
    medea_module: Any,
    context: EvidenceContextBundle,
    status: MedeaDBStatus,
    *,
    max_pairs: int = 10,
    neighbors_per_single_gene: int = 3,
) -> MedeaDBEvidence:
    """Parse bounded DepMap evidence for report genes through upstream Medea."""
    if max_pairs <= 0:
        raise MedeaDatabaseError("MEDEA_DB_MAX_GENE_PAIRS must be positive")
    if neighbors_per_single_gene < 0:
        raise MedeaDatabaseError(
            "MEDEA_DB_SIMILAR_GENES_PER_SINGLE_GENE cannot be negative"
        )
    genes = context_genes(context)
    if not genes:
        return MedeaDBEvidence((), (), (), ())

    lookup = _open_depmap_lookup(medea_module, status)
    try:
        available = tuple(gene for gene in genes if gene in lookup.gene_to_idx)
        missing = tuple(gene for gene in genes if gene not in lookup.gene_to_idx)
        pairwise: list[DepMapPairEvidence] = []
        for gene_a, gene_b in islice(combinations(available, 2), max_pairs):
            result = lookup.get_correlation(gene_a, gene_b)
            pairwise.append(
                DepMapPairEvidence(
                    gene_a=gene_a,
                    gene_b=gene_b,
                    correlation=float(result["correlation"]),
                    p_value=float(result["p_value"]),
                    adjusted_p_value=(
                        float(result["adjusted_p_value"])
                        if result.get("adjusted_p_value") is not None
                        else None
                    ),
                )
            )

        neighbors: list[DepMapNeighborEvidence] = []
        if len(available) == 1 and neighbors_per_single_gene:
            query_gene = available[0]
            raw_neighbors = lookup.find_similar_genes(
                query_gene,
                top_n=neighbors_per_single_gene,
                min_correlation=0.5,
                max_p_value=0.05,
            )
            for item in raw_neighbors:
                neighbors.append(
                    DepMapNeighborEvidence(
                        query_gene=query_gene,
                        gene=str(item["gene"]),
                        correlation=float(item["correlation"]),
                        p_value=float(item["p_value"]),
                    )
                )
        return MedeaDBEvidence(
            queried_genes=genes,
            pairwise=tuple(pairwise),
            neighbors=tuple(neighbors),
            missing_genes=missing,
        )
    except MedeaDatabaseError:
        raise
    except Exception as error:
        raise MedeaDatabaseError(f"MedeaDB DepMap lookup failed: {error}") from error
    finally:
        _close_lookup(lookup)


def depmap_correlation(
    medea_module: Any,
    status: MedeaDBStatus,
    gene_a: str,
    gene_b: str,
) -> DepMapPairEvidence:
    """Run one direct correlation lookup through Medea's real parser."""
    first = gene_a.strip().upper()
    second = gene_b.strip().upper()
    if not first or not second:
        raise MedeaDatabaseError("gene_a and gene_b are required")
    lookup = _open_depmap_lookup(medea_module, status)
    try:
        result = lookup.get_correlation(first, second)
        return DepMapPairEvidence(
            gene_a=first,
            gene_b=second,
            correlation=float(result["correlation"]),
            p_value=float(result["p_value"]),
            adjusted_p_value=(
                float(result["adjusted_p_value"])
                if result.get("adjusted_p_value") is not None
                else None
            ),
        )
    except KeyError as error:
        raise MedeaDatabaseError(str(error)) from error
    except Exception as error:
        raise MedeaDatabaseError(f"MedeaDB DepMap lookup failed: {error}") from error
    finally:
        _close_lookup(lookup)


def evidence_prompt_text(evidence: MedeaDBEvidence) -> str:
    """Render bounded raw database observations for the literature query."""
    lines = [
        "MedeaDB DepMap 24Q2 exploratory evidence; do not interpret it as clinical truth:"
    ]
    for item in evidence.pairwise:
        adjusted = (
            f", adjusted_p={item.adjusted_p_value:.3g}"
            if item.adjusted_p_value is not None
            else ""
        )
        lines.append(
            f"- {item.gene_a}/{item.gene_b}: r={item.correlation:.4f}, "
            f"p={item.p_value:.3g}{adjusted}"
        )
    for item in evidence.neighbors:
        lines.append(
            f"- {item.query_gene} similar dependency profile: {item.gene}, "
            f"r={item.correlation:.4f}, p={item.p_value:.3g}"
        )
    if evidence.missing_genes:
        lines.append(
            "- Report genes absent from the DepMap matrix: "
            + ", ".join(evidence.missing_genes)
        )
    if not evidence.has_data and not evidence.missing_genes:
        lines.append(
            "- No report gene pair or single-gene neighbor query was applicable."
        )
    return "\n".join(lines)
