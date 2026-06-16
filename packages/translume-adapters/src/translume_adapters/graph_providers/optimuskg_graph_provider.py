from __future__ import annotations

from pathlib import Path

from translume_adapters.errors import ProviderUnavailableError
from translume_adapters.graph_providers.optimuskg_runtime import (
    OptimusKGGraphConfig,
    OptimusKGRuntimeError,
    retrieve_optimuskg_graph_context,
)
from translume_schemas.entities import NormalizedEntitySet
from translume_schemas.graph import GraphEvidenceArtifact


class OptimusKGGraphProvider:
    """Graph provider backed by the real OptimusKG Python client and parquet data.

    The provider does not read generic CSV/JSON edge files and does not
    synthesize graph-like evidence. It imports the vendored OptimusKG package,
    retrieves the documented OptimusKG parquet tables, filters them with Polars,
    and fails loudly when the upstream package or graph data is unavailable.
    """

    def __init__(
        self,
        repo_path: Path,
        *,
        cache_dir: Path | None = None,
        use_lcc: bool = True,
        force_download: bool = False,
        max_edges: int = 500,
    ) -> None:
        self._config = OptimusKGGraphConfig(
            repo_path=repo_path,
            cache_dir=cache_dir,
            use_lcc=use_lcc,
            force_download=force_download,
            max_edges=max_edges,
        )

    async def retrieve_context(
        self,
        entities: NormalizedEntitySet,
    ) -> GraphEvidenceArtifact:
        """Retrieve graph context through the real OptimusKG data path.

        Acceptance criteria:
            1. Missing OptimusKG package/data raises `ProviderUnavailableError`.
            2. Returned nodes and edges derive from OptimusKG parquet tables.
            3. No generic edge CSV/JSON/JSONL files are used.
            4. Missing entity matches are recorded in the artifact.
            5. Graph relationships remain evidence inputs, not clinical claims.
        """
        try:
            return retrieve_optimuskg_graph_context(entities, self._config)
        except OptimusKGRuntimeError as error:
            raise ProviderUnavailableError(str(error)) from error
