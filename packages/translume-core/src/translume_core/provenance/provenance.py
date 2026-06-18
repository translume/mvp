from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from uuid import uuid4

from translume_core.provenance.hashing import hash_text, stable_json_hash
from translume_schemas.provenance import ArtifactProvenance


class ArtifactProvenanceError(RuntimeError):
    """Raised when artifact provenance is incomplete or unsafe for production."""


def build_artifact_provenance(
    artifact_type: str,
    schema_name: str,
    model_name: str | None,
    prompt_text: str | None,
    schema_json: dict[str, object] | None,
    source_artifact_ids: list[str],
    created_at: datetime,
    *,
    source_file_id: str | None = None,
    source_chunk_ids: Sequence[str] | None = None,
    generation_status: str = "generated",
    artifact_id: str | None = None,
) -> ArtifactProvenance:
    """Build provenance metadata for a generated artifact.

    Acceptance criteria:
        1. Includes artifact_id, artifact_type, and schema_name.
        2. Includes model/provider name when provided.
        3. Includes prompt and schema hashes when provided.
        4. Separates source artifact IDs from source chunk IDs.
        5. Includes generation status for runtime auditability.
        6. Function is deterministic if artifact_id and timestamp are supplied.
    """
    return ArtifactProvenance(
        artifact_id=artifact_id or f"artifact_{uuid4().hex}",
        artifact_type=artifact_type,
        schema_name=schema_name,
        model_name=model_name,
        prompt_hash=hash_text(prompt_text) if prompt_text is not None else None,
        schema_hash=stable_json_hash(schema_json) if schema_json is not None else None,
        source_file_id=source_file_id,
        source_chunk_ids=list(source_chunk_ids or []),
        source_artifact_ids=list(source_artifact_ids),
        created_at=created_at,
        generation_status=generation_status,
    )


def require_complete_provenance_record(record: ArtifactProvenance) -> None:
    """Fail if one provenance record is not production-auditable.

    Acceptance criteria:
        1. Rejects missing artifact, type, schema, schema hash, and status.
        2. Rejects known generic model/provider labels.
        3. Requires either source artifacts or source chunks unless the record is
           the first report-extraction artifact sourced directly from chunks.
        4. Does not mutate the input record.
    """
    missing = []
    if not record.artifact_id.strip():
        missing.append("artifact_id")
    if not record.artifact_type.strip():
        missing.append("artifact_type")
    if not record.schema_name.strip():
        missing.append("schema_name")
    if not (record.schema_hash or "").strip():
        missing.append("schema_hash")
    if not record.generation_status.strip():
        missing.append("generation_status")
    if missing:
        raise ArtifactProvenanceError(
            f"artifact provenance {record.artifact_id or '<missing>'} is missing: "
            + ", ".join(missing)
        )
    if record.model_name and _is_generic_model_name(record.model_name):
        raise ArtifactProvenanceError(
            f"artifact provenance {record.artifact_id} uses generic model/provider name: "
            f"{record.model_name}"
        )
    if not record.source_artifact_ids and not record.source_chunk_ids:
        raise ArtifactProvenanceError(
            f"artifact provenance {record.artifact_id} has no source artifact or chunk IDs"
        )


def _is_generic_model_name(value: str) -> bool:
    lowered = value.strip().casefold()
    return lowered in {
        "translume_mvp",
        "deterministic_compiler_or_external_provider",
        "external_provider",
        "placeholder",
        "mock",
        "fake",
    }
