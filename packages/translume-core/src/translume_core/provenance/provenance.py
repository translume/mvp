from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from translume_core.provenance.hashing import hash_text, stable_json_hash
from translume_ports.model_provider import ModelCallCapture
from translume_schemas.model_calls import ModelCallRecord
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
    model_calls: Sequence[ModelCallRecord] = (),
    model_call_ids: Sequence[str] = (),
    component_provenance: Sequence[ArtifactProvenance] = (),
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
    completed_calls = [
        record
        for record in model_calls
        if record.endpoint == "/responses" and record.status == "completed"
    ]
    completed = completed_calls[-1] if completed_calls else None
    return ArtifactProvenance(
        artifact_id=artifact_id or f"artifact_{uuid4().hex}",
        artifact_type=artifact_type,
        schema_name=schema_name,
        model_name=(completed.actual_model or model_name) if completed else model_name,
        prompt_hash=hash_text(prompt_text) if prompt_text is not None else None,
        schema_hash=stable_json_hash(schema_json) if schema_json is not None else None,
        source_file_id=source_file_id,
        source_chunk_ids=list(source_chunk_ids or []),
        source_artifact_ids=list(source_artifact_ids),
        created_at=created_at,
        generation_status=generation_status,
        provider_name=completed.provider if completed else None,
        reasoning_mode=completed.reasoning_mode if completed else None,
        reasoning_effort=completed.reasoning_effort if completed else None,
        wire_schema_hash=completed.wire_schema_hash if completed else None,
        model_calls=list(model_calls),
        model_call_ids=list(
            dict.fromkeys(
                [*model_call_ids, *[record.call_id for record in model_calls]]
            )
        ),
        component_provenance=list(component_provenance),
    )


def model_call_snapshot(model_provider: object) -> tuple[ModelCallRecord, ...]:
    """Read an immutable request-scoped snapshot without manufacturing records.

    Acceptance criteria:
        1. Only actual typed call records are accepted.
        2. Pure test/domain providers without telemetry produce no fake usage.
        3. No caller-owned collection is mutated.
    """
    records = getattr(model_provider, "call_records", ())
    if not isinstance(records, (list, tuple)):
        raise ArtifactProvenanceError(
            "Model call records must be an immutable snapshot"
        )
    if any(not isinstance(record, ModelCallRecord) for record in records):
        raise ArtifactProvenanceError(
            "Model call provenance contains an invalid record"
        )
    return tuple(records)


@dataclass(frozen=True)
class _UnscopedCallCapture:
    """Compatibility capture for pure domain providers without remote calls."""

    model_provider: object
    start: int

    @property
    def records(self) -> tuple[ModelCallRecord, ...]:
        return model_call_snapshot(self.model_provider)[self.start :]


@contextmanager
def capture_model_calls(model_provider: object) -> Iterator[ModelCallCapture]:
    """Isolate generated-artifact provenance from concurrently running stages.

    Acceptance criteria:
        1. Production providers use an explicit task-local capture scope.
        2. Pure domain providers do not acquire manufactured API metadata.
        3. Scope cleanup occurs even when generation or validation fails.
    """
    capture = getattr(model_provider, "capture_calls", None)
    if callable(capture):
        with capture() as scope:
            yield scope
    else:
        yield _UnscopedCallCapture(
            model_provider, len(model_call_snapshot(model_provider))
        )


def unique_model_calls(
    records: Sequence[ArtifactProvenance],
) -> tuple[ModelCallRecord, ...]:
    """Count a real attempt once even when several artifacts reference it.

    Acceptance criteria:
        1. Traverses extraction and decision-stage component provenance.
        2. Preserves first-observed call order and rejects conflicting IDs.
        3. Does not infer usage for requests without a provider usage record.
    """
    unique: dict[str, ModelCallRecord] = {}
    pending = list(reversed(records))
    while pending:
        provenance = pending.pop()
        for call in provenance.model_calls:
            existing = unique.get(call.call_id)
            if existing is not None and existing != call:
                raise ArtifactProvenanceError(
                    "Conflicting metadata for one model call ID"
                )
            unique[call.call_id] = call
        pending.extend(reversed(provenance.component_provenance))
    return tuple(unique.values())


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
