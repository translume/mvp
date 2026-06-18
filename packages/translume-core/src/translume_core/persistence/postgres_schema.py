from __future__ import annotations

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True)
class PostgresColumnSpec:
    """Postgres column specification for MVP metadata tables.

    Attributes:
        name: Column name.
        sql_type: SQL type expression.
        nullable: Whether NULL is allowed.
        primary_key: Whether this column is the table primary key.
    """

    name: str
    sql_type: str
    nullable: bool = False
    primary_key: bool = False


@dataclass(frozen=True)
class PostgresTableSpec:
    """Postgres table specification.

    Attributes:
        name: Table name.
        columns: Ordered column specifications.
    """

    name: str
    columns: tuple[PostgresColumnSpec, ...]


TEXT: Final[str] = "text"
TIMESTAMPTZ: Final[str] = "timestamptz"
JSONB: Final[str] = "jsonb"
INTEGER: Final[str] = "integer"
BOOLEAN: Final[str] = "boolean"
DOUBLE_PRECISION: Final[str] = "double precision"


TABLE_CASE_SESSIONS: Final[str] = "case_sessions"
TABLE_SOURCE_FILES: Final[str] = "source_files"
TABLE_DOCUMENT_CHUNKS: Final[str] = "document_chunks"
TABLE_ARTIFACTS: Final[str] = "artifacts"
TABLE_REPORT_FINDINGS: Final[str] = "report_findings"
TABLE_NORMALIZED_ENTITIES: Final[str] = "normalized_entities"
TABLE_GRAPH_EVIDENCE: Final[str] = "graph_evidence"
TABLE_TOOL_OUTPUTS: Final[str] = "tool_outputs"
TABLE_MEDEA_REASONING: Final[str] = "medea_reasoning"
TABLE_EVIDENCE_CLAIMS: Final[str] = "evidence_claims"
TABLE_ARTIFACT_PROVENANCE: Final[str] = "artifact_provenance"
TABLE_VALIDATION_DECISIONS: Final[str] = "validation_decisions"
TABLE_LEDGER_EVENTS: Final[str] = "ledger_events"
TABLE_REVIEW_PACKETS: Final[str] = "review_packets"


MVP_POSTGRES_TABLES: Final[tuple[PostgresTableSpec, ...]] = (
    PostgresTableSpec(
        TABLE_CASE_SESSIONS,
        (
            PostgresColumnSpec("session_id", TEXT, primary_key=True),
            PostgresColumnSpec("case_id", TEXT),
            PostgresColumnSpec("report_type", TEXT),
            PostgresColumnSpec("safety_mode", TEXT),
            PostgresColumnSpec("created_at", TIMESTAMPTZ),
            PostgresColumnSpec("payload", JSONB),
        ),
    ),
    PostgresTableSpec(
        TABLE_SOURCE_FILES,
        (
            PostgresColumnSpec("source_file_id", TEXT, primary_key=True),
            PostgresColumnSpec("case_id", TEXT),
            PostgresColumnSpec("session_id", TEXT),
            PostgresColumnSpec("filename", TEXT),
            PostgresColumnSpec("path", TEXT),
            PostgresColumnSpec("size_bytes", INTEGER),
            PostgresColumnSpec("sha256", TEXT),
            PostgresColumnSpec("payload", JSONB),
        ),
    ),
    PostgresTableSpec(
        TABLE_DOCUMENT_CHUNKS,
        (
            PostgresColumnSpec("chunk_id", TEXT, primary_key=True),
            PostgresColumnSpec("case_id", TEXT),
            PostgresColumnSpec("session_id", TEXT),
            PostgresColumnSpec("source_file_id", TEXT),
            PostgresColumnSpec("report_type", TEXT),
            PostgresColumnSpec("page_start", INTEGER),
            PostgresColumnSpec("page_end", INTEGER),
            PostgresColumnSpec("section", TEXT),
            PostgresColumnSpec("chunk_type", TEXT),
            PostgresColumnSpec("needs_human_review", BOOLEAN),
            PostgresColumnSpec("payload", JSONB),
        ),
    ),
    PostgresTableSpec(
        TABLE_ARTIFACTS,
        (
            PostgresColumnSpec("artifact_id", TEXT, primary_key=True),
            PostgresColumnSpec("artifact_type", TEXT),
            PostgresColumnSpec("case_id", TEXT),
            PostgresColumnSpec("session_id", TEXT),
            PostgresColumnSpec("source_file_id", TEXT),
            PostgresColumnSpec("payload", JSONB),
        ),
    ),
    PostgresTableSpec(
        TABLE_REPORT_FINDINGS,
        (
            PostgresColumnSpec("finding_id", TEXT, primary_key=True),
            PostgresColumnSpec("artifact_id", TEXT),
            PostgresColumnSpec("case_id", TEXT),
            PostgresColumnSpec("session_id", TEXT),
            PostgresColumnSpec("source_file_id", TEXT),
            PostgresColumnSpec("gene", TEXT, nullable=True),
            PostgresColumnSpec("alteration", TEXT),
            PostgresColumnSpec("alteration_type", TEXT),
            PostgresColumnSpec("confidence", DOUBLE_PRECISION),
            PostgresColumnSpec("needs_human_review", BOOLEAN),
            PostgresColumnSpec("payload", JSONB),
        ),
    ),
    PostgresTableSpec(
        TABLE_NORMALIZED_ENTITIES,
        (
            PostgresColumnSpec("entity_id", TEXT, primary_key=True),
            PostgresColumnSpec("artifact_id", TEXT),
            PostgresColumnSpec("case_id", TEXT),
            PostgresColumnSpec("session_id", TEXT),
            PostgresColumnSpec("entity_type", TEXT),
            PostgresColumnSpec("normalized_label", TEXT),
            PostgresColumnSpec("source_finding_id", TEXT, nullable=True),
            PostgresColumnSpec("needs_human_review", BOOLEAN),
            PostgresColumnSpec("payload", JSONB),
        ),
    ),
    PostgresTableSpec(
        TABLE_GRAPH_EVIDENCE,
        (
            PostgresColumnSpec("record_id", TEXT, primary_key=True),
            PostgresColumnSpec("artifact_id", TEXT),
            PostgresColumnSpec("case_id", TEXT),
            PostgresColumnSpec("session_id", TEXT),
            PostgresColumnSpec("record_type", TEXT),
            PostgresColumnSpec("relation_type", TEXT, nullable=True),
            PostgresColumnSpec("payload", JSONB),
        ),
    ),
    PostgresTableSpec(
        TABLE_TOOL_OUTPUTS,
        (
            PostgresColumnSpec("artifact_id", TEXT, primary_key=True),
            PostgresColumnSpec("case_id", TEXT),
            PostgresColumnSpec("session_id", TEXT),
            PostgresColumnSpec("workflow", TEXT),
            PostgresColumnSpec("requires_human_review", BOOLEAN),
            PostgresColumnSpec("payload", JSONB),
        ),
    ),
    PostgresTableSpec(
        TABLE_MEDEA_REASONING,
        (
            PostgresColumnSpec("artifact_id", TEXT, primary_key=True),
            PostgresColumnSpec("case_id", TEXT),
            PostgresColumnSpec("session_id", TEXT),
            PostgresColumnSpec("reasoning_mode", TEXT),
            PostgresColumnSpec("requires_human_review", BOOLEAN),
            PostgresColumnSpec("payload", JSONB),
        ),
    ),
    PostgresTableSpec(
        TABLE_EVIDENCE_CLAIMS,
        (
            PostgresColumnSpec("claim_id", TEXT, primary_key=True),
            PostgresColumnSpec("case_id", TEXT),
            PostgresColumnSpec("session_id", TEXT),
            PostgresColumnSpec("claim_class", TEXT),
            PostgresColumnSpec("validation_status", TEXT),
            PostgresColumnSpec("payload", JSONB),
        ),
    ),
    PostgresTableSpec(
        TABLE_ARTIFACT_PROVENANCE,
        (
            PostgresColumnSpec("artifact_id", TEXT, primary_key=True),
            PostgresColumnSpec("artifact_type", TEXT),
            PostgresColumnSpec("schema_name", TEXT),
            PostgresColumnSpec("model_name", TEXT, nullable=True),
            PostgresColumnSpec("prompt_hash", TEXT, nullable=True),
            PostgresColumnSpec("schema_hash", TEXT, nullable=True),
            PostgresColumnSpec("source_file_id", TEXT, nullable=True),
            PostgresColumnSpec("source_artifact_ids", JSONB),
            PostgresColumnSpec("source_chunk_ids", JSONB),
            PostgresColumnSpec("case_id", TEXT, nullable=True),
            PostgresColumnSpec("session_id", TEXT, nullable=True),
            PostgresColumnSpec("created_at", TIMESTAMPTZ),
            PostgresColumnSpec("validation_status", TEXT),
            PostgresColumnSpec("generation_status", TEXT),
            PostgresColumnSpec("payload", JSONB),
        ),
    ),
    PostgresTableSpec(
        TABLE_VALIDATION_DECISIONS,
        (
            PostgresColumnSpec("decision_id", TEXT, primary_key=True),
            PostgresColumnSpec("claim_id", TEXT),
            PostgresColumnSpec("case_id", TEXT),
            PostgresColumnSpec("session_id", TEXT),
            PostgresColumnSpec("status", TEXT),
            PostgresColumnSpec("reviewer_id", TEXT, nullable=True),
            PostgresColumnSpec("created_at", TIMESTAMPTZ),
            PostgresColumnSpec("payload", JSONB),
        ),
    ),
    PostgresTableSpec(
        TABLE_LEDGER_EVENTS,
        (
            PostgresColumnSpec("event_id", TEXT, primary_key=True),
            PostgresColumnSpec("event_type", TEXT),
            PostgresColumnSpec("case_id", TEXT),
            PostgresColumnSpec("session_id", TEXT),
            PostgresColumnSpec("artifact_id", TEXT, nullable=True),
            PostgresColumnSpec("source_file_id", TEXT, nullable=True),
            PostgresColumnSpec("created_at", TIMESTAMPTZ),
            PostgresColumnSpec("payload", JSONB),
        ),
    ),
    PostgresTableSpec(
        TABLE_REVIEW_PACKETS,
        (
            PostgresColumnSpec("packet_id", TEXT, primary_key=True),
            PostgresColumnSpec("case_id", TEXT),
            PostgresColumnSpec("session_id", TEXT),
            PostgresColumnSpec("source_file_id", TEXT),
            PostgresColumnSpec("payload", JSONB),
        ),
    ),
)


def create_table_sql(table: PostgresTableSpec) -> str:
    """Return CREATE TABLE SQL for a table specification.

    Acceptance criteria:
        1. Includes every configured column in order.
        2. Includes a primary key when the spec marks one.
        3. Does not perform I/O.
        4. Does not interpolate user-provided values.
    """
    column_sql: list[str] = []
    primary_key: str | None = None
    for column in table.columns:
        nullable_sql = "" if not column.nullable or column.primary_key else " NULL"
        column_sql.append(f"{column.name} {column.sql_type}{nullable_sql}")
        if column.primary_key:
            primary_key = column.name
    if primary_key is not None:
        column_sql.append(f"PRIMARY KEY ({primary_key})")
    joined = ",\n    ".join(column_sql)
    return f"CREATE TABLE IF NOT EXISTS {table.name} (\n    {joined}\n);"


def upsert_sql(table: PostgresTableSpec) -> str:
    """Return parameterized UPSERT SQL for a table specification.

    Acceptance criteria:
        1. Uses named placeholders only.
        2. Updates non-primary-key columns on conflict.
        3. Does not include user-provided SQL identifiers.
        4. Does not perform I/O.
    """
    primary_keys = [column.name for column in table.columns if column.primary_key]
    if len(primary_keys) != 1:
        raise ValueError(f"table must have exactly one primary key: {table.name}")
    columns = [column.name for column in table.columns]
    placeholders = [f"%({name})s" for name in columns]
    updates = [f"{name} = EXCLUDED.{name}" for name in columns if name not in primary_keys]
    return (
        f"INSERT INTO {table.name} ({', '.join(columns)}) "
        f"VALUES ({', '.join(placeholders)}) "
        f"ON CONFLICT ({primary_keys[0]}) DO UPDATE SET {', '.join(updates)};"
    )


def table_specs_by_name() -> dict[str, PostgresTableSpec]:
    """Return MVP table specs keyed by table name."""
    return {table.name: table for table in MVP_POSTGRES_TABLES}
