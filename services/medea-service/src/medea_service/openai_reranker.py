"""Remote OpenAI embeddings with deterministic CPU passage similarity."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Protocol


class SynchronousEmbeddingProvider(Protocol):
    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class OpenAIEmbeddingReranker:
    """Satisfy both upstream OpenScholar ranking paths without a local encoder."""

    def __init__(self, provider: SynchronousEmbeddingProvider) -> None:
        self._provider = provider

    def compute_score(
        self, pairs: list[list[str]], batch_size: int = 50
    ) -> list[float]:
        """Score query/passage pairs in input order using remote vectors.

        Acceptance criteria:
            1. All nonempty input pairs receive one finite cosine score.
            2. Long inputs are fully segmented, never silently truncated.
            3. Duplicate segments are embedded once per scoring operation.
            4. No learned local model or local model weights are accessed.
        """
        if batch_size <= 0:
            raise ValueError("batch_size must be positive")
        segments: dict[str, tuple[str, ...]] = {}
        for pair in pairs:
            if len(pair) != 2 or any(
                not isinstance(text, str) or not text.strip() for text in pair
            ):
                raise ValueError("reranker pairs must contain two nonempty strings")
            for text in pair:
                if text not in segments:
                    # Whitespace-only segments contain no semantic input and
                    # are rejected by the embeddings API. All non-whitespace
                    # content remains present, even across Unicode boundaries.
                    segments[text] = tuple(
                        part for part in _segment_utf8(text) if part.strip()
                    )
        unique_segments = list(
            dict.fromkeys(part for parts in segments.values() for part in parts)
        )
        if not unique_segments:
            return []
        vectors: dict[str, list[float]] = {}
        for start in range(0, len(unique_segments), min(batch_size, 32)):
            batch = unique_segments[start : start + min(batch_size, 32)]
            embedded = self._provider.embed(batch)
            if len(embedded) != len(batch):
                raise ValueError("embedding response cardinality mismatch")
            vectors.update(zip(batch, embedded, strict=True))
        averaged = {
            text: _weighted_unit_mean(parts, vectors)
            for text, parts in segments.items()
        }
        return [_cosine(averaged[first], averaged[second]) for first, second in pairs]


def _segment_utf8(text: str, max_bytes: int = 8000) -> tuple[str, ...]:
    """Split losslessly below the embedding input bound without token models."""
    output: list[str] = []
    current: list[str] = []
    size = 0
    for character in text:
        length = len(character.encode("utf-8"))
        if size + length > max_bytes:
            output.append("".join(current))
            current, size = [], 0
        current.append(character)
        size += length
    if current:
        output.append("".join(current))
    return tuple(output)


def _weighted_unit_mean(
    parts: Sequence[str], vectors: dict[str, list[float]]
) -> list[float]:
    dimension = len(vectors[parts[0]])
    if not dimension:
        raise ValueError("embedding vectors must not be empty")
    result = [0.0] * dimension
    for part in parts:
        vector = vectors[part]
        if len(vector) != dimension or not all(
            math.isfinite(value) for value in vector
        ):
            raise ValueError("embedding vectors have inconsistent or nonfinite values")
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            raise ValueError("embedding vector has zero norm")
        weight = len(part.encode("utf-8"))
        for index, value in enumerate(vector):
            result[index] += weight * value / norm
    norm = math.sqrt(sum(value * value for value in result))
    if norm == 0 or not math.isfinite(norm):
        raise ValueError("segmented embedding mean has zero or invalid norm")
    return [value / norm for value in result]


def _cosine(first: Sequence[float], second: Sequence[float]) -> float:
    if len(first) != len(second):
        raise ValueError("embedding dimensions differ")
    score = sum(a * b for a, b in zip(first, second, strict=True))
    if not math.isfinite(score):
        raise ValueError("passage similarity must be finite")
    return max(-1.0, min(1.0, score))
