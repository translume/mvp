from __future__ import annotations

import csv
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from translume_adapters.errors import ProviderUnavailableError
from translume_schemas.entities import NormalizedEntitySet
from translume_schemas.graph import GraphEdge, GraphEvidenceArtifact, GraphNode


class OptimusKGGraphProvider:
    """Graph adapter that uses local OptimusKG-derived edge files.

    The production path requires real local graph data exported from the
    vendored OptimusKG repo or cache. It does not fabricate graph edges.
    """

    def __init__(self, edge_csv_path: Path) -> None:
        self._edge_csv_path = edge_csv_path

    async def retrieve_context(
        self,
        entities: NormalizedEntitySet,
    ) -> GraphEvidenceArtifact:
        """Retrieve graph context for normalized entities.

        Acceptance criteria:
            1. Missing graph data raises `ProviderUnavailableError`.
            2. Every returned node has provenance.
            3. Every returned edge has relation type and source.
            4. Every missing entity is recorded.
            5. No graph relationship is converted into a clinical claim here.

        Args:
            entities: Normalized report entities.

        Returns:
            Graph evidence artifact.
        """
        if not self._edge_csv_path.exists():
            raise ProviderUnavailableError(
                f"OptimusKG edge CSV is missing: {self._edge_csv_path}. "
                "Run vendor/index workflow before enabling MIMS-required mode."
            )
        rows = _read_edges(self._edge_csv_path)
        labels = {entity.normalized_label.upper(): entity.entity_id for entity in entities.entities}
        nodes: dict[str, GraphNode] = {}
        edges: list[GraphEdge] = []
        matched_entities: set[str] = set()
        for row in rows:
            subject = row["subject"].upper()
            obj = row["object"].upper()
            if subject not in labels and obj not in labels:
                continue
            for label, kind in [(subject, row.get("subject_kind", "entity")), (obj, row.get("object_kind", "entity"))]:
                node_id = f"node_{uuid5(NAMESPACE_URL, label).hex[:16]}"
                nodes.setdefault(
                    node_id,
                    GraphNode(
                        node_id=node_id,
                        label=label,
                        kind=kind or "entity",
                        source="optimuskg_local_csv",
                        provenance={"edge_csv": str(self._edge_csv_path)},
                    ),
                )
            if subject in labels:
                matched_entities.add(labels[subject])
            if obj in labels:
                matched_entities.add(labels[obj])
            source_node_id = f"node_{uuid5(NAMESPACE_URL, subject).hex[:16]}"
            target_node_id = f"node_{uuid5(NAMESPACE_URL, obj).hex[:16]}"
            edge_seed = f"{subject}:{row['relation_type']}:{obj}:{row.get('source', '')}"
            edges.append(
                GraphEdge(
                    edge_id=f"edge_{uuid5(NAMESPACE_URL, edge_seed).hex[:16]}",
                    source_node_id=source_node_id,
                    target_node_id=target_node_id,
                    relation_type=row["relation_type"],
                    source=row.get("source", "optimuskg"),
                    provenance={"edge_csv": str(self._edge_csv_path)},
                )
            )
        missing = [entity.entity_id for entity in entities.entities if entity.entity_id not in matched_entities]
        artifact_id = f"artifact_{uuid5(NAMESPACE_URL, entities.artifact_id + ':graph').hex[:16]}"
        return GraphEvidenceArtifact(
            artifact_id=artifact_id,
            source_entity_ids=[entity.entity_id for entity in entities.entities],
            nodes=list(nodes.values()),
            edges=edges,
            missing_entities=missing,
            warnings=[] if edges else ["no_optimuskg_edges_matched_normalized_entities"],
        )


def _read_edges(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"subject", "relation_type", "object"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ProviderUnavailableError(
                f"OptimusKG edge CSV missing columns: {', '.join(sorted(missing))}"
            )
        return [{key: value or "" for key, value in row.items()} for row in reader]
