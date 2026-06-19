from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from scripts.download_mims_data import (
    MEDEADB_REQUIRED_FILES,
    download_medeadb,
    download_optimuskg,
    inspect_medeadb,
    inspect_optimuskg_cache,
)
from scripts.full_stack_preflight import PreflightError, validate_mims_data


def _write_complete_medeadb(root: Path) -> Path:
    for relative_paths in MEDEADB_REQUIRED_FILES.values():
        for relative in relative_paths:
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"fixture")
    embedding = (
        root / "transcriptformer_embedding" / "embedding_store" / "disease" / "cell.npy"
    )
    embedding.parent.mkdir(parents=True, exist_ok=True)
    embedding.write_bytes(b"fixture")
    (embedding.parent / "metadata.json.gz").write_bytes(b"fixture")
    return root


def _write_graph_pair(root: Path) -> tuple[Path, Path]:
    pl = pytest.importorskip("polars")
    root.mkdir(parents=True, exist_ok=True)
    nodes = root / "largest_connected_component_nodes.parquet"
    edges = root / "largest_connected_component_edges.parquet"
    pl.DataFrame(
        [{"id": "GENE:MTAP", "label": "gene", "properties": "{}"}]
    ).write_parquet(nodes)
    pl.DataFrame(
        [
            {
                "from": "GENE:MTAP",
                "to": "GENE:MTAP",
                "label": "related_to",
            }
        ]
    ).write_parquet(edges)
    return nodes, edges


def test_inspect_medeadb_requires_all_resource_families(tmp_path: Path) -> None:
    medeadb = _write_complete_medeadb(tmp_path / "MedeaDB")
    status = inspect_medeadb(medeadb)
    assert status.available is True
    assert all(status.resources.values())

    (medeadb / "depmap_24q2" / "corr_matrix.npy").unlink()
    status = inspect_medeadb(medeadb)
    assert status.available is False
    assert "depmap_24q2/corr_matrix.npy" in status.missing

    _write_complete_medeadb(medeadb)
    embedding = next(
        (medeadb / "transcriptformer_embedding" / "embedding_store").rglob("*.npy")
    )
    embedding.write_bytes(b"")
    status = inspect_medeadb(medeadb)
    assert status.available is False
    assert "transcriptformer_embedding/embedding_store/**/*.npy" in status.missing

    _write_complete_medeadb(medeadb)
    metadata = next(
        (medeadb / "transcriptformer_embedding" / "embedding_store").rglob(
            "metadata.json.gz"
        )
    )
    metadata.unlink()
    status = inspect_medeadb(medeadb)
    assert status.available is False
    assert (
        "transcriptformer_embedding/embedding_store/**/metadata.json.gz"
        in status.missing
    )

    _write_complete_medeadb(medeadb)
    checkpoint = medeadb / "compass" / "checkpoint" / "pretrainer.pt"
    checkpoint.write_bytes(
        b"version https://git-lfs.github.com/spec/v1\n"
        b"oid sha256:fixture\nsize 123\n"
    )
    status = inspect_medeadb(medeadb)
    assert status.available is False
    assert "compass/checkpoint/pretrainer.pt" in status.missing


def test_download_medeadb_uses_huggingface_snapshot_local_dir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []
    module = ModuleType("huggingface_hub")

    def snapshot_download(**kwargs: object) -> str:
        calls.append(dict(kwargs))
        destination = Path(str(kwargs["local_dir"]))
        _write_complete_medeadb(destination)
        return str(destination)

    module.snapshot_download = snapshot_download  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "huggingface_hub", module)
    destination = tmp_path / "cache" / "MedeaDB"
    status = download_medeadb(destination, revision="revision-1", max_workers=2)

    assert status.available is True
    assert calls[0]["repo_id"] == "mims-harvard/MedeaDB"
    assert calls[0]["repo_type"] == "dataset"
    assert calls[0]["local_dir"] == destination.resolve()
    assert calls[0]["revision"] == "revision-1"


def test_download_optimuskg_uses_client_cache_and_validates_schema(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_nodes, source_edges = _write_graph_pair(tmp_path / "source")
    cache_holder: dict[str, Path] = {}

    def set_cache_dir(path: Path) -> None:
        cache_holder["path"] = Path(path)

    def get_file(relative_path: str, force: bool = False) -> Path:
        del force
        source = source_nodes if "nodes" in relative_path else source_edges
        target = cache_holder["path"] / "doi_10_7910_DVN_IYNGEV" / "1.0" / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
        return target

    monkeypatch.setitem(
        sys.modules,
        "optimuskg",
        SimpleNamespace(set_cache_dir=set_cache_dir, get_file=get_file),
    )
    repo = tmp_path / "OptimusKG"
    repo.mkdir()
    (repo / "README.md").write_text("fixture", encoding="utf-8")
    cache = tmp_path / "cache"

    status = download_optimuskg(repo, cache, use_lcc=True)
    assert status.available is True
    assert status.nodes_path is not None
    assert "doi_10_7910_DVN_IYNGEV/1.0" in status.nodes_path
    assert inspect_optimuskg_cache(cache, use_lcc=True).available is True


def test_optimuskg_inspection_does_not_mix_different_cache_versions(
    tmp_path: Path,
) -> None:
    cache = tmp_path / "cache"
    nodes_dir = cache / "doi" / "version-a"
    edges_dir = cache / "doi" / "version-b"
    nodes_dir.mkdir(parents=True)
    edges_dir.mkdir(parents=True)
    (nodes_dir / "largest_connected_component_nodes.parquet").write_bytes(b"node")
    (edges_dir / "largest_connected_component_edges.parquet").write_bytes(b"edge")

    status = inspect_optimuskg_cache(cache, use_lcc=True)
    assert status.available is False
    assert set(status.missing) == {
        "largest_connected_component_nodes.parquet",
        "largest_connected_component_edges.parquet",
    }


def test_preflight_validates_host_mims_data_paths(tmp_path: Path) -> None:
    medea_host = tmp_path / "medea_cache"
    _write_complete_medeadb(medea_host / "MedeaDB")
    optimus_host = tmp_path / "optimuskg_cache"
    _write_graph_pair(optimus_host / "doi" / "1.0")
    environment = {
        "MEDEA_DATA_HOST_DIR": str(medea_host),
        "OPTIMUSKG_DATA_HOST_DIR": str(optimus_host),
        "OPTIMUSKG_USE_LCC": "true",
    }

    checked = validate_mims_data(tmp_path, environment)
    assert any(item.startswith("medeadb:") for item in checked)
    assert any(item.startswith("optimuskg_cache:") for item in checked)

    (medea_host / "MedeaDB" / "depmap_24q2" / "corr_matrix.npy").unlink()
    with pytest.raises(PreflightError, match="make medea-data"):
        validate_mims_data(tmp_path, environment)


def test_preflight_prefers_exact_relative_data_paths(tmp_path: Path) -> None:
    exact_medeadb = _write_complete_medeadb(tmp_path / "custom" / "MedeaDB")
    exact_optimus = tmp_path / "custom" / "optimuskg"
    _write_graph_pair(exact_optimus / "doi" / "1.0")

    checked = validate_mims_data(
        tmp_path,
        {
            "MEDEADB_PATH": "custom/MedeaDB",
            "OPTIMUSKG_CACHE_DIR": "custom/optimuskg",
            # Conflicting convenience-parent values prove the exact variables win.
            "MEDEA_DATA_HOST_DIR": str(tmp_path / "wrong-medea-parent"),
            "OPTIMUSKG_DATA_HOST_DIR": str(tmp_path / "wrong-optimus-parent"),
            "OPTIMUSKG_USE_LCC": "true",
        },
    )

    assert f"medeadb:{exact_medeadb.resolve()}" in checked
    assert any(
        item.startswith(f"optimuskg_cache:{exact_optimus.resolve()}")
        for item in checked
    )


def test_preflight_rejects_optimuskg_files_with_wrong_schema(
    tmp_path: Path,
) -> None:
    pl = pytest.importorskip("polars")
    medea_host = tmp_path / "medea_cache"
    _write_complete_medeadb(medea_host / "MedeaDB")
    optimus_host = tmp_path / "optimuskg_cache" / "doi" / "1.0"
    optimus_host.mkdir(parents=True)
    pl.DataFrame([{"wrong": "node"}]).write_parquet(
        optimus_host / "largest_connected_component_nodes.parquet"
    )
    pl.DataFrame([{"wrong": "edge"}]).write_parquet(
        optimus_host / "largest_connected_component_edges.parquet"
    )

    with pytest.raises(PreflightError, match="cannot be parsed"):
        validate_mims_data(
            tmp_path,
            {
                "MEDEA_DATA_HOST_DIR": str(medea_host),
                "OPTIMUSKG_DATA_HOST_DIR": str(optimus_host.parents[1]),
                "OPTIMUSKG_USE_LCC": "true",
            },
        )
