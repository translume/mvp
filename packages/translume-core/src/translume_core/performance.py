from __future__ import annotations

import asyncio
import copy
import json
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
from typing import TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class LatencyBudgetExceededError(TimeoutError):
    """Raised when a configured workflow or prompt stage exceeds its budget."""


@dataclass(frozen=True)
class CacheStats:
    """Snapshot of cache behavior for tests and observability."""

    entries: int
    hits: int
    misses: int
    stores: int
    in_flight: int


@dataclass
class _CacheEntry:
    value: object
    expires_at: float | None


class AsyncInMemoryCache:
    """Small async cache for provider/model orchestration boundaries.

    Acceptance criteria:
        1. Concurrent callers for the same key share one in-flight factory call.
        2. Returned values are deep-copied so callers cannot mutate cached state.
        3. TTL expiry is enforced against a monotonic clock.
        4. Failed factory calls are not cached.
        5. The cache is explicit infrastructure, not a clinical-data fallback.
    """

    def __init__(self, *, time_function: Callable[[], float] | None = None) -> None:
        self._time_function = time.monotonic if time_function is None else time_function
        self._entries: dict[str, _CacheEntry] = {}
        self._in_flight: dict[str, asyncio.Task[object]] = {}
        self._lock = asyncio.Lock()
        self._hits = 0
        self._misses = 0
        self._stores = 0

    async def get_or_set(
        self,
        key: str,
        factory: Callable[[], Awaitable[T]],
        *,
        ttl_seconds: float | None,
    ) -> T:
        """Return cached value or compute/cache it through the async factory."""
        now = self._time_function()
        async with self._lock:
            cached = self._entries.get(key)
            if cached is not None and _entry_is_valid(cached, now):
                self._hits += 1
                return _copy_cached_value(cached.value)
            if cached is not None:
                self._entries.pop(key, None)
            task = self._in_flight.get(key)
            owner = False
            if task is None:
                self._misses += 1
                task = asyncio.create_task(factory())
                self._in_flight[key] = task
                owner = True
            else:
                self._hits += 1

        try:
            value = await task
        except Exception:
            if owner:
                async with self._lock:
                    if self._in_flight.get(key) is task:
                        self._in_flight.pop(key, None)
            raise

        if owner:
            async with self._lock:
                if self._in_flight.get(key) is task:
                    self._in_flight.pop(key, None)
                if ttl_seconds is None or ttl_seconds > 0:
                    expires_at = (
                        None
                        if ttl_seconds is None
                        else self._time_function() + ttl_seconds
                    )
                    self._entries[key] = _CacheEntry(
                        value=_copy_cached_value(value),
                        expires_at=expires_at,
                    )
                    self._stores += 1
        return _copy_cached_value(value)

    async def clear(self) -> None:
        """Clear cached entries and in-flight state."""
        async with self._lock:
            self._entries.clear()
            self._in_flight.clear()

    def stats(self) -> CacheStats:
        """Return a non-mutating cache stats snapshot."""
        return CacheStats(
            entries=len(self._entries),
            hits=self._hits,
            misses=self._misses,
            stores=self._stores,
            in_flight=len(self._in_flight),
        )


async def run_with_latency_budget(
    *,
    stage_name: str,
    timeout_seconds: float | None,
    awaitable: Awaitable[T],
) -> T:
    """Await a stage with an optional latency budget.

    A `None` or non-positive timeout disables enforcement. This keeps budgets
    explicit in config while avoiding hidden default timeouts in tests/local dev.
    """
    if timeout_seconds is None or timeout_seconds <= 0:
        return await awaitable
    try:
        return await asyncio.wait_for(awaitable, timeout=timeout_seconds)
    except TimeoutError as error:
        raise LatencyBudgetExceededError(
            f"stage '{stage_name}' exceeded latency budget "
            f"of {timeout_seconds:g} seconds"
        ) from error


def stable_cache_key(namespace: str, *parts: object) -> str:
    """Return a stable opaque cache key for structured provider inputs."""
    payload = {
        "namespace": namespace,
        "parts": [_json_safe(part) for part in parts],
    }
    raw = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return f"{namespace}:{sha256(raw.encode('utf-8')).hexdigest()}"


def _entry_is_valid(entry: _CacheEntry, now: float) -> bool:
    return entry.expires_at is None or entry.expires_at > now


def _copy_cached_value(value: T) -> T:
    if isinstance(value, BaseModel):
        return value.model_copy(deep=True)  # type: ignore[return-value]
    return copy.deepcopy(value)


def _json_safe(value: object) -> object:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, Mapping):
        return {
            str(key): _json_safe(item)
            for key, item in sorted(value.items(), key=lambda kv: str(kv[0]))
        }
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes, bytearray),
    ):
        return [_json_safe(item) for item in value]
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")  # type: ignore[attr-defined]
    return repr(value)
