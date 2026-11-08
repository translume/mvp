"""OpenAI embeddings with validated batches and bounded, request-local caches."""

from __future__ import annotations

import hashlib
import math
import threading
from collections import OrderedDict
from collections.abc import Mapping, Sequence

from translume_clients.openai_client import OpenAIClient, OpenAISyncClient
from translume_schemas.model_calls import ModelResponseError

MAX_EMBEDDING_INPUT_BYTES = 8192
MAX_EMBEDDING_BATCH_BYTES = 300000
_MODEL_DIMENSIONS = {"text-embedding-3-large": 3072, "text-embedding-3-small": 1536}
_PREPROCESSING_VERSION = "utf8-exact-v1"


def validate_embedding_response(
    response: Mapping[str, object],
    *,
    expected_count: int,
    dimensions: int,
    model_name: str | None = None,
) -> list[list[float]]:
    """Return original-order vectors only after validating the whole response.

    Acceptance criteria:
        1. Every requested index occurs exactly once, regardless of response order.
        2. Every vector has the configured dimensions and finite numeric values.
        3. Missing/duplicate indices and zero vectors fail instead of being filled.
        4. Model mismatches fail; no unrelated cached vector is substituted.
    """
    if model_name and response.get("model") != model_name:
        raise ModelResponseError("OpenAI embeddings returned an unexpected model")
    rows = response.get("data")
    if not isinstance(rows, list) or len(rows) != expected_count:
        raise ModelResponseError(
            "OpenAI embedding count does not match the input count"
        )
    vectors: dict[int, list[float]] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ModelResponseError("OpenAI embedding row is not an object")
        index = row.get("index")
        if (
            type(index) is not int
            or not 0 <= index < expected_count
            or index in vectors
        ):
            raise ModelResponseError(
                "OpenAI embedding indices are invalid or duplicated"
            )
        raw = row.get("embedding")
        if not isinstance(raw, list) or len(raw) != dimensions:
            raise ModelResponseError(
                "OpenAI embedding dimensions do not match configuration"
            )
        if any(type(value) not in {int, float} for value in raw):
            raise ModelResponseError("OpenAI embedding values must be numeric")
        try:
            vector = [float(value) for value in raw]
        except (OverflowError, ValueError) as error:
            raise ModelResponseError(
                "OpenAI embedding values cannot be represented"
            ) from error
        if any(not math.isfinite(value) for value in vector) or not any(vector):
            raise ModelResponseError("OpenAI embeddings must be finite and nonzero")
        vectors[index] = vector
    return [vectors[index] for index in range(expected_count)]


def embedding_batches(texts: Sequence[str], batch_size: int) -> list[list[str]]:
    """Bound inputs conservatively by UTF-8 bytes without downloading a tokenizer.

    Acceptance criteria:
        1. A text token cannot require more than its UTF-8 byte count.
        2. Each item and batch stay within the API token/item limits.
        3. Empty/oversized items fail; text is never silently truncated.
        4. Order and content are preserved exactly.
    """
    if type(batch_size) is not int or not 1 <= batch_size <= 2048:
        raise ValueError("embedding batch_size must be between 1 and 2048")
    if isinstance(texts, (str, bytes)):
        raise TypeError("Embedding inputs must be a sequence of strings")
    batches: list[list[str]] = []
    current: list[str] = []
    total_bytes = 0
    for text in texts:
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Embedding inputs must be nonempty strings")
        size = len(text.encode("utf-8"))
        if size > MAX_EMBEDDING_INPUT_BYTES:
            raise ValueError(
                "Embedding input exceeds the conservative 8192-byte bound; "
                "segment the source without discarding text before embedding"
            )
        if current and (
            len(current) >= batch_size or total_bytes + size > MAX_EMBEDDING_BATCH_BYTES
        ):
            batches.append(current)
            current = []
            total_bytes = 0
        current.append(text)
        total_bytes += size
    if current:
        batches.append(current)
    return batches


class _EmbeddingProviderBase:
    def __init__(
        self,
        *,
        model_name: str = "text-embedding-3-large",
        dimensions: int = 1536,
        batch_size: int = 32,
        cache_size: int = 512,
    ) -> None:
        maximum = _MODEL_DIMENSIONS.get(model_name)
        if maximum is None:
            raise ValueError("Use an OpenAI text-embedding-3 model")
        if type(dimensions) is not int or not 1 <= dimensions <= maximum:
            raise ValueError(f"Embedding dimensions must be between 1 and {maximum}")
        if type(cache_size) is not int or cache_size < 0:
            raise ValueError("Embedding cache_size must be nonnegative")
        embedding_batches([], batch_size)
        self.model_name = model_name
        self.dimensions = dimensions
        self._batch_size = batch_size
        self._cache_size = cache_size
        self._cache: OrderedDict[str, tuple[float, ...]] = OrderedDict()
        self._cache_lock = threading.Lock()

    def _cache_key(self, text: str) -> str:
        content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        return f"{self.model_name}:{self.dimensions}:{_PREPROCESSING_VERSION}:{content_hash}"

    def _prepare(
        self, texts: Sequence[str]
    ) -> tuple[list[str], dict[str, list[float]], list[list[str]]]:
        inputs = list(texts) if not isinstance(texts, (str, bytes)) else texts
        embedding_batches(inputs, self._batch_size)
        cached: dict[str, list[float]] = {}
        missing: list[str] = []
        seen: set[str] = set()
        with self._cache_lock:
            for text in inputs:
                key = self._cache_key(text)
                if key in seen:
                    continue
                seen.add(key)
                if key in self._cache:
                    cached[key] = list(self._cache[key])
                    self._cache.move_to_end(key)
                else:
                    missing.append(text)
        return inputs, cached, embedding_batches(missing, self._batch_size)

    def _request(self, texts: list[str]) -> dict[str, object]:
        return {
            "model": self.model_name,
            "input": texts,
            "dimensions": self.dimensions,
            "encoding_format": "float",
        }

    def _accept_batch(
        self,
        texts: list[str],
        response: Mapping[str, object],
        results: dict[str, list[float]],
    ) -> None:
        vectors = validate_embedding_response(
            response,
            expected_count=len(texts),
            dimensions=self.dimensions,
            model_name=self.model_name,
        )
        with self._cache_lock:
            for text, vector in zip(texts, vectors, strict=True):
                key = self._cache_key(text)
                results[key] = vector
                if self._cache_size:
                    self._cache[key] = tuple(vector)
                    self._cache.move_to_end(key)
                    while len(self._cache) > self._cache_size:
                        self._cache.popitem(last=False)

    def _original_order(
        self, inputs: list[str], vectors: dict[str, list[float]]
    ) -> list[list[float]]:
        return [list(vectors[self._cache_key(text)]) for text in inputs]


class OpenAIEmbeddingProvider(_EmbeddingProviderBase):
    def __init__(self, client: OpenAIClient, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._client = client

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Fetch all uncached vectors remotely, preserving original item order."""
        inputs, vectors, batches = self._prepare(texts)
        for batch in batches:
            response = await self._client.embeddings(self._request(batch))
            self._accept_batch(batch, response, vectors)
        return self._original_order(inputs, vectors)


class OpenAISyncEmbeddingProvider(_EmbeddingProviderBase):
    def __init__(self, client: OpenAISyncClient, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._client = client

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Fetch all uncached vectors remotely for synchronous vendor scorers."""
        inputs, vectors, batches = self._prepare(texts)
        for batch in batches:
            response = self._client.embeddings(self._request(batch))
            self._accept_batch(batch, response, vectors)
        return self._original_order(inputs, vectors)
