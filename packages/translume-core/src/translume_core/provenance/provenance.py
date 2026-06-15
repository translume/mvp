from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from translume_core.provenance.hashing import hash_text, stable_json_hash
from translume_schemas.provenance import ArtifactProvenance


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
    artifact_id: str | None = None,
) -> ArtifactProvenance:
    """Build provenance metadata for a generated artifact.

    Acceptance criteria:
        1. Includes artifact_id, artifact_type, and schema_name.
        2. Includes model name when provided.
        3. Includes prompt and schema hashes when provided.
        4. Includes source artifact IDs.
        5. Function is deterministic if artifact_id and timestamp are supplied.
    """
    return ArtifactProvenance(
        artifact_id=artifact_id or f"artifact_{uuid4().hex}",
        artifact_type=artifact_type,
        schema_name=schema_name,
        model_name=model_name,
        prompt_hash=hash_text(prompt_text) if prompt_text is not None else None,
        schema_hash=stable_json_hash(schema_json) if schema_json is not None else None,
        source_file_id=source_file_id,
        source_artifact_ids=source_artifact_ids,
        created_at=created_at,
    )
