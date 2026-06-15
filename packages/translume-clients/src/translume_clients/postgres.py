from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from translume_core.persistence.postgres_records import (
    PostgresRecord,
    ledger_event_to_postgres_record,
    review_packet_to_postgres_records,
)
from translume_core.persistence.postgres_schema import (
    MVP_POSTGRES_TABLES,
    PostgresTableSpec,
    create_table_sql,
    table_specs_by_name,
    upsert_sql,
)
from translume_schemas.export import ReviewPacketExport
from translume_schemas.ledger import LedgerEvent


class PostgresClientError(RuntimeError):
    """Raised when Postgres persistence fails."""


@dataclass(frozen=True)
class PostgresClientConfig:
    """Postgres client configuration.

    Attributes:
        dsn: Psycopg-compatible Postgres connection string.
        connect_timeout_seconds: Connection timeout in seconds.
    """

    dsn: str
    connect_timeout_seconds: float = 10.0


class PostgresLedgerStore:
    """Durable Postgres store for Translume MVP metadata and ledger rows.

    This client is a real production boundary. It does not keep in-memory state
    and does not fabricate persistence results.
    """

    def __init__(self, config: PostgresClientConfig) -> None:
        self._config = config
        self._table_specs = table_specs_by_name()

    async def ensure_schema(self) -> None:
        """Create MVP metadata tables when they do not exist.

        Acceptance criteria:
            1. Executes schema creation against the configured Postgres DSN.
            2. Creates every table in `MVP_POSTGRES_TABLES`.
            3. Propagates connection or SQL failures as `PostgresClientError`.
        """
        try:
            psycopg, _jsonb = _load_psycopg()
            async with await psycopg.AsyncConnection.connect(
                self._config.dsn,
                connect_timeout=self._config.connect_timeout_seconds,
            ) as connection:
                async with connection.cursor() as cursor:
                    for table in MVP_POSTGRES_TABLES:
                        await cursor.execute(create_table_sql(table))
                await connection.commit()
        except Exception as error:  # pragma: no cover - exercised in integration.
            raise PostgresClientError(f"Postgres schema initialization failed: {error}") from error

    async def persist_review_packet(self, packet: ReviewPacketExport) -> dict[str, int]:
        """Persist one review packet and all metadata rows.

        Acceptance criteria:
            1. Converts packet to table records through pure domain logic.
            2. Upserts every record in one transaction.
            3. Rolls back the transaction on failure.
            4. Returns persisted row counts by table.
            5. Does not mutate the packet.
        """
        batch = review_packet_to_postgres_records(packet)
        try:
            psycopg, jsonb = _load_psycopg()
            async with await psycopg.AsyncConnection.connect(
                self._config.dsn,
                connect_timeout=self._config.connect_timeout_seconds,
            ) as connection:
                async with connection.cursor() as cursor:
                    for table_name, records in batch.records_by_table.items():
                        table = self._table_specs[table_name]
                        sql = upsert_sql(table)
                        for record in records:
                            await cursor.execute(sql, _adapt_record(record, table, jsonb))
                await connection.commit()
        except Exception as error:  # pragma: no cover - exercised in integration.
            raise PostgresClientError(f"Postgres review packet persistence failed: {error}") from error
        return batch.counts()


    async def fetch_review_packet_by_session_id(
        self,
        session_id: str,
    ) -> ReviewPacketExport:
        """Fetch the durable review packet for one session.

        Acceptance criteria:
            1. Reads from the configured Postgres DSN.
            2. Returns the JSON payload stored in `review_packets`.
            3. Raises `PostgresClientError` if no packet exists.
            4. Validates the payload as `ReviewPacketExport`.
            5. Performs no fallback or fabricated packet creation.
        """
        if not session_id.strip():
            raise ValueError("session_id is required")
        try:
            psycopg, _jsonb = _load_psycopg()
            async with await psycopg.AsyncConnection.connect(
                self._config.dsn,
                connect_timeout=self._config.connect_timeout_seconds,
            ) as connection:
                async with connection.cursor() as cursor:
                    await cursor.execute(
                        """
                        SELECT payload
                        FROM review_packets
                        WHERE session_id = %(session_id)s
                        LIMIT 1
                        """,
                        {"session_id": session_id},
                    )
                    row = await cursor.fetchone()
        except Exception as error:  # pragma: no cover - integration path.
            raise PostgresClientError(
                f"Postgres review packet fetch failed: {error}"
            ) from error
        if row is None:
            raise PostgresClientError(
                f"review packet not found for session_id={session_id}"
            )
        try:
            return ReviewPacketExport.model_validate(row[0])
        except Exception as error:
            raise PostgresClientError(
                f"stored review packet payload is invalid: {error}"
            ) from error

    async def append_ledger_event(self, event: LedgerEvent) -> None:
        """Append or update one ledger event.

        Acceptance criteria:
            1. Persists exactly one event row.
            2. Uses the same table schema as full packet persistence.
            3. Does not mutate the event.
        """
        table = self._table_specs["ledger_events"]
        record = ledger_event_to_postgres_record(event)
        try:
            psycopg, jsonb = _load_psycopg()
            async with await psycopg.AsyncConnection.connect(
                self._config.dsn,
                connect_timeout=self._config.connect_timeout_seconds,
            ) as connection:
                async with connection.cursor() as cursor:
                    await cursor.execute(upsert_sql(table), _adapt_record(record, table, jsonb))
                await connection.commit()
        except Exception as error:  # pragma: no cover - exercised in integration.
            raise PostgresClientError(f"Postgres ledger event persistence failed: {error}") from error


def _adapt_record(
    record: PostgresRecord,
    table: PostgresTableSpec,
    jsonb_type: type[Any],
) -> dict[str, object]:
    values = dict(record.values)
    adapted: dict[str, object] = {}
    for column in table.columns:
        value = values.get(column.name)
        if column.sql_type == "jsonb" and value is not None:
            adapted[column.name] = jsonb_type(value)
        else:
            adapted[column.name] = value
    return adapted


def _load_psycopg() -> tuple[Any, type[Any]]:
    try:
        import psycopg
        from psycopg.types.json import Jsonb
    except ModuleNotFoundError as error:  # pragma: no cover - dependency path.
        raise PostgresClientError(
            "psycopg is required for Postgres persistence. Install with "
            "`uv sync --group postgres` or build the Docker service."
        ) from error
    return psycopg, Jsonb
