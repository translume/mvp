from __future__ import annotations

from typing import Protocol

from translume_schemas.export import ReviewPacketExport
from translume_schemas.ledger import LedgerEvent
from translume_schemas.session import CaseSession, StoredFile


class LedgerStore(Protocol):
    """Protocol for durable review-packet metadata stores."""

    async def ensure_schema(self) -> None:
        """Ensure required ledger/artifact tables exist."""

    async def persist_ingestion_metadata(
        self,
        session: CaseSession,
        stored_file: StoredFile,
        upload_event: LedgerEvent,
    ) -> dict[str, int]:
        """Persist session, source-file, and upload ledger metadata."""

    async def persist_review_packet(self, packet: ReviewPacketExport) -> dict[str, int]:
        """Persist packet metadata and return record counts by table."""

    async def append_ledger_event(self, event: LedgerEvent) -> None:
        """Persist one ledger event."""
