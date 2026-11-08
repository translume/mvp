"""Remote embedding contracts; no learned model is loaded in this process."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol


class EmbeddingProvider(Protocol):
    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Return one finite, fixed-dimensional vector per original input."""


class SyncEmbeddingProvider(Protocol):
    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Synchronous boundary for vendor literature-retrieval interfaces."""
