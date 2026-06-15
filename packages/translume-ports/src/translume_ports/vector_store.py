from __future__ import annotations

from typing import Protocol


class VectorStore(Protocol):
    """Protocol for OpenSearch-like retrieval stores."""

    async def ensure_index(self, index_name: str, body: dict[str, object]) -> None:
        """Ensure an index exists."""

    async def index(
        self,
        index_name: str,
        documents: list[dict[str, object]],
    ) -> None:
        """Index documents into a retrieval store."""

    async def search(
        self,
        index_name: str,
        query: dict[str, object],
    ) -> list[dict[str, object]]:
        """Search a retrieval store."""
