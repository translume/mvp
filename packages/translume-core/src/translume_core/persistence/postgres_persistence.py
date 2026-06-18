from __future__ import annotations

from dataclasses import dataclass

from translume_core.persistence.postgres_records import review_packet_to_postgres_records
from translume_schemas.export import ReviewPacketExport
from translume_schemas.ledger import LedgerEvent
from translume_schemas.session import CaseSession, StoredFile


@dataclass(frozen=True)
class PostgresPersistenceResult:
    """Summary of Postgres persistence work.

    Attributes:
        persisted_records_by_table: Count of rows persisted by table name.
    """

    persisted_records_by_table: dict[str, int]

async def persist_ingestion_metadata_to_postgres(
    session: CaseSession,
    stored_file: StoredFile,
    upload_event: LedgerEvent,
    ledger_store: object,
) -> PostgresPersistenceResult:
    """Persist session, source-file, and upload ledger metadata immediately.

    Acceptance criteria:
        1. Ensures schema before writing upload metadata.
        2. Persists the case session row before document extraction can begin.
        3. Persists the source-file row before document extraction can begin.
        4. Persists the upload ledger event before document extraction can begin.
        5. Propagates store failures instead of silently continuing.
        6. Does not mutate any supplied object.
    """
    await ledger_store.ensure_schema()
    counts = await ledger_store.persist_ingestion_metadata(
        session,
        stored_file,
        upload_event,
    )
    return PostgresPersistenceResult(persisted_records_by_table=dict(counts))




async def persist_review_packet_to_postgres(
    packet: ReviewPacketExport,
    ledger_store: object,
) -> PostgresPersistenceResult:
    """Persist review packet metadata to Postgres through a ledger store.

    Acceptance criteria:
        1. Ensures the schema before writing records.
        2. Persists sessions, source files, chunks, artifacts, findings,
           evidence, claims, provenance, validation decisions, ledger events,
           and the full review packet payload.
        3. Any store failure propagates to the caller.
        4. The packet is not mutated.

    Args:
        packet: Review packet export.
        ledger_store: Object implementing `ensure_schema` and
            `persist_review_packet`.

    Returns:
        Persistence counts by table.
    """
    await ledger_store.ensure_schema()
    counts = await ledger_store.persist_review_packet(packet)
    return PostgresPersistenceResult(persisted_records_by_table=dict(counts))


async def append_ledger_event_to_postgres(
    event: LedgerEvent,
    ledger_store: object,
) -> None:
    """Append one ledger event through a ledger store.

    Acceptance criteria:
        1. Ensures schema before appending.
        2. Propagates store failures.
        3. Does not mutate the event.
    """
    await ledger_store.ensure_schema()
    await ledger_store.append_ledger_event(event)
