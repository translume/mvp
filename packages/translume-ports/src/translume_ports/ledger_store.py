from __future__ import annotations

from typing import Protocol

from translume_schemas.export import ReviewPacketExport
from translume_schemas.ledger import LedgerEvent


class LedgerStore(Protocol):
    """Protocol for durable review-packet metadata stores."""

    async def ensure_schema(self) -> None:
        """Ensure required ledger/artifact tables exist."""

    async def persist_review_packet(self, packet: ReviewPacketExport) -> dict[str, int]:
        """Persist packet metadata and return record counts by table."""

    async def append_ledger_event(self, event: LedgerEvent) -> None:
        """Persist one ledger event."""
